#!/usr/bin/env bash
set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[install]${NC} $*"; }
warn()  { echo -e "${YELLOW}[warn]${NC} $*"; }

# ── .env ──────────────────────────────────────────────────────────────────────
# SECRET_KEY is generated per install rather than copied: it signs session tokens
# and encrypts TOTP secrets, so a value shared across installs is a shared master
# key. The app refuses to start if this is left empty.
gen_secret() {
    python3 -c "import secrets; print(secrets.token_hex(32))"
}

if [ ! -f .env ]; then
    cp .env.example .env
    KEY="$(gen_secret)"
    # Portable in-place edit (BSD sed on macOS needs the empty -i argument).
    sed -i.bak "s|^SECRET_KEY=.*|SECRET_KEY=${KEY}|" .env && rm -f .env.bak
    info "Created .env from .env.example with a freshly generated SECRET_KEY"
    warn "Set DATABASE_URL before running in production"
else
    info ".env already exists — skipping"
    if grep -qE '^SECRET_KEY=\s*$|^SECRET_KEY=thorotest-dev-secret-change-in-production\s*$' .env; then
        KEY="$(gen_secret)"
        sed -i.bak "s|^SECRET_KEY=.*|SECRET_KEY=${KEY}|" .env && rm -f .env.bak
        warn "SECRET_KEY in .env was empty or the shipped placeholder — generated a new one"
    fi
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
    info "Building frontend (frontend/dist)..."
    npm run build
    info "Installing Playwright browsers..."
    npx playwright install --with-deps chromium
else
    warn "Node not found — cannot build the frontend. Install Node 20+ and run 'npm install && npm run build', or deploy with Docker (builds it for you)."
fi

echo ""
info "Setup complete."
echo ""
echo "  Start development server:  make dev"
echo "  Start with Docker:         make docker-up"
echo "  Run tests:                 make test"
echo ""
