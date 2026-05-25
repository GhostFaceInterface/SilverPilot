#!/usr/bin/env bash
# ==============================================================================
# SilverPilot VPS Smoke Test & Validation Orchestrator
# ==============================================================================
# This script executes inside the VPS context to validate deployment state,
# run database migrations, test collectors, and verify E2E signal integrity.
# ==============================================================================

set -euo pipefail

# --- Color Scheme ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color
BOLD='\033[1m'

# --- Icons ---
ICON_INFO="ℹ️ "
ICON_SUCCESS="✅"
ICON_WARNING="⚠️ "
ICON_ERROR="❌"
ICON_GEAR="⚙️ "

# --- Logger Functions ---
log_info() {
    printf "${BLUE}${ICON_INFO}${NC}%s\n" "$1"
}

log_success() {
    printf "${GREEN}${ICON_SUCCESS}${NC}%s\n" "$1"
}

log_warning() {
    printf "${YELLOW}${ICON_WARNING}${NC}%s\n" "$1"
}

log_error() {
    printf "${RED}${ICON_ERROR}${NC}%s\n" "$1"
}

header() {
    printf "\n${CYAN}${BOLD}======================================================================${NC}\n"
    printf "${CYAN}${BOLD} %s %s${NC}\n" "$ICON_GEAR" "$1"
    printf "${CYAN}${BOLD}======================================================================${NC}\n"
}

header "SILVERPILOT VPS SMOKE TEST INTEGRITY SUITE"

# 1. Configuration Validation
log_info "1/7 Validating Docker Compose configuration..."
if docker compose --env-file .env.production config >/dev/null; then
    log_success "Docker Compose configuration is valid."
else
    log_error "Invalid Docker Compose configuration."
    exit 1
fi

# 2. Services Update
log_info "2/7 Rebuilding and starting Docker services (dashboard + collector profiles)..."
docker compose --env-file .env.production --profile collector --profile dashboard up -d --build
log_success "Docker services updated and started in background."

# 3. Database Migrations
log_info "3/7 Running Alembic database migrations..."
if docker compose --env-file .env.production run --rm api alembic upgrade head; then
    log_success "Database migrations executed successfully."
else
    log_error "Alembic migrations failed."
    exit 1
fi

# 4. HTTP Server Health Check (Retry Loop)
log_info "4/7 Verifying HTTP Server availability..."
server_online=false
for i in {1..10}; do
    if curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1; then
        server_online=true
        break
    fi
    log_warning "Waiting for HTTP Server to start (attempt $i/10)..."
    sleep 1
done

if [ "$server_online" = true ]; then
    log_success "HTTP Server is ONLINE."
    curl -fsS http://127.0.0.1:8000/health
    printf "\n"
else
    log_error "HTTP Server failed to start after 10 attempts."
    exit 1
fi

# 5. E2E Strategy & Backtest Verification
log_info "5/7 Running E2E Strategy & Backtest Verification Pipeline..."
# Dynamic volume mapping using current directory paths
if docker compose --env-file .env.production run --rm -v "$(pwd)/scripts:/app/scripts" api python scripts/verify_execution_pipeline.py; then
    log_success "E2E verification pipeline completed successfully."
else
    log_error "E2E verification pipeline failed."
    exit 1
fi

# 6. Data Collectors Execution
log_info "6/7 Running all collector sanity jobs..."

log_info "Running collector: tcmb-usd-try"
if docker compose --env-file .env.production run --rm api python -m app.collectors.runner --job tcmb-usd-try; then
    log_success "tcmb-usd-try collector succeeded."
else
    log_error "tcmb-usd-try collector failed."
    exit 1
fi

log_info "Running collector: global-xag-usd"
# Soft failure: allowed to fail during weekends/holidays or off-market hours
if docker compose --env-file .env.production run --rm api python -m app.collectors.runner --job global-xag-usd; then
    log_success "global-xag-usd collector succeeded."
else
    log_warning "global-xag-usd collector failed/returned stale data (normal during weekends/holidays or off-market hours)."
fi

log_info "Running collector: kuveyt-silver"
if docker compose --env-file .env.production run --rm api python -m app.collectors.runner --job kuveyt-silver; then
    log_success "kuveyt-silver collector succeeded."
else
    log_error "kuveyt-silver collector failed."
    exit 1
fi

log_info "Running collector: fed-rss"
if docker compose --env-file .env.production run --rm api python -m app.collectors.runner --job fed-rss; then
    log_success "fed-rss collector succeeded."
else
    log_error "fed-rss collector failed."
    exit 1
fi

log_info "Running collector: fred-macro"
if docker compose --env-file .env.production run --rm api python -m app.collectors.runner --job fred-macro; then
    log_success "fred-macro collector succeeded."
else
    log_error "fred-macro collector failed."
    exit 1
fi

# 7. End-to-End Metrics & Freshness Verification
log_info "7/7 Fetching collector health, quality and validation gate diagnostics..."

printf "\n[Collector Health]\n"
curl -fsS http://127.0.0.1:8000/collectors/health
printf "\n"

printf "\n[Collector Quality]\n"
curl -fsS http://127.0.0.1:8000/collectors/quality
printf "\n"

printf "\n[Validation Gate]\n"
curl -fsS http://127.0.0.1:8000/collectors/validation-gate
printf "\n"

header "🎉 REMOTE VPS DEPLOYMENT SMOKE CHECK SUCCESSFUL! 🎉"
