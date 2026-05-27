"""Command-line entry point: `uv run python -m dorim_recognition.cli ...`"""

from __future__ import annotations

import typer
from loguru import logger

from dorim_recognition.core.config import get_settings
from dorim_recognition.db.ingest import ingest_aliases, ingest_products
from dorim_recognition.db.migrate import apply_migrations
from dorim_recognition.matching.engine import MatchQuery, get_index, match

app = typer.Typer(help="Dorim Drug Recognition — operator CLI", add_completion=False)


@app.command()
def migrate() -> None:
    """Apply pending SQL migrations to the database."""
    apply_migrations()


@app.command()
def ingest(
    products_only: bool = typer.Option(False, "--products-only"),
    aliases_only: bool = typer.Option(False, "--aliases-only"),
) -> None:
    """Rebuild recognition_engine.products and recognition_engine.aliases."""
    if not aliases_only:
        ingest_products()
    if not products_only:
        ingest_aliases()


@app.command()
def search(
    name: str = typer.Argument(..., help="Drug name to look up"),
    maker: str = typer.Option("", "--maker", "-m"),
    top_n: int = typer.Option(5, "--top-n", "-n"),
    no_alias: bool = typer.Option(False, "--no-alias", help="Disable alias short-circuit"),
) -> None:
    """Run a single lookup and print results."""
    get_index()
    res = match(
        MatchQuery(name=name, maker_name=maker or None),
        top_n=top_n,
        use_alias_shortcircuit=not no_alias,
    )
    if not res.candidates:
        typer.echo("no candidates")
        raise typer.Exit(code=1)
    for i, c in enumerate(res.candidates, 1):
        typer.echo(f"{i:>2}. {c.confidence:.3f}  #{c.product_id}  {c.search_string}")
    if res.exact_alias_hit:
        typer.echo("(exact alias hit)")
    typer.echo(" ".join(f"{k}={v:.1f}ms" for k, v in res.stage_ms.items()))


@app.command()
def health() -> None:
    """Print engine settings + table sizes."""
    settings = get_settings()
    from dorim_recognition.db.connection import raw_connection
    with raw_connection(autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) AS c FROM {settings.engine_schema}.products")
            products = cur.fetchone()["c"]
            cur.execute(f"SELECT COUNT(*) AS c FROM {settings.engine_schema}.aliases")
            aliases = cur.fetchone()["c"]
            cur.execute(f"SELECT COUNT(*) AS c FROM {settings.engine_schema}.match_logs")
            logs = cur.fetchone()["c"]
    typer.echo(f"db          : {settings.db_host}:{settings.db_port}/{settings.db_name}")
    typer.echo(f"engine schema: {settings.engine_schema}")
    typer.echo(f"products    : {products}")
    typer.echo(f"aliases     : {aliases}")
    typer.echo(f"match_logs  : {logs}")


if __name__ == "__main__":
    app()
