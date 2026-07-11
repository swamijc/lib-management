#!/usr/bin/env bash
# =============================================================================
#  setup.sh — SDK Management Application — one-shot bootstrap
#
#  Usage:
#    chmod +x setup.sh
#    ./setup.sh          # Full setup + start all services
#    ./setup.sh --no-start   # Setup only, do NOT start services
#    ./setup.sh --reset  # Drop DB + re-setup (fresh slate)
#    ./setup.sh --service api-gateway
#    ./setup.sh --service library-data-service,scheduler-service --no-start
#    ./setup.sh --service ui-react --force-deps
# =============================================================================

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── Colour helpers ────────────────────────────────────────────────────────────
RED=$'\033[0;31m'; GREEN=$'\033[0;32m'; YELLOW=$'\033[1;33m'
CYAN=$'\033[0;36m'; BOLD=$'\033[1m'; RESET=$'\033[0m'

step()    { echo -e "\n${BOLD}${CYAN}▶ $*${RESET}"; }
ok()      { echo -e "  ${GREEN}✓${RESET} $*"; }
warn()    { echo -e "  ${YELLOW}⚠${RESET}  $*"; }
err()     { echo -e "  ${RED}✗${RESET} $*"; }
info()    { echo -e "    ${CYAN}↳${RESET} $*"; }
banner()  {
  echo -e "\n${BOLD}${CYAN}╔══════════════════════════════════════════════════════════╗"
  echo -e "║       SDK Management Application — Setup                 ║"
  echo -e "╚══════════════════════════════════════════════════════════╝${RESET}"
}

usage() {
  cat <<'EOF'
Usage:
  ./setup.sh [options]

Options:
  --no-start                  Setup only; do not start/restart services
  --reset                     Remove database and reinitialize
  --service <name|a,b,c|all> Setup only selected services (default: all)
  --force-deps                Reinstall deps even when input hashes are unchanged
  --help                      Show this help

Examples:
  ./setup.sh
  ./setup.sh --service api-gateway --no-start
  ./setup.sh --service library-data-service,scheduler-service
  ./setup.sh --service ui-react --force-deps
EOF
}

ALL_SERVICES=(
  api-gateway
  library-data-service
  scraper-service
  comparison-service
  recommendation-service
  notification-service
  scheduler-service
  ui-service
  ui-react
)

PYTHON_SERVICES=(
  api-gateway
  library-data-service
  scraper-service
  comparison-service
  recommendation-service
  notification-service
  scheduler-service
  ui-service
)

# ── Parse flags ───────────────────────────────────────────────────────────────
AUTO_START=true
RESET_DB=false
FORCE_DEPS=false
SERVICE_SCOPE="all"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-start)
      AUTO_START=false
      shift
      ;;
    --reset)
      RESET_DB=true
      shift
      ;;
    --force-deps)
      FORCE_DEPS=true
      shift
      ;;
    --service)
      SERVICE_SCOPE="${2:-}"
      if [[ -z "$SERVICE_SCOPE" ]]; then
        err "--service requires a value"
        usage
        exit 1
      fi
      shift 2
      ;;
    --service=*)
      SERVICE_SCOPE="${1#*=}"
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      err "Unknown option: $1"
      usage
      exit 1
      ;;
  esac
done

SERVICES_TO_SETUP=()
if [[ "$SERVICE_SCOPE" == "all" ]]; then
  SERVICES_TO_SETUP=("${ALL_SERVICES[@]}")
else
  IFS=',' read -r -a SERVICES_TO_SETUP <<< "$SERVICE_SCOPE"
  for svc in "${SERVICES_TO_SETUP[@]}"; do
    valid=false
    for known in "${ALL_SERVICES[@]}"; do
      if [[ "$svc" == "$known" ]]; then
        valid=true
        break
      fi
    done
    if [[ "$valid" != "true" ]]; then
      err "Unknown service in --service: $svc"
      usage
      exit 1
    fi
  done
fi

contains_service() {
  local needle="$1"
  for svc in "${SERVICES_TO_SETUP[@]}"; do
    if [[ "$svc" == "$needle" ]]; then
      return 0
    fi
  done
  return 1
}

SELECTED_PYTHON_SERVICES=()
for svc in "${PYTHON_SERVICES[@]}"; do
  if contains_service "$svc"; then
    SELECTED_PYTHON_SERVICES+=("$svc")
  fi
