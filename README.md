# Rup-Split

Free, self-hosted expense splitting app. Track shared expenses across groups, split costs equally/by exact amounts/by percentage, simplify debts, and settle up. A Splitwise alternative with no paywalls.

## Features

- **Groups** — Create groups (trip, home, couple), invite via shareable link
- **Expenses** — Add expenses with 3 split types: equal, exact amounts, percentage
- **Multi-currency** — Per-expense currency selector (INR, USD, EUR, GBP, AED, JPY, CAD, AUD)
- **Debt simplification** — Minimizes number of transactions needed to settle up
- **Friends** — Search users by email, send/accept/reject requests, add friends directly to groups
- **Settlements** — Record payments, track settlement history
- **Balances** — Real-time derived balances (never cached, always accurate)
- **Dashboard** — Cross-group balance overview

## Tech Stack

- **Backend:** Python 3.11+, FastAPI, SQLAlchemy 2.0 (async)
- **Frontend:** Jinja2 + HTMX + Tailwind CSS + DaisyUI
- **Database:** SQLite (dev) / PostgreSQL (prod)
- **Auth:** Session-based (bcrypt + HTTP-only cookies)
- **Theme:** Money-green color palette

## Quick Start

```bash
# Clone
git clone https://github.com/jvalin17/rup-split.git
cd rup-split

# Setup
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Configure
cp .env.example .env
# Edit .env if needed (defaults work for local dev with SQLite)

# Run
uvicorn app.main:app --port 8041 --reload
```

Open http://localhost:8041

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | No | `sqlite+aiosqlite:///./rupsplit.db` | Database connection string |
| `SECRET_KEY` | Yes (prod) | Auto-generated | Session signing key |
| `CSRF_SECRET` | Yes (prod) | Auto-generated | CSRF token secret |
| `DEBUG` | No | `false` | Enable debug logging |

## Running Tests

```bash
# All tests
.venv/bin/python -m pytest -q

# Verbose
.venv/bin/python -m pytest -v

# Single file
.venv/bin/python -m pytest tests/unit/test_friendship.py -v
```

29 tests passing (splits, simplification, friendship service).

## Deploy to Render

1. Push to GitHub (repo: `jvalin17/rup-split`)
2. Go to [render.com](https://render.com) → New → Web Service
3. Connect your GitHub repo
4. Render auto-detects `render.yaml` and `Dockerfile`
5. Set environment variables: `DATABASE_URL`, `SECRET_KEY`, `CSRF_SECRET`
6. Deploy

For production, use PostgreSQL (e.g., Neon free tier):
```
DATABASE_URL=postgresql+asyncpg://user:pass@host/dbname?sslmode=require
```

## Project Structure

```
app/
  config.py          # Settings (env vars)
  database.py        # SQLAlchemy async engine
  main.py            # FastAPI app + router registration
  models/
    user.py          # User model
    group.py         # Group + GroupMember models
    expense.py       # Expense + ExpenseSplit models
    friendship.py    # Friendship model (pending/accepted)
  routes/
    auth.py          # Login, register, logout
    dashboard.py     # Dashboard with cross-group balances
    expense.py       # Add/delete expenses
    friend.py        # Search, request, accept, reject, remove, add-to-group
    group.py         # Create, detail, invite, join
    settlement.py    # Record settlements
  services/
    balance.py       # Derived balance computation
    expense.py       # Split calculations (equal, exact, percent)
    friendship.py    # Friend request logic
  templates/         # Jinja2 templates (base, auth, group, expense, friends)
  static/style.css   # Money-green theme overrides
tests/
  unit/              # 29 unit tests
Dockerfile           # Production container
render.yaml          # Render deployment config
```

## License

MIT
