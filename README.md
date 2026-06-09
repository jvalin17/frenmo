# Rup-Split

Free, self-hosted Splitwise alternative. Split expenses with friends, simplify debts, settle up — no paywalls.

**Live:** [rup-split.onrender.com](https://rup-split.onrender.com)

## Features

- **5 Split Types** — Equal, exact amounts, percentage, shares (for groups like "me + 2 parents"), and full (one person owes all)
- **Multi-currency** — USD, INR, EUR, GBP, AED, JPY, CAD, AUD per expense
- **Groups** — Create groups (trip, home, couple), invite via shareable link
- **Friends** — Search by email, send/accept/reject requests, add friends to groups directly
- **Debt Simplification** — Minimizes transactions needed to settle up
- **Spending Charts** — Category breakdown (pie), monthly trends (bar), per-member spending
- **Comments** — Threaded comments on each expense
- **Edit Expenses** — Update description, amount, split type, category after creation
- **Account Settings** — Edit profile, change password
- **Password Reset** — Email-based via Resend API
- **Dashboard** — Hero balance card (color changes: green when owed, orange when owing), quick actions, per-group balances
- **Sidebar Layout** — Members panel on left, content on right (responsive)

## Tech Stack

- **Backend:** Python 3.11+, FastAPI, SQLAlchemy 2.0 (async)
- **Frontend:** Jinja2 + HTMX + Tailwind CSS + DaisyUI + Chart.js
- **Database:** SQLite (dev) / PostgreSQL (prod, Neon)
- **Auth:** Session-based (bcrypt + HTTP-only cookies + signed reset tokens)
- **Email:** Resend API for password reset
- **Hosting:** Render (free tier) + Neon PostgreSQL (free tier)
- **Theme:** Apple-inspired light theme with color-faded cards

## Quick Start

```bash
git clone https://github.com/jvalin17/rup-split.git
cd rup-split
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
uvicorn app.main:app --port 8041 --reload
```

Open http://localhost:8041

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | No | `sqlite+aiosqlite:///./rupsplit.db` | Database connection string |
| `SECRET_KEY` | Yes (prod) | Auto-generated | Session signing key |
| `CSRF_SECRET` | Yes (prod) | Auto-generated | CSRF token secret |
| `RESEND_API_KEY` | No | — | Resend API key for password reset emails |
| `RESET_FROM_EMAIL` | No | `onboarding@resend.dev` | From address for reset emails |

## Running Tests

```bash
python -m pytest -q          # 63 tests
python -m pytest -v          # verbose
python -m pytest tests/unit/test_splits.py  # single file
```

63 tests covering: splits (equal/exact/percent/shares/full), debt simplification, friendship service, edit expense, comments, password reset.

## Deploy to Render

1. Push to GitHub
2. Render → New → Web Service → connect repo
3. Set env vars: `DATABASE_URL`, `SECRET_KEY`, `CSRF_SECRET`, `RESEND_API_KEY`
4. Deploy (auto-detects `Dockerfile` + `render.yaml`)

PostgreSQL (Neon free tier):
```
DATABASE_URL=postgresql+asyncpg://user:pass@host/dbname
```

## Project Structure

```
app/
  config.py              # Settings (env vars)
  database.py            # SQLAlchemy async engine + SSL handling
  main.py                # FastAPI app + router registration
  models/
    user.py              # User
    group.py             # Group + GroupMember
    expense.py           # Expense + ExpenseSplit
    friendship.py        # Friendship (pending/accepted)
    comment.py           # Comments on expenses
  routes/
    auth.py              # Login, register, logout
    password_reset.py    # Forgot/reset password (Resend email)
    account.py           # Profile edit, password change
    dashboard.py         # Home with hero balance + groups
    expense.py           # Add/edit/delete expenses
    friend.py            # Search, request, accept, remove, add-to-group
    group.py             # Create, detail (sidebar), invite, join, charts
    comment.py           # Add/delete comments
    settlement.py        # Record settlements
  services/
    balance.py           # Derived balance computation
    expense.py           # Split calculations (5 types)
    friendship.py        # Friend request logic
    charts.py            # Chart data aggregation
    comments.py          # Comment CRUD
    password_reset.py    # Token generation/validation
    email.py             # Resend API integration
  templates/             # Jinja2 (base, auth, dashboard, group, expense, friends, account)
  static/style.css       # Apple-inspired theme with color-faded cards
tests/
  unit/                  # 63 unit tests
Dockerfile               # Production container
render.yaml              # Render deployment config
```

## Privacy & Security

- **Minimal data:** Only nickname + email. No real name, phone, or address collected.
- **Passwords:** Bcrypt hashed (never stored in plain text)
- **Sessions:** HTTP-only signed cookies
- **In transit:** HTTPS enforced by Render
- **At rest:** Neon PostgreSQL encrypts data at rest
- **Data usage:** Only for expense splitting and charts. No analytics, no tracking, no third-party sharing.

## License

MIT
