"""
@file evals/run_evals.py
@description Command line entry of the agent evaluation suite (roadmap M7).

    python evals/run_evals.py                          offline run, report only
    python evals/run_evals.py --baseline evals/baseline.json
                                                       release gate (CI)
    python evals/run_evals.py --baseline evals/baseline.json --update-baseline
                                                       record a new baseline
    python evals/run_evals.py --live                   use the configured models

The suite itself lives in backend/app/evaluation. The offline run needs no
database, network or API key: the engine runs on an in-memory database and
the model is scripted.
"""

from __future__ import annotations

import os
import secrets
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"


def main() -> int:
    # Settings() fails closed without these. The offline suite never talks to
    # PostgreSQL, Redis or a model provider, so throwaway values are enough;
    # values already in the environment (or a --live configuration) win.
    if "--live" not in sys.argv:
        os.environ.setdefault("AEHUB_SECRET_KEY", secrets.token_urlsafe(32))
        os.environ.setdefault("GROQ_API_KEY", "offline-eval")
        os.environ.setdefault("POSTGRES_URL", "postgresql://offline-eval@localhost:5432/offline-eval")
        os.environ.setdefault("AEHUB_CHECKER_MODEL", "eval-critic")
        os.environ.setdefault("AEHUB_TELEMETRY_CONSOLE", "0")

    sys.path.insert(0, str(BACKEND))

    from app.evaluation.engine import run

    return run(sys.argv[1:])


if __name__ == "__main__":
    sys.exit(main())
