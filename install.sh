#!/usr/bin/env bash
set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[install]${NC} $*"; }
warn()  { echo -e "${YELLOW}[warn]${NC} $*"; }

# ── .env ──────────────────────────────────────────────────────────────────────
if [ ! -f .env ]; then
    cp .env.example .env
    info "Created .env from .env.example"
    warn "Edit .env and set DATABASE_URL + SECRET_KEY before running in production"
else
    info ".env already exists — skipping"
fi

# ── Python venv ───────────────────────────────────────────────────────────────
if [ ! -d venv ]; then
    info "Creating Python virtual environment..."
    python3 -m venv venv
fi

info "Installing Python dependencies..."
./venv/bin/pip install --upgrade pip --quiet
./venv/bin/pip install -r requirements.txt --quiet

# ── Node + Playwright ─────────────────────────────────────────────────────────
if command -v node &>/dev/null; then
    info "Installing Node dependencies..."
    npm install --silent
    info "Installing Playwright browsers..."
    npx playwright install --with-deps chromium
else
    warn "Node not found — skipping Playwright install (not needed for production)"
fi

echo ""
info "Setup complete."
echo ""
echo "  Start development server:  make dev"
echo "  Start with Docker:         make docker-up"
echo "  Run tests:                 make test"
echo ""