done

banner
info "Service scope: ${SERVICE_SCOPE}"

# =============================================================================
# STEP 1 — Prerequisites check
# =============================================================================
step "1/7  Checking prerequisites"

# Python 3.11+
if ! command -v python3 &>/dev/null; then
  err "python3 not found. Install Python 3.11+ and re-run."
  exit 1
fi
PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PY_MAJOR=$(echo "$PY_VER" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VER" | cut -d. -f2)
if (( PY_MAJOR < 3 || (PY_MAJOR == 3 && PY_MINOR < 11) )); then
  err "Python $PY_VER found. Python 3.11+ is required."
  exit 1
fi
ok "Python $PY_VER"

# pip
if ! python3 -m pip --version &>/dev/null; then
  err "pip not found. Run: python3 -m ensurepip --upgrade"
  exit 1
fi
ok "pip $(python3 -m pip --version | awk '{print $2}')"

# packaging (needed by recommendation + comparison service)
if ! python3 -c "import packaging" &>/dev/null; then
  warn "packaging not yet installed — will be installed below"
fi

# Node.js 18+
if ! command -v node &>/dev/null; then
  err "node not found. Install Node.js 18+ (https://nodejs.org) and re-run."
  exit 1
fi
NODE_VER=$(node --version | sed 's/v//')
NODE_MAJOR=$(echo "$NODE_VER" | cut -d. -f1)
if (( NODE_MAJOR < 18 )); then
  err "Node.js $NODE_VER found. Node.js 18+ is required."
  exit 1
fi
ok "Node.js $NODE_VER"

# npm
if ! command -v npm &>/dev/null; then
  err "npm not found. It should ship with Node.js."
  exit 1
fi
ok "npm $(npm --version)"

# =============================================================================
# STEP 2 — Environment file
# =============================================================================
step "2/7  Environment configuration"

if [[ ! -f ".env" ]]; then
  if [[ -f ".env.example" ]]; then
    cp .env.example .env
    ok "Created .env from .env.example"
    warn "Review .env and update INTERNAL_SERVICE_KEY / JWT_SECRET_KEY before production use."
  else
    warn ".env.example not found — creating minimal .env"
    cat > .env << 'ENVEOF'
# Auto-generated by setup.sh — review before production use
INTERNAL_SERVICE_KEY=dev-internal-key-local
JWT_SECRET_KEY=dev-jwt-secret-local
DEFAULT_ADMIN_PASSWORD=admin123
DATABASE_URL=sqlite+aiosqlite:///./db/library_management.db
LIBRARY_DATA_SERVICE_URL=http://localhost:8001
SCRAPER_SERVICE_URL=http://localhost:8002
COMPARISON_SERVICE_URL=http://localhost:8003
RECOMMENDATION_SERVICE_URL=http://localhost:8004
NOTIFICATION_SERVICE_URL=http://localhost:8005
SCHEDULER_SERVICE_URL=http://localhost:8006
API_GATEWAY_URL=http://localhost:8000
SCHEDULE_CRON=0 2 * * *
SCHEDULE_ENABLED=true
ENVEOF
    ok "Created minimal .env"
  fi
else
  ok ".env already exists — skipping"
fi

# =============================================================================
# STEP 3 — Directory structure
# =============================================================================
step "3/7  Creating runtime directories"

mkdir -p run/pids run/logs db
ok "run/pids, run/logs, db"

if [[ "$RESET_DB" == "true" ]]; then
  warn "--reset flag: removing existing database"
  rm -f db/library_management.db
  ok "Database cleared"
fi

# =============================================================================
# STEP 4 — Python dependencies (all 8 services)
# =============================================================================
step "4/7  Installing Python dependencies"

# Collect unique packages across all services to install in one pass
# (avoids redundant pip installs for shared packages like fastapi, uvicorn…)
COMBINED_REQS="$SCRIPT_DIR/run/combined_requirements.txt"
echo "# Auto-generated by setup.sh — do not edit manually" > "$COMBINED_REQS"
echo "# Merged requirements from all Python services" >> "$COMBINED_REQS"
echo "" >> "$COMBINED_REQS"

# Use a temp file to track seen package names (bash 3.2 compatible — no assoc arrays)
SEEN_FILE="$SCRIPT_DIR/run/.seen_pkgs"
: > "$SEEN_FILE"

for svc in "${SELECTED_PYTHON_SERVICES[@]}"; do
  REQ="services/$svc/requirements.txt"
  if [[ ! -f "$REQ" ]]; then
    warn "No requirements.txt for $svc — skipping"
    continue
  fi
  info "Reading  $REQ"
  while IFS= read -r line || [[ -n "$line" ]]; do
    [[ -z "$line" || "$line" =~ ^# ]] && continue
    # Extract bare package name (strip extras, version specifiers, whitespace)
    pkg_key=$(echo "$line" | sed 's/\[.*\]//g; s/[>=<!].*//' | tr '[:upper:]' '[:lower:]' | tr -d ' ')
    if ! grep -qxF "$pkg_key" "$SEEN_FILE" 2>/dev/null; then
      echo "$pkg_key" >> "$SEEN_FILE"
      echo "$line" >> "$COMBINED_REQS"
    fi
  done < "$REQ"
done
rm -f "$SEEN_FILE"

UNIQUE_COUNT=$(grep -c '.' "$COMBINED_REQS" 2>/dev/null || echo 0)
info "Unique packages to install: $((UNIQUE_COUNT - 2))"

PY_REQ_HASH_FILE="$SCRIPT_DIR/run/combined_requirements.sha256"
REQ_HASH=$(shasum -a 256 "$COMBINED_REQS" | awk '{print $1}')
PREV_REQ_HASH=""
if [[ -f "$PY_REQ_HASH_FILE" ]]; then
  PREV_REQ_HASH=$(cat "$PY_REQ_HASH_FILE" 2>/dev/null || true)
fi

if [[ ${#SELECTED_PYTHON_SERVICES[@]} -eq 0 ]]; then
  ok "No Python services selected — skipping Python dependency install"
elif [[ "$FORCE_DEPS" != "true" && -n "$PREV_REQ_HASH" && "$PREV_REQ_HASH" == "$REQ_HASH" ]]; then
  ok "Python dependencies unchanged — skipping pip install (use --force-deps to reinstall)"
else
  echo ""
  echo "  Running: pip install -r run/combined_requirements.txt"
  echo ""

  if python3 -m pip install -r "$COMBINED_REQS" --quiet --no-warn-script-location; then
    echo "$REQ_HASH" > "$PY_REQ_HASH_FILE"
    ok "All Python dependencies installed"
  else
    err "pip install failed. Check run/combined_requirements.txt for conflicts."
    exit 1
  fi
fi

# =============================================================================
# STEP 5 — Node.js dependencies (React UI)
# =============================================================================
step "5/7  Installing Node.js dependencies (ui-react)"

UI_DIR="services/ui-react"
if ! contains_service "ui-react"; then
  ok "ui-react not selected — skipping Node install"
elif [[ ! -f "$UI_DIR/package.json" ]]; then
  warn "services/ui-react/package.json not found — skipping Node install"
else
  cd "$UI_DIR"
  NODE_HASH_FILE="$SCRIPT_DIR/run/ui-react-deps.sha256"
  if [[ -f package-lock.json ]]; then
    NODE_HASH=$(shasum -a 256 package-lock.json package.json | shasum -a 256 | awk '{print $1}')
  else
    NODE_HASH=$(shasum -a 256 package.json | awk '{print $1}')
  fi
  PREV_NODE_HASH=""
  if [[ -f "$NODE_HASH_FILE" ]]; then
    PREV_NODE_HASH=$(cat "$NODE_HASH_FILE" 2>/dev/null || true)
  fi

  if [[ "$FORCE_DEPS" != "true" && -n "$PREV_NODE_HASH" && "$PREV_NODE_HASH" == "$NODE_HASH" && -d node_modules ]]; then
    ok "Node dependencies unchanged — skipping npm install (use --force-deps to reinstall)"
  else
    if [[ -f package-lock.json ]]; then
      info "Running: npm ci"
      if npm ci --silent 2>/dev/null || npm ci; then
        echo "$NODE_HASH" > "$NODE_HASH_FILE"
        ok "Node.js dependencies installed via npm ci"
      else
        err "npm ci failed. Check services/ui-react/package.json / package-lock.json."
        cd "$SCRIPT_DIR"
        exit 1
      fi
    else
      info "Running: npm install"
      if npm install --silent 2>/dev/null || npm install; then
        echo "$NODE_HASH" > "$NODE_HASH_FILE"
        ok "Node.js dependencies installed via npm install"
      else
        err "npm install failed. Check services/ui-react/package.json."
        cd "$SCRIPT_DIR"
        exit 1
      fi
    fi
  fi
  cd "$SCRIPT_DIR"
fi

# =============================================================================
# STEP 6 — Database initialisation
# =============================================================================
step "6/7  Database initialisation"

DB_PATH="db/library_management.db"
if ! contains_service "library-data-service"; then
  ok "library-data-service not selected — skipping DB initialization"
elif [[ -f "$DB_PATH" ]]; then
  DB_SIZE=$(du -h "$DB_PATH" | cut -f1)
  ok "Database already exists ($DB_PATH, $DB_SIZE) — skipping init"
  info "Use  ./setup.sh --reset  to start fresh"
else
  info "Running Alembic migrations to create schema…"
  cd services/library-data-service
  if python3 -m alembic -c ../../migrations/alembic.ini upgrade head 2>/dev/null; then
    ok "Schema created via Alembic"
  else
    warn "Alembic migration skipped (library-data-service will auto-create tables on first start)"
  fi
  cd "$SCRIPT_DIR"
fi

# =============================================================================
# STEP 7 — Summary & optional service start
# =============================================================================
step "7/7  Setup complete"
echo ""
echo -e "  ${GREEN}${BOLD}All dependencies installed successfully.${RESET}"
echo ""
echo -e "  ${BOLD}Installed:${RESET}"
echo -e "    Python  $(python3 --version)"
echo -e "    pip     $(python3 -m pip --version | awk '{print $2}')"
echo -e "    Node    $(node --version)"
echo -e "    npm     $(npm --version)"
echo ""
echo -e "  ${BOLD}Services configured:${RESET}"
echo -e "    api-gateway           → http://localhost:8000"
echo -e "    library-data-service  → http://localhost:8001"
echo -e "    scraper-service       → http://localhost:8002"
echo -e "    comparison-service    → http://localhost:8003"
echo -e "    recommendation-service→ http://localhost:8004"
echo -e "    notification-service  → http://localhost:8005"
echo -e "    scheduler-service     → http://localhost:8006"
echo -e "    ui-service (Streamlit)→ http://localhost:8501"
echo -e "    ui-react (React/Vite) → http://localhost:3000"
echo ""

if [[ "$AUTO_START" == "true" ]]; then
  echo -e "  ${BOLD}Starting selected services…${RESET}"
  echo ""
  if [[ -x "manage.sh" ]]; then
    if [[ "$SERVICE_SCOPE" == "all" ]]; then
      bash manage.sh restart
    else
      for svc in "${SERVICES_TO_SETUP[@]}"; do
        bash manage.sh restart "$svc"
      done
    fi
  else
    chmod +x manage.sh
    if [[ "$SERVICE_SCOPE" == "all" ]]; then
      bash manage.sh restart
    else
      for svc in "${SERVICES_TO_SETUP[@]}"; do
        bash manage.sh restart "$svc"
      done
    fi
  fi
  echo ""
  echo -e "  ${GREEN}${BOLD}✓ Selected services started.${RESET}"
  echo ""
  echo -e "  ${BOLD}Open the app:${RESET}"
  echo -e "    React UI   →  ${CYAN}http://localhost:3000${RESET}"
  echo -e "    API Docs   →  ${CYAN}http://localhost:8000/docs${RESET}"
  echo -e "    Login:  admin / admin123  (change password in Settings)"
else
  echo -e "  ${YELLOW}Services NOT started (--no-start flag).${RESET}"
  if [[ "$SERVICE_SCOPE" == "all" ]]; then
    echo -e "  To start:  ${BOLD}./manage.sh start${RESET}"
  else
    echo -e "  To start selected:  ${BOLD}./manage.sh start <service>${RESET}"
  fi
fi

echo ""
echo -e "  ${BOLD}Other useful commands:${RESET}"
echo -e "    ./manage.sh status          — Show all service PIDs & ports"
echo -e "    ./manage.sh logs <service>  — Tail live logs"
echo -e "    ./manage.sh stop            — Stop all services"
echo -e "    ./setup.sh --reset          — Full reset (clears DB)"
echo ""
