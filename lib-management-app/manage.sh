#!/usr/bin/env bash
# =============================================================================
#  manage.sh — SDK Management Application service manager
# =============================================================================
#
#  Usage:
#    ./manage.sh start   [service|all]   Start one or all services
#    ./manage.sh stop    [service|all]   Stop one or all services
#    ./manage.sh restart [service|all]   Restart one or all services
#    ./manage.sh status                  Show status of all services
#    ./manage.sh logs    <service>       Tail live logs (Ctrl+C to exit)
#    ./manage.sh health                  Ping all /health endpoints
#    ./manage.sh help                    Show this help
#
# =============================================================================

set -euo pipefail

# ── Paths ─────────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_ROOT="$SCRIPT_DIR"
SERVICES_DIR="$APP_ROOT/services"
PID_DIR="$APP_ROOT/run/pids"
LOG_DIR="$APP_ROOT/run/logs"

# ── Load .env if present ──────────────────────────────────────────────────────
if [[ -f "$APP_ROOT/.env" ]]; then
  # Export all vars from .env (skip comments and empty lines)
  set -a
  # shellcheck disable=SC1090
  source "$APP_ROOT/.env"
  set +a
fi

# ── Ordered service list (start order = dependency order) ─────────────────────
START_ORDER=(
  library-data-service      # 8001 — data store (no upstream deps)
  scraper-service           # 8002 — version scraper (no upstream deps)
  comparison-service        # 8003 — depends on library-data + scraper
  recommendation-service    # 8004 — depends on comparison
  notification-service      # 8005 — standalone channel service
  scheduler-service         # 8006 — depends on all above
  api-gateway               # 8000 — JWT proxy (depends on all backends)
  ui-service                # 8501 — Streamlit (depends on api-gateway)
  ui-react                  # 3000 — React/Vite UI (depends on api-gateway)
)

# ── Colour helpers ────────────────────────────────────────────────────────────
RED=$'\033[0;31m'; GREEN=$'\033[0;32m'; YELLOW=$'\033[1;33m'
CYAN=$'\033[0;36m'; BOLD=$'\033[1m'; RESET=$'\033[0m'

log_info()    { echo -e "${CYAN}  →${RESET} $*"; }
log_ok()      { echo -e "${GREEN}  ✓${RESET} $*"; }
log_warn()    { echo -e "${YELLOW}  ⚠${RESET} $*"; }
log_error()   { echo -e "${RED}  ✗${RESET} $*"; }
log_section() { echo -e "\n${BOLD}$*${RESET}"; }

# ── Service metadata ──────────────────────────────────────────────────────────

get_port() {
  case $1 in
    library-data-service)   echo 8001 ;;
    scraper-service)        echo 8002 ;;
    comparison-service)     echo 8003 ;;
    recommendation-service) echo 8004 ;;
    notification-service)   echo 8005 ;;
    scheduler-service)      echo 8006 ;;
    api-gateway)            echo 8000 ;;
    ui-service)             echo 8501 ;;
    ui-react)               echo 3000 ;;
    *) echo "" ;;
  esac
}

is_known_service() { [[ -n "$(get_port "$1")" ]]; }

get_start_cmd() {
  local svc=$1 port
  port=$(get_port "$svc")
  case $svc in
    ui-react)
      echo "./node_modules/.bin/vite --host 0.0.0.0 --port $port"
      ;;
    ui-service)
      echo "python3 -m streamlit run src/app.py \
        --server.port=$port \
        --server.address=0.0.0.0 \
        --server.headless=true \
        --browser.gatherUsageStats=false"
      ;;
    *)
      echo "python3 -m uvicorn src.main:app --host 0.0.0.0 --port $port"
      ;;
  esac
}

# ── PID / log file paths ──────────────────────────────────────────────────────
pid_file() { echo "$PID_DIR/$1.pid"; }
log_file() { echo "$LOG_DIR/$1.log"; }

is_running() {
  local f
  f=$(pid_file "$1")
  [[ -f "$f" ]] && kill -0 "$(cat "$f")" 2>/dev/null
}

