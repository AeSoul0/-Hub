# Sviluppo: contribuire e testare

Come cambiare lo schema, la qualità del codice, i test e le valutazioni degli agenti.

## Contributing

ÆHub is a personal project; changes go through pull requests on `main`, one per milestone, merged by hand when CI is green.

### Changing the schema

Since D1 (ADR-031) Alembic is the only source of the schema. At every start the API runs `alembic upgrade head` (Docker, `make demo` and the desktop app alike), so an update keeps memory, runs and audit. A database built before D1 by the old `create_all` is recognised, gets the tables it lacks and is marked at the baseline, without losing a row.

Every change to a model in `backend/app/domain/models/` is a new revision; no more separate tables to get around `create_all`:

```bash
cd backend
alembic revision --autogenerate -m "memory: add the expiry date"
```

Read the generated file before committing it: autogenerate does not see everything (data moves, expression indexes, extensions). Then check that the models and the revisions agree:

```bash
alembic upgrade head
alembic check
```

All three commands use `POSTGRES_URL`. In CI, `tests/database/test_migrations.py` builds a database from scratch and one with the old `create_all`, and fails when a model changed without a revision.

### Code quality

Backend:

```bash
cd backend
ruff check .
```

Ruff runs with `BLE001` (R1): a blind `except Exception` needs a reason in its `noqa` comment and, unless it re-raises or reports the error, a log line.

Frontend:

```bash
cd frontend
npm run lint
npm run format
```

Every source file starts with an `@file <path>` / `@description …` header, checked in CI:

```bash
python scripts/check_headers.py
```

---

## Testing

Run the backend tests and the evaluation gate locally:

```bash
cd backend && python -m pytest ../tests -q && cd ..
make eval
```

### Unit and integration tests

The backend tests are in `tests/` (pytest; most need PostgreSQL with pgvector at `POSTGRES_URL`). They cover:
* **Agent engine:** tool loop, human approval and resume, guardrails, budget and limits, routing and failover, the Pydantic AI adapter, Context Manager and memory.
* **Security:** SSRF, path traversal, secret redaction, the sandbox, the session and origin checks.
* **API surface:** the exact list of HTTP and WebSocket routes (`tests/security/test_api_surface.py`).
* **Frontend and backend agree:** every address the frontend calls is a real route with the right method (`tests/security/test_frontend_api_routes.py`), and every route, setting and variable has its row in `docs/frontend-coverage.md` (`tests/security/test_frontend_coverage.py`).
* **Database:** the Alembic revisions build the schema from scratch and upgrade an old database (`tests/database/`).
* **Desktop:** the sidecar and, with `AEHUB_BROWSER_SMOKE=1`, a Playwright run of the static frontend in Chromium (`tests/desktop/`).

The frontend has component and hook tests (Vitest, Testing Library, jsdom) in `frontend/tests/`:

```bash
cd frontend && npm test && npm run lint
```

### Agent evaluations

`evals/run_evals.py` runs the cases in `backend/app/evaluation/dataset.json` through the real agent engine (planner loop, Tool Gateway, guardrails, approvals, Critic, Context Manager, memory). By default the model is scripted and the tools are deterministic, so the suite runs offline in seconds and costs nothing. `--live` uses the configured models instead.

The dataset covers successful tasks, retries after tool failures, tool selection, hallucination (answers must be grounded in tool output), human approval of HIGH-risk tools, prompt injection and secret leaks, cross-session memory, long context (50 tool calls under budget) and budget limits.

Each run reports the metrics of the spec (6.5): `success_rate`, `tool_accuracy`, `hallucination_rate`, `reliability`, `security_pass_rate`, `mean_cost` and latency. The release gate fails when:

* any security case fails (`security_pass_rate` must be 100%);
* any other metric is worse than `evals/baseline.json`, or mean cost grows by more than 10%.

```bash
make eval            # check against evals/baseline.json
make eval-baseline   # re-record the baseline after an intended change
```

CI runs the same gate on every push and pull request and uploads `eval-report.json`. It also runs `pip-audit`, `bandit`, Trivy and TruffleHog, checks the Compose file and builds both images. Third-party actions are pinned to commit SHAs.


---
