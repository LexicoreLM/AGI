"""FastAPI application: web UI + REST endpoints."""

from __future__ import annotations

import json
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from loguru import logger

from dorim_recognition.api.batch import process_stream
from dorim_recognition.api.jobs import REGISTRY, BatchJob, BatchCancelled
from dorim_recognition.api.schemas import (
    HealthResponse,
    MatchCandidateOut,
    MatchRequest,
    MatchResponse,
)
from dorim_recognition.core.config import get_settings
from dorim_recognition.db.connection import raw_connection
from dorim_recognition.matching.engine import MatchQuery, get_index, match


BASE = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = BASE / "templates"
STATIC_DIR = BASE / "static"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Warm up the catalog index so the first request isn't slow."""
    logger.info("warming up catalog index...")
    get_index()
    logger.success("ready.")
    yield


app = FastAPI(
    title="Dorim Drug Recognition",
    description="Maps raw drug names + manufacturer to catalog entries with confidence.",
    version="0.1.0",
    lifespan=lifespan,
)

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# -----------------------------------------------------------------------------
# JSON API
# -----------------------------------------------------------------------------

@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    settings = get_settings()
    with raw_connection(autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) AS c FROM {settings.engine_schema}.products")
            products = cur.fetchone()["c"]
            cur.execute(f"SELECT COUNT(*) AS c FROM {settings.engine_schema}.aliases")
            aliases = cur.fetchone()["c"]
    return HealthResponse(status="ok", catalog_size=products, aliases_size=aliases)


@app.post("/match", response_model=MatchResponse)
def match_endpoint(req: MatchRequest) -> MatchResponse:
    """Single-row matching."""
    res = match(
        MatchQuery(name=req.name, maker_name=req.maker_name, contractor_id=req.contractor_id),
        top_n=req.top_n,
    )
    candidates = [
        MatchCandidateOut(
            product_id=c.product_id,
            search_string=c.search_string,
            confidence=c.confidence,
            confidence_percent=round(c.confidence * 100, 1),
            components=c.components,
        )
        for c in res.candidates
    ]
    # Telemetry — fire-and-forget.
    try:
        _log_match(req, res)
    except Exception as exc:  # pragma: no cover - telemetry must not break API
        logger.warning("match_logs insert failed: {}", exc)
    return MatchResponse(
        candidates=candidates,
        exact_alias_hit=res.exact_alias_hit,
        stage_ms={k: round(v, 2) for k, v in res.stage_ms.items()},
        external_code=req.external_code,
    )


def _log_match(req: MatchRequest, res) -> None:
    settings = get_settings()
    top = res.candidates[0] if res.candidates else None
    with raw_connection(autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"INSERT INTO {settings.engine_schema}.match_logs "
                "(input_name, input_maker, input_contractor_id, top_product_id, "
                "top_confidence, candidates, stage_ms) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (
                    req.name,
                    req.maker_name,
                    req.contractor_id,
                    top.product_id if top else None,
                    top.confidence if top else None,
                    json.dumps([
                        {"product_id": c.product_id, "confidence": c.confidence, "components": c.components}
                        for c in res.candidates
                    ]),
                    json.dumps(res.stage_ms),
                ),
            )


@app.post("/match/batch")
async def batch_submit(
    file: UploadFile = File(...),
    top_n: int = Form(3),
) -> JSONResponse:
    """Submit a batch job. Returns immediately with a ``job_id``.

    Expected columns (case-insensitive, any one variant):
      - name: 'name' / 'product_name' / 'название' / 'наименование' / 'товар'
      - maker: 'maker' / 'maker_name' / 'manufacturer' / 'производитель' / 'изготовитель'
      - contractor_id (optional): 'contractor_id' / 'contractor' / 'контрагент'

    Poll ``GET /match/batch/{job_id}`` for progress, then
    ``GET /match/batch/{job_id}/download`` when ``download_ready=true``.
    """
    settings = get_settings()
    raw = await file.read()
    if len(raw) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"File too large (>{settings.max_upload_mb} MB)")

    filename = file.filename or "input.xlsx"
    job = REGISTRY.create(filename)

    def work(j: BatchJob) -> None:
        t0 = time.perf_counter()
        out_bytes, out_name, cancelled = process_stream(
            raw,
            filename,
            top_n=top_n,
            progress_cb=lambda done, total: _update_progress(j, done, total),
            cancel_cb=lambda: j.cancel_requested,
        )
        # Always offer a (possibly partial) result so users don't lose work.
        j.result_bytes = out_bytes
        j.result_filename = out_name
        if cancelled:
            j.status = "cancelled"
            logger.info(
                "batch job {} CANCELLED at {}/{} after {:.2f}s",
                j.job_id, j.processed, j.total, time.perf_counter() - t0,
            )
        else:
            logger.info(
                "batch job {} processed {} rows in {:.2f}s -> {}",
                j.job_id, j.total, time.perf_counter() - t0, out_name,
            )

    REGISTRY.submit(job, work)
    return JSONResponse({"job_id": job.job_id, "filename": filename})


def _update_progress(job: BatchJob, processed: int, total: int) -> None:
    """Mutate progress fields. Set total on first call."""
    if not job.total:
        job.total = total
    job.processed = processed


@app.get("/match/batch/{job_id}")
def batch_status(job_id: str) -> JSONResponse:
    job = REGISTRY.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return JSONResponse(job.to_public())


@app.get("/match/batch/{job_id}/download")
def batch_download(job_id: str) -> Response:
    job = REGISTRY.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    if job.result_bytes is None or job.status not in ("done", "cancelled"):
        raise HTTPException(status_code=409, detail=f"job not ready (status={job.status})")
    return Response(
        content=job.result_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{job.result_filename}"'},
    )


@app.post("/match/batch/{job_id}/cancel")
def batch_cancel(job_id: str) -> JSONResponse:
    """Request cancellation. The worker stops at the next progress checkpoint
    (typically within ~1% of total rows). The job's processed-so-far rows are
    still downloadable as a partial result."""
    if not REGISTRY.request_cancel(job_id):
        job = REGISTRY.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="job not found")
        raise HTTPException(
            status_code=409,
            detail=f"job already terminal (status={job.status})",
        )
    return JSONResponse({"cancel_requested": True})


# -----------------------------------------------------------------------------
# Web UI
# -----------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def index_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "index.html", {"result": None})


@app.post("/", response_class=HTMLResponse)
def index_match(
    request: Request,
    name: str = Form(...),
    maker_name: str = Form(""),
    contractor_id: str = Form(""),
    external_code: str = Form(""),
    top_n: int = Form(5),
) -> HTMLResponse:
    contractor = None
    if contractor_id.strip():
        try:
            contractor = int(contractor_id.strip())
        except ValueError:
            contractor = None
    res = match(
        MatchQuery(name=name, maker_name=maker_name or None, contractor_id=contractor),
        top_n=top_n,
    )
    settings = get_settings()
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "result": res,
            "form": {
                "name": name,
                "maker_name": maker_name,
                "contractor_id": contractor_id,
                "external_code": external_code,
                "top_n": top_n,
            },
            "external_code": external_code.strip() or None,
            "threshold": settings.low_confidence_threshold,
        },
    )