# ── Apply environment for each service ───────────────────────────────────────
# Called inside a subshell that has already cd'd into the service directory.
apply_service_env() {
  local svc=$1

  # ── Shared across all FastAPI services ──────────────────────────────────────
  export PYTHONPATH="$APP_ROOT"
  export INTERNAL_SERVICE_KEY="${INTERNAL_SERVICE_KEY:-dev-internal-key-change-in-prod}"
  export DEBUG="${DEBUG:-false}"

  # ── Service-specific ─────────────────────────────────────────────────────────
  case "$svc" in
    library-data-service)
      # Always use absolute path derived from APP_ROOT so it works on any machine
      export DATABASE_URL="sqlite+aiosqlite:////${APP_ROOT}/db/library_management.db"
      ;;

    comparison-service)
      export LIBRARY_DATA_SERVICE_URL="${LIBRARY_DATA_SERVICE_URL:-http://localhost:8001}"
      export SCRAPER_SERVICE_URL="${SCRAPER_SERVICE_URL:-http://localhost:8002}"
      ;;

    recommendation-service)
      export LIBRARY_DATA_SERVICE_URL="${LIBRARY_DATA_SERVICE_URL:-http://localhost:8001}"
      export COMPARISON_SERVICE_URL="${COMPARISON_SERVICE_URL:-http://localhost:8003}"
      export LLM_PROVIDER="${LLM_PROVIDER:-}"
      export LLM_MODEL="${LLM_MODEL:-gpt-4o-mini}"
      export LLM_API_KEY="${LLM_API_KEY:-${LLM_KEY:-}}"
      export LLM_API_BASE="${LLM_API_BASE:-}"
      ;;

    notification-service)
      export SMTP_HOST="${SMTP_HOST:-smtp.office365.com}"
      export SMTP_PORT="${SMTP_PORT:-587}"
      export SMTP_USERNAME="${SMTP_USERNAME:-}"
      export SMTP_PASSWORD="${SMTP_PASSWORD:-}"
      export SMTP_FROM_ADDRESS="${SMTP_FROM_ADDRESS:-}"
      export DEFAULT_EMAIL_RECIPIENTS="${DEFAULT_EMAIL_RECIPIENTS:-}"
      export TEAMS_WEBHOOK_URL="${TEAMS_WEBHOOK_URL:-}"
      ;;

    scheduler-service)
      export LIBRARY_DATA_SERVICE_URL="${LIBRARY_DATA_SERVICE_URL:-http://localhost:8001}"
      export SCRAPER_SERVICE_URL="${SCRAPER_SERVICE_URL:-http://localhost:8002}"
      export COMPARISON_SERVICE_URL="${COMPARISON_SERVICE_URL:-http://localhost:8003}"
      export RECOMMENDATION_SERVICE_URL="${RECOMMENDATION_SERVICE_URL:-http://localhost:8004}"
      export NOTIFICATION_SERVICE_URL="${NOTIFICATION_SERVICE_URL:-http://localhost:8005}"
      export SCHEDULE_ENABLED="${SCHEDULE_ENABLED:-true}"
      export SCHEDULE_CRON="${SCHEDULE_CRON:-0 2 * * *}"   # already a string; quotes protect it
      ;;

    api-gateway)
      export DATABASE_URL="sqlite+aiosqlite:////${APP_ROOT}/db/library_management.db"
      export JWT_SECRET_KEY="${JWT_SECRET_KEY:-dev-jwt-secret-change-in-production}"
      export JWT_EXPIRE_MINUTES="${JWT_EXPIRE_MINUTES:-480}"
      export LIBRARY_DATA_SERVICE_URL="${LIBRARY_DATA_SERVICE_URL:-http://localhost:8001}"
      export SCRAPER_SERVICE_URL="${SCRAPER_SERVICE_URL:-http://localhost:8002}"
      export COMPARISON_SERVICE_URL="${COMPARISON_SERVICE_URL:-http://localhost:8003}"
      export RECOMMENDATION_SERVICE_URL="${RECOMMENDATION_SERVICE_URL:-http://localhost:8004}"
      export NOTIFICATION_SERVICE_URL="${NOTIFICATION_SERVICE_URL:-http://localhost:8005}"
      export SCHEDULER_SERVICE_URL="${SCHEDULER_SERVICE_URL:-http://localhost:8006}"
      export DEFAULT_ADMIN_PASSWORD="${DEFAULT_ADMIN_PASSWORD:-changeme}"
      ;;

    ui-service)
      # ui-service does not depend on the shared package
      export PYTHONPATH="$SERVICES_DIR/ui-service"
      export API_GATEWAY_URL="${API_GATEWAY_URL:-http://localhost:8000}"
      ;;
    ui-react)
      # Load nvm if npm is not on PATH
      if ! command -v npm &>/dev/null && [[ -s "$HOME/.nvm/nvm.sh" ]]; then
        export NVM_DIR="$HOME/.nvm"
        # shellcheck source=/dev/null
        \. "$NVM_DIR/nvm.sh"
      fi
      # Auto-install node_modules on first run
      if [[ ! -d node_modules ]]; then npm install --silent; fi
      # Kill any stale process holding port 3000 so Vite always binds to the right port
      local stale_pid
      stale_pid=$(lsof -ti:3000 -n -P 2>/dev/null || true)
      if [[ -n "$stale_pid" ]]; then
        kill "$stale_pid" 2>/dev/null || true
        sleep 1
      fi
      ;;
  esac
}

