#!/usr/bin/env bash
# @file scripts/codespace.sh
# @description ÆHub in GitHub Codespaces (or any Ubuntu 24.04 machine):
# PostgreSQL with pgvector, the backend in a virtual environment, and the
# pages as a static export served by the backend itself, so one port (3002)
# and one HTTPS address are enough.
#
#   bash scripts/codespace.sh install   # once: packages, Python, the pages
#   bash scripts/codespace.sh start     # start (again) and print the address
#   bash scripts/codespace.sh stop | status | key | logs | build
#
# Keys come from the environment (Codespaces secrets), never from a file in
# the repository. Data stays in ~/.aehub (database password, login key,
# working folder, voice models, log).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA="${AEHUB_HOME:-$HOME/.aehub}"
VENV="$DATA/venv"
PORT="${AEHUB_PORT:-3002}"
DB_NAME="aehub_db"
DB_USER="aehub_user"

as_root() { if [ "$(id -u)" = 0 ]; then "$@"; else sudo "$@"; fi; }
# Through root: a codespace's sudo lets its user become root without a
# password, but not other users (sudo -u postgres would ask for one).
as_postgres() { as_root runuser -u postgres -- "$@"; }
say() { printf '\n\033[1;36m[ÆHub]\033[0m %s\n' "$*"; }

secret_file() {
    # A random value kept in ~/.aehub, made once.
    local file="$DATA/$1"
    if [ ! -s "$file" ]; then
        mkdir -p "$DATA"
        (umask 077 && python3 -c 'import secrets; print(secrets.token_urlsafe(32))' > "$file")
    fi
    cat "$file"
}

login_key() {
    if [ -n "${AEHUB_SECRET_KEY:-}" ]; then echo "$AEHUB_SECRET_KEY"; else secret_file login-key; fi
}

address() {
    if [ -n "${CODESPACE_NAME:-}" ] && [ -n "${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN:-}" ]; then
        echo "https://${CODESPACE_NAME}-${PORT}.${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN}"
    else
        echo "http://localhost:${PORT}"
    fi
}

build_pages() {
    say "Building the pages (static export)…"
    (cd "$ROOT/frontend" && npm ci --no-audit --no-fund && AEHUB_STATIC_EXPORT=1 npm run build)
}

install() {
    say "Installing PostgreSQL with pgvector and Python…"
    as_root apt-get update -q
    as_root env DEBIAN_FRONTEND=noninteractive apt-get install -y -q \
        postgresql-16 postgresql-16-pgvector python3-venv python3-dev build-essential
    mkdir -p "$DATA"
    if [ ! -x "$VENV/bin/python" ]; then
        python3 -m venv "$VENV"
    fi
    say "Installing the backend's Python packages (a few minutes)…"
    "$VENV/bin/pip" install -q --upgrade pip
    "$VENV/bin/pip" install -q -r "$ROOT/backend/requirements.txt"
    build_pages
    say "Installed. Start with: bash scripts/codespace.sh start"
}

start_database() {
    if ! pg_isready -q -h 127.0.0.1 -p 5432; then
        as_root service postgresql start >/dev/null
        for _ in $(seq 1 30); do pg_isready -q -h 127.0.0.1 -p 5432 && break; sleep 1; done
    fi
    local password
    password="$(secret_file db-password)"
    # Role and database, made once; the password is the one in ~/.aehub.
    as_postgres psql -q -v ON_ERROR_STOP=1 -v user="$DB_USER" -v pass="$password" <<'SQL'
SELECT format('CREATE ROLE %I LOGIN', :'user') WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'user')\gexec
ALTER ROLE :"user" WITH LOGIN PASSWORD :'pass';
SQL
    as_postgres psql -q -v ON_ERROR_STOP=1 -v user="$DB_USER" -v db="$DB_NAME" <<'SQL'
SELECT format('CREATE DATABASE %I OWNER %I', :'db', :'user') WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = :'db')\gexec
SQL
    as_postgres psql -q -d "$DB_NAME" -c "SET client_min_messages = warning; CREATE EXTENSION IF NOT EXISTS vector" >/dev/null
}

