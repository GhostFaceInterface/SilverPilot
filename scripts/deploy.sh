#!/usr/bin/env bash
# ==============================================================================
# SilverPilot VPS Deployment & Automation Orchestrator
# ==============================================================================
# This script automates:
#   1. Local Git Status check and commit/push validation.
#   2. Secure SSH connection verification to `silverpilot-vps`.
#   3. Pulling latest main branch code on VPS.
#   4. Rebuilding Docker containers & running DB Migrations (Alembic).
#   5. Smoke testing all data collectors and quality endpoints.
# ==============================================================================

set -euo pipefail

# --- Color Scheme ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color
BOLD='\033[1m'

# --- Icons ---
ICON_INFO="ℹ️ "
ICON_SUCCESS="✅"
ICON_WARNING="⚠️ "
ICON_ERROR="❌"
ICON_ROCKET="🚀"
ICON_GEAR="⚙️ "
ICON_LOCK="🔒"

# --- Functions ---
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
    printf "${CYAN}${BOLD} %s %s${NC}\n" "$ICON_ROCKET" "$1"
    printf "${CYAN}${BOLD}======================================================================${NC}\n"
}

# --- Command Line Arguments ---
ASSUME_YES=false
COMMIT_MSG="feat: deploy phase 3.6 technical indicator engine live integration and tests"

while [[ $# -gt 0 ]]; do
    case $1 in
        -y|--yes|--non-interactive)
            ASSUME_YES=true
            shift
            ;;
        -m|--message)
            COMMIT_MSG="$2"
            shift 2
            ;;
        *)
            log_error "Unknown argument: $1"
            exit 1
            ;;
    esac
done

# --- Pre-flight Checks ---
header "SILVERPILOT VPS DEPLOYMENT & GIT AUTOMATION"

# 1. SSH Alias Verification
log_info "Verifying SSH connection to alias 'silverpilot-vps'..."
if ssh -q -o ConnectTimeout=5 silverpilot-vps exit; then
    log_success "SSH alias connection verified."
else
    log_error "Failed to connect to SSH alias 'silverpilot-vps'. Please ensure your ~/.ssh/config contains the alias."
    exit 1
fi

# 2. Git Status Check & Automatic Committer
log_info "Checking local Git working directory..."
git_status=$(git status --porcelain)

if [ -n "$git_status" ]; then
    log_warning "Found uncommitted changes in your working directory:"
    git status -s
    
    printf "\n"
    REPLY=""
    commit_msg=""
    if [ "$ASSUME_YES" = true ]; then
        REPLY="y"
        commit_msg="$COMMIT_MSG"
        log_info "Non-interactive mode enabled: Auto-staging, committing and pushing."
    else
        read -p "Would you like to stage, commit and push these changes? (y/n) " -n 1 -r
        printf "\n"
    fi
    
    if [[ ${REPLY:-} =~ ^[Yy]$ ]] || [[ -z "${REPLY:-}" && ${REPLY:-} =~ ^[Yy]$ ]]; then
        # If user didn't auto-accept, prompt for commit message
        if [ "$ASSUME_YES" = false ]; then
            read -p "Enter commit message [Press Enter for default: '$COMMIT_MSG']: " user_msg
            if [ -z "${user_msg:-}" ]; then
                commit_msg="$COMMIT_MSG"
            else
                commit_msg="$user_msg"
            fi
        fi
        
        log_info "Staging all changes (git add .)..."
        git add .
        
        log_info "Committing changes..."
        git commit -m "$commit_msg"
        log_success "Committed successfully."
        
        log_info "Pushing commits to remote repository (origin main)..."
        git push origin main
        log_success "Pushed to origin successfully."
    else
        log_warning "Proceeding with deployment without committing new local changes. VPS will pull whatever is currently pushed."
    fi
else
    log_success "Working directory is clean."
    
    # Check if branch is ahead of remote
    ahead_commits=$(git log @{u}.. 2>/dev/null | wc -l || echo "0")
    if [ "$ahead_commits" -gt 0 ]; then
        log_warning "Local branch is ahead of remote by $ahead_commits commits. Pushing now..."
        git push origin main
        log_success "Pushed ahead commits successfully."
    fi
fi

# --- VPS Deployment Execution ---
header "EXECUTING DEPLOYMENT ON VPS (silverpilot-vps)"

vps_cmd="
set -euo pipefail

# ANSI color codes for remote server
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e \"\${BLUE}[1/5] Pulling latest main branch code...\${NC}\"
cd /opt/silverpilot/SilverPilot
git fetch origin
git pull --ff-only

echo -e \"\${BLUE}[2/5] Building and updating Docker services...\${NC}\"
docker compose --env-file .env.production config >/dev/null
docker compose --env-file .env.production up -d --build

echo -e \"\${BLUE}[3/5] Running Alembic Database migrations...\${NC}\"
docker compose --env-file .env.production run --rm api alembic upgrade head

echo -e \"\${BLUE}[4/5] Executing smoke check on HTTP Server...\${NC}\"
for i in {1..10}; do
    if curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1; then
        break
    fi
    echo -e \"Waiting for HTTP Server to start (attempt \\\$i/10)...\"
    sleep 1
done
curl -fsS http://127.0.0.1:8000/health



echo -e \"\${BLUE}[4.5/5] Running E2E Strategy & Backtest Verification Pipeline...\${NC}\"
docker compose --env-file .env.production run --rm -v /opt/silverpilot/SilverPilot/scripts:/app/scripts api python scripts/verify_execution_pipeline.py

echo -e \"\${BLUE}[5/5] Running all collector sanity jobs...\${NC}\"
echo \"Running: tcmb-usd-try\"
docker compose --env-file .env.production run --rm api python -m app.collectors.runner --job tcmb-usd-try
echo \"Running: global-xag-usd\"
docker compose --env-file .env.production run --rm api python -m app.collectors.runner --job global-xag-usd
echo \"Running: kuveyt-silver\"
docker compose --env-file .env.production run --rm api python -m app.collectors.runner --job kuveyt-silver
echo \"Running: fed-rss\"
docker compose --env-file .env.production run --rm api python -m app.collectors.runner --job fed-rss
echo \"Running: fred-macro\"
docker compose --env-file .env.production run --rm api python -m app.collectors.runner --job fred-macro

echo -e \"\${BLUE}Verifying end-to-end Collector health metrics...\${NC}\"
curl -fsS http://127.0.0.1:8000/collectors/health
echo \"\"
curl -fsS http://127.0.0.1:8000/collectors/quality
echo \"\"
curl -fsS http://127.0.0.1:8000/collectors/validation-gate
echo \"\"

echo -e \"\${GREEN}🎉 Remote deployment smoke check succeeded!\${NC}\"
"

log_info "Connecting to silverpilot-vps and executing deploy instructions..."
if ssh -t silverpilot-vps "$vps_cmd"; then
    header "DEPLOYMENT SUCCESSFUL"
    log_success "SilverPilot has been successfully committed, pushed, deployed and validated on the VPS! 🚀"
else
    header "DEPLOYMENT FAILED"
    log_error "Something went wrong during remote VPS execution. Please review the logs above."
    exit 1
fi