# =============================================================================
#  Commands
# =============================================================================

# ── start ─────────────────────────────────────────────────────────────────────
start_service() {
  local svc=$1
  local svc_dir="$SERVICES_DIR/$svc"

  if ! [[ -d "$svc_dir" ]]; then
    log_error "Directory not found: $svc_dir"; return 1
  fi

  if is_running "$svc"; then
    log_warn "$svc already running (PID $(cat "$(pid_file "$svc")"))"
    return 0
  fi

  mkdir -p "$PID_DIR" "$LOG_DIR"
  local pid_f log_f cmd
  pid_f=$(pid_file "$svc")
  log_f=$(log_file "$svc")
  cmd=$(get_start_cmd "$svc")

  log_info "Starting ${BOLD}$svc${RESET} on port $(get_port "$svc")..."

  # Launch in background subshell; stdout + stderr go to the log file
  (
    cd "$svc_dir"
    apply_service_env "$svc"
    # shellcheck disable=SC2086
    exec $cmd >> "$log_f" 2>&1
  ) &

  local child_pid=$!
  echo "$child_pid" > "$pid_f"

  # Brief pause then verify the process is still alive
  sleep 1
  if is_running "$svc"; then
    log_ok "$svc started   PID=$child_pid   log=$(basename "$log_f")"
  else
    log_error "$svc failed to start. Last 20 lines of log:"
    echo "──────────────────────────────────────"
    tail -20 "$log_f" 2>/dev/null || true
    echo "──────────────────────────────────────"
    rm -f "$pid_f"
    return 1
  fi
}

# ── stop ──────────────────────────────────────────────────────────────────────
stop_service() {
  local svc=$1
  local pid_f
  pid_f=$(pid_file "$svc")

  if ! is_running "$svc"; then
    log_warn "$svc is not running"
    return 0
  fi

  local pid
  pid=$(cat "$pid_f")
  kill "$pid" 2>/dev/null || true

  # Wait up to 5 s for graceful shutdown
  local waited=0
  while kill -0 "$pid" 2>/dev/null && (( waited < 5 )); do
    sleep 1; (( waited++ ))
  done

  # Force-kill if still alive
  kill -9 "$pid" 2>/dev/null || true
  rm -f "$pid_f"
  log_ok "Stopped $svc (PID $pid)"
}