stop() {
    if [ -s "$DATA/backend.pid" ] && kill -0 "$(cat "$DATA/backend.pid")" 2>/dev/null; then
        kill "$(cat "$DATA/backend.pid")"
        rm -f "$DATA/backend.pid"
        say "Stopped."
    fi
}

start() {
    if [ ! -x "$VENV/bin/python" ] || [ ! -d "$ROOT/frontend/out" ]; then
        install
    fi
    start_database
    stop >/dev/null 2>&1 || true
    mkdir -p "$DATA/workspace" "$DATA/voice"

    local url host password key
    url="$(address)"
    host="${url#*://}"
    password="$(secret_file db-password)"
    key="$(login_key)"

    # The models of each role, from the keys this codespace has (unless set).
    local chosen roles prices
    chosen="$(python3 "$ROOT/scripts/codespace_models.py" || true)"
    roles="$(printf '%s' "$chosen" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(json.dumps(d["roles"]) if d.get("roles") else "")' 2>/dev/null || true)"
    prices="$(printf '%s' "$chosen" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(json.dumps(d["prices"]) if d.get("prices") else "")' 2>/dev/null || true)"
    if [ -z "${AEHUB_MODEL_ROLES:-}" ] && [ -n "$roles" ]; then
        export AEHUB_MODEL_ROLES="$roles"
        say "Models of each role (change them in IMPOSTAZIONI):"
        printf '%s' "$roles" | python3 -c 'import json, sys
for role, models in json.load(sys.stdin).items(): print("  %-12s %s" % (role, " -> ".join(models)))'
    elif [ -z "${AEHUB_MODEL_ROLES:-}" ]; then
        say "No model chosen: add ANTHROPIC_API_KEY, GEMINI_API_KEY or OPENROUTER_API_KEY as Codespaces secrets (or check the ones above), then restart; or pick the models in IMPOSTAZIONI."
    fi
    if [ -z "${AEHUB_MODEL_PRICES:-}" ] && [ -n "$prices" ]; then
        export AEHUB_MODEL_PRICES="$prices"
    fi

    say "Starting ÆHub…"
    (
        cd "$ROOT/backend"
        export AEHUB_SECRET_KEY="$key"
        export POSTGRES_URL="postgresql://${DB_USER}:${password}@127.0.0.1:5432/${DB_NAME}"
        export AEHUB_FRONTEND_DIR="$ROOT/frontend/out"
        export AEHUB_EVENT_BUS=memory
        export AEHUB_TELEMETRY_CONSOLE=0
        export AEHUB_ALLOWED_HOSTS="$host"
        export AEHUB_ALLOWED_ORIGINS="$url,http://localhost:${PORT}"
        export AEHUB_ALLOWED_DIRS="${AEHUB_ALLOWED_DIRS:-$DATA/workspace}"
        export AEHUB_VOICE_MODELS_DIR="$DATA/voice"
        nohup "$VENV/bin/python" -m uvicorn main:app --host 127.0.0.1 --port "$PORT" \
            > "$DATA/backend.log" 2>&1 &
        echo $! > "$DATA/backend.pid"
    )

    for _ in $(seq 1 90); do
        if curl -fsS -o /dev/null "http://127.0.0.1:${PORT}/health" 2>/dev/null; then
            say "ÆHub is running."
            echo "  Address:   $url/control-plane/"
            echo "  Login key: $key"
            echo "  (again: bash scripts/codespace.sh key; log: bash scripts/codespace.sh logs)"
            return 0
        fi
        sleep 1
    done
    say "The backend did not start; the end of its log:"
    tail -n 40 "$DATA/backend.log"
    return 1
}

case "${1:-start}" in
    install) install ;;
    start) start ;;
    stop) stop ;;
    build) build_pages ;;
    key) login_key ;;
    logs) tail -n 100 -f "$DATA/backend.log" ;;
    status)
        if curl -fsS -o /dev/null "http://127.0.0.1:${PORT}/health" 2>/dev/null; then echo "running: $(address)/control-plane/"; else echo "stopped"; fi
        ;;
    *) echo "usage: bash scripts/codespace.sh [install|start|stop|status|key|logs|build]"; exit 2 ;;
esac
