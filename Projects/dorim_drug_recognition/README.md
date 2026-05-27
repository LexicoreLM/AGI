# Dorim Drug Recognition

Сервис распознавания лекарственных средств: на вход — название и производитель,
на выход — наиболее релевантные товары из каталога с оценкой вероятности.

## Что внутри

```
┌─────────────────────────┐   ┌───────────────────────────┐
│ HTTP API + Jinja2 UI    │   │ Batch xlsx/csv processor  │
└────────────┬────────────┘   └──────────────┬────────────┘
             │                               │
             ▼                               ▼
       ┌────────────────────────────────────────────┐
       │  Hybrid matching engine                    │
       │   stage 0 — alias short-circuit (md5)      │
       │   stage 1 — pg_trgm GiST KNN (~30 ms)      │
       │   stage 2 — rerank (fuzzy+TF-IDF+dose+mfr) │
       └────────────────────────────────────────────┘
                            │
                            ▼
       ┌────────────────────────────────────────────┐
       │  PostgreSQL: recognition_engine.*          │
       │   products  72.5 K       aliases  514 K    │
       │   GiST trigram index on normalized strings │
       │   match_logs (request telemetry)           │
       └────────────────────────────────────────────┘
```

Источник данных — `service_recognition.drugs` (каталог) и `service_recognition.bindings`
(привязки, операторская схема). Сервис не пишет в неё ничего; свои артефакты
держит в схеме `recognition_engine` в той же БД.

## Качество

Оценка на 2000 случайных привязках с отключённым alias short-circuit
(моделирует ситуацию «новая пара (name, maker) не встречалась раньше»):

| metric                      | значение |
|-----------------------------|----------|
| top-1 accuracy              | **73.5 %** |
| top-5 accuracy              | **91.3 %** |
| median latency              | 43 ms |
| p90 latency                 | 56 ms |
| confidence(correct) — mean  | 0.71 |
| confidence(wrong) — mean    | 0.66 |

В продакшене ~30 % входов — повторы и резолвятся stage 0 за 2 ms с confidence 0.99,
поэтому ожидаемый сквозной top-1 ≈ 82 %.

## Быстрый старт

```bash
# 1. зависимости
uv sync

# 2. конфигурация
cp .env.example .env
# отредактируй DORIM_DB_* при необходимости

# 3. миграции + ингест данных
uv run python -m dorim_recognition.cli migrate
uv run python -m dorim_recognition.cli ingest    # ~45 секунд

# 4. запуск сервиса
uv run uvicorn dorim_recognition.api.app:app --reload --port 8000
```

Открой http://localhost:8000 для UI, http://localhost:8000/docs для OpenAPI.

## Использование

### REST API

```bash
curl -s -X POST http://localhost:8000/match \
  -H 'content-type: application/json' \
  -d '{"name":"Найз таб. 100мг №20","maker_name":"Dr.Reddys lab, Индия","top_n":3}' | jq
```

Ответ:
```json
{
  "candidates": [
    {
      "product_id": 10294,
      "search_string": "найз табл. 100 мг блистер №20 dr.reddy's индия",
      "confidence": 0.99,
      "components": {"source": 1.0}
    }
  ],
  "exact_alias_hit": true,
  "stage_ms": {"alias": 2.5}
}
```

### Batch (файлы)

```bash
curl -X POST http://localhost:8000/match/batch \
  -F 'file=@input.xlsx' -F 'top_n=3' \
  -o output.xlsx
```

Колонки (регистр не важен, любой из вариантов):
- название: `name` / `название` / `наименование` / `товар`
- производитель: `maker` / `maker_name` / `производитель`
- контрагент (опц.): `contractor_id`

В выходном xlsx добавляются: `matched_product_id`, `matched_search_string`,
`confidence`, `exact_alias_hit`, `alt_1_*`, …, `alt_N-1_*`.

### CLI

```bash
uv run python -m dorim_recognition.cli health
uv run python -m dorim_recognition.cli search "Долгит крем 150г" --maker "Dolorgiet"
uv run python -m dorim_recognition.cli migrate
uv run python -m dorim_recognition.cli ingest
```

## Структура проекта

```
src/dorim_recognition/
├── api/         FastAPI app, request schemas, batch processor
├── core/        config (pydantic-settings)
├── db/          PG connection, migrations runner, ingest scripts
├── matching/    normalize.py, engine.py — собственно матчинг
├── cli/         typer-based CLI
└── templates/   Jinja2 (index.html)

migrations/      001_init_schema.sql, 002_switch_to_gist.sql
scripts/         evaluate.py, inspect_failures.py
```

## Тюнинг

Все веса гибридного скоринга и параметры пайплайна — в `core/config.py`
(переопределяются через `.env`):

```
DORIM_W_FUZZY=0.40        # rapidfuzz.token_set_ratio
DORIM_W_TFIDF=0.30        # char-ngram TF-IDF cosine
DORIM_W_MAKER=0.20        # fuzzy match по производителю
DORIM_W_DOSAGE=0.10       # совпадение дозировки/кол-ва
DORIM_CANDIDATE_LIMIT=500 # сколько кандидатов брать из pg_trgm в Stage 1
DORIM_LOW_CONFIDENCE_THRESHOLD=0.55  # порог "low confidence" в UI
```

После любого изменения весов — повторить `scripts/evaluate.py`.

## Что можно улучшить дальше

- **Калибровка confidence**: текущая разность 0.71 (correct) vs 0.66 (wrong) даёт
  слабую разделимость. Тренировка логрегрессии на (component_scores) → P(correct).
- **Учёт contractor_id**: разные поставщики используют разные стили написания;
  per-contractor подмодель может улучшить top-1 на 2-3 pp.
- **Sentence-transformer embeddings**: рерэнк через многоязычную модель
  (например, paraphrase-multilingual-MiniLM) поверх top-100 кандидатов.
- **Order-independent alias hash**: сейчас `"Dr.Reddys lab Индия"` и
  `"Индия, Dr.Reddys lab"` дают разные md5. Сортировка токенов уберёт это.
- **Background ingest job**: cron-task для инкрементального обновления aliases
  из новых статусов 200/210.