# ── status ────────────────────────────────────────────────────────────────────
cmd_status() {
  log_section "SDK Management Application — Service Status"
  echo ""
  printf "${BOLD}%-32s %-6s %-10s %-8s${RESET}\n" "SERVICE" "PORT" "STATUS" "PID"
  printf '%0.s─' {1..58}; echo ""

  for svc in "${START_ORDER[@]}"; do
    local port pid_info status_str
    port=$(get_port "$svc")
    if is_running "$svc"; then
      pid_info=$(cat "$(pid_file "$svc")")
      status_str="${GREEN}● running${RESET}"
    else
      pid_info="-"
      status_str="${RED}○ stopped${RESET}"
    fi
    printf "%-32s %-6s " "$svc" "$port"
    printf "${status_str}"
    printf "   %s\n" "$pid_info"
  done
  echo ""
}

# ── logs ──────────────────────────────────────────────────────────────────────
cmd_logs() {
  local svc=$1
  local log_f
  log_f=$(log_file "$svc")

  if ! [[ -f "$log_f" ]]; then
    log_error "No log file yet for $svc  (has the service been started?)"; return 1
  fi

  echo -e "${CYAN}=== Logs: $svc  (Ctrl+C to exit) ===${RESET}"
  tail -f "$log_f"
}

# ── health ────────────────────────────────────────────────────────────────────
cmd_health() {
  log_section "SDK Management Application — Health Check"
  echo ""

  local all_ok=true

  for svc in "${START_ORDER[@]}"; do
    local port url http_code
    port=$(get_port "$svc")

    # Streamlit / React use different health paths
    if [[ "$svc" == "ui-service" ]]; then
      url="http://localhost:$port/_stcore/health"
    elif [[ "$svc" == "ui-react" ]]; then
      url="http://localhost:$port/"
    else
      url="http://localhost:$port/health"
    fi

    if http_code=$(curl -sf -o /dev/null -w "%{http_code}" --max-time 3 "$url" 2>/dev/null) \
       && [[ "$http_code" == "200" ]]; then
      log_ok "$(printf '%-32s' "$svc")  $url"
    else
      log_error "$(printf '%-32s' "$svc")  $url  (HTTP ${http_code:-timeout})"
      all_ok=false
    fi
  done

  echo ""
  if $all_ok; then
    log_ok "All services healthy"
  else
    log_warn "One or more services are not responding"
  fi
  echo ""
}

# ── help ──────────────────────────────────────────────────────────────────────
cmd_help() {
  cat <<EOF

${BOLD}SDK Management Application — Service Manager${RESET}

${BOLD}USAGE${RESET}
  ./manage.sh <command> [service|all]

${BOLD}COMMANDS${RESET}
  start   [service|all]   Start one or all services (default: all)
  stop    [service|all]   Stop one or all services  (default: all)
  restart [service|all]   Restart one or all services
  status                  Show live status of every service
  logs    <service>       Tail live log output (Ctrl+C to exit)
  health                  Ping each service /health endpoint via curl
  help                    Show this message

${BOLD}SERVICES${RESET}
  library-data-service    8001  Library CRUD + version history  (SQLite/PG)
  scraper-service         8002  Version scraper  (Maven/CocoaPods/SPM/GitHub)
  comparison-service      8003  Semver comparison engine
  recommendation-service  8004  Rule-based + LLM upgrade advice
  notification-service    8005  Email (SMTP) + Teams webhook
  scheduler-service       8006  APScheduler pipeline runner
  api-gateway             8000  JWT authentication + reverse proxy
  ui-service              8501  Streamlit dashboard
  ui-react                3000  React/Vite dashboard

${BOLD}ENVIRONMENT  (.env file or shell export)${RESET}
  # ── Required in production ──────────────────────────────────────────────
  INTERNAL_SERVICE_KEY    Shared service-to-service secret (all FastAPI svcs)
  JWT_SECRET_KEY          JWT signing secret  (api-gateway)

  # ── Database ─────────────────────────────────────────────────────────────
  DATABASE_URL            SQLAlchemy URL  (default: SQLite ./db/*.db)

  # ── Optional integrations ────────────────────────────────────────────────
  LLM_PROVIDER            litellm provider key  e.g. openai | azure | ollama
  LLM_MODEL               Model name            e.g. gpt-4o-mini
  LLM_API_KEY             LLM API key
  LLM_API_BASE            Azure / Ollama API base URL

  SMTP_HOST               SMTP server   (notification-service)
  SMTP_PORT               SMTP port     (default 587)
  SMTP_USERNAME           SMTP login
  SMTP_PASSWORD           SMTP password
  SMTP_FROM_ADDRESS       Sender address
  DEFAULT_EMAIL_RECIPIENTS  Comma-separated recipients
  TEAMS_WEBHOOK_URL       MS Teams incoming webhook URL

  SCHEDULE_CRON           Cron expression  (default: "0 2 * * *")
  SCHEDULE_ENABLED        true/false       (default: true)

  DEFAULT_ADMIN_PASSWORD  First-run admin password  (api-gateway)
  API_GATEWAY_URL         Gateway URL seen by the UI (default: http://localhost:8000)

${BOLD}EXAMPLES${RESET}
  ./manage.sh start                         # start all 9 services
  ./manage.sh start api-gateway             # start one service
  ./manage.sh stop  scheduler-service       # stop one service
  ./manage.sh restart ui-service            # restart one service
  ./manage.sh restart all                   # rolling restart
  ./manage.sh status                        # live status table
  ./manage.sh logs  scraper-service         # tail scraper logs
  ./manage.sh health                        # ping all /health endpoints

${BOLD}RUNTIME FILES${RESET}
  PID files  →  $APP_ROOT/run/pids/<service>.pid
  Log files  →  $APP_ROOT/run/logs/<service>.log

EOF
}

# =============================================================================
#  Main dispatch
# =============================================================================

COMMAND="${1:-help}"
TARGET="${2:-all}"

case "$COMMAND" in
  start)
    if [[ "$TARGET" == "all" ]]; then
      log_section "Starting all services..."
      for svc in "${START_ORDER[@]}"; do start_service "$svc" || true; done
      echo ""
      cmd_status
    else
      is_known_service "$TARGET" || { log_error "Unknown service: $TARGET"; cmd_help; exit 1; }
      start_service "$TARGET"
    fi
    ;;

  stop)
    if [[ "$TARGET" == "all" ]]; then
      log_section "Stopping all services (reverse order)..."
      for (( i=${#START_ORDER[@]}-1; i>=0; i-- )); do
        stop_service "${START_ORDER[$i]}"
      done
      echo ""
    else
      is_known_service "$TARGET" || { log_error "Unknown service: $TARGET"; cmd_help; exit 1; }
      stop_service "$TARGET"
    fi
    ;;

  restart)
    if [[ "$TARGET" == "all" ]]; then
      log_section "Restarting all services..."
      for (( i=${#START_ORDER[@]}-1; i>=0; i-- )); do
        stop_service "${START_ORDER[$i]}"
      done
      sleep 1
      for svc in "${START_ORDER[@]}"; do start_service "$svc" || true; done
      echo ""
      cmd_status
    else
      is_known_service "$TARGET" || { log_error "Unknown service: $TARGET"; cmd_help; exit 1; }
      log_section "Restarting ${TARGET}..."
      stop_service "$TARGET"
      sleep 1
      start_service "$TARGET"
    fi
    ;;

  status)
    cmd_status
    ;;

  logs)
    if [[ "$TARGET" == "all" ]]; then
      log_error "Specify a service name:  ./manage.sh logs <service>"; exit 1
    fi
    is_known_service "$TARGET" || { log_error "Unknown service: $TARGET"; exit 1; }
    cmd_logs "$TARGET"
    ;;

  health)
    cmd_health
    ;;

  help|--help|-h)
    cmd_help
    ;;

  *)
    log_error "Unknown command: '$COMMAND'"
    cmd_help
    exit 1
    ;;
esac
