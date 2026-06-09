# 💰 Frenmo

Free Splitwise alternative. Split expenses with friends, simplify debts, settle up — no paywalls.

**Live:** [frenmo.onrender.com](https://frenmo.onrender.com)

## Features

- **5 Split Types** — Equal, exact amounts, percentage, shares (e.g., 3 shares for you + parents), and full (one person owes all)
- **Multi-currency** — USD, INR, EUR, GBP, AED, JPY, CAD, AUD. Each group has its own currency. Expenses in any currency auto-convert to group currency with `*` (approximate).
- **Currency Converter** — Live exchange rates (cached 12h) with converter widget in every group sidebar.
- **Date Picker** — Set expense date (past-date expenses for trips, receipts, etc.)
- **Groups** — Create groups (trip, home, couple) with their own currency, invite via shareable link. Editable name and currency.
- **Friends** — Search by email, send/accept/reject requests, add friends to groups directly
- **Debt Simplification** — Greedy algorithm minimizes transactions needed to settle up
- **Spending Charts** — Category pie chart, monthly bar chart, per-member spending with progress bars
- **Comments** — Threaded comments on each expense with blue-tinted cards
- **Edit Expenses** — Update description, amount, date, split type, category after creation
- **Password Reset** — Forgot password sends a signed reset link via email (Resend API). Expires in 30 minutes. Doesn't reveal whether email exists (security).
- **Account Settings** — Edit nickname, email, default currency, change password, delete account
- **Dashboard** — Hero balance card (green when owed, orange when owing, blue when settled), quick actions, per-group balances with emoji icons
- **Sidebar Layout** — Members panel with balances on left, converter widget, content on right (responsive — stacks on mobile)

## Tech Stack

- **Backend:** Python 3.11+, FastAPI, SQLAlchemy 2.0 (async)
- **Frontend:** Jinja2 + HTMX + Tailwind CSS + DaisyUI + Chart.js
- **Database:** SQLite (dev) / PostgreSQL (prod, Neon free tier)
- **Auth:** Session-based (bcrypt + HTTP-only cookies + signed reset tokens)
- **Email:** Resend API for password reset
- **Exchange Rates:** open.er-api.com (free, no API key needed)
- **Hosting:** Render (free tier) + Neon PostgreSQL (free tier)
- **Theme:** Apple-inspired light theme with color-faded cards and USA flag gradient logo

## Project Structure

```
app/
  models/           user, group, expense, friendship, comment
  routes/           auth, password_reset, account, dashboard, expense, friend, group, comment, settlement
  services/         balance, expense (5 split types), friendship, charts, comments, password_reset, email, currency
  templates/        Jinja2 templates (base, auth, dashboard, group, expense, friends, account)
  static/           Apple-inspired CSS theme with color-faded cards
tests/unit/         72 unit tests
```

## Privacy & Security

- **Minimal data:** Only nickname + email. No real name, phone, or address collected.
- **Passwords:** Bcrypt hashed (never stored in plain text)
- **Sessions:** HTTP-only signed cookies
- **In transit:** HTTPS enforced by Render
- **At rest:** Neon PostgreSQL encrypts data at rest
- **Data usage:** Only for expense splitting and charts. No analytics, no tracking, no third-party sharing.
- **Password reset:** Doesn't reveal whether an email is registered (prevents enumeration).
- **Account deletion:** Users can permanently delete their account and all associated data.

## Built With Claude Code + Agent Toolkit

This entire app was built using [Claude Code](https://claude.ai/claude-code) with the Agent Toolkit harness:

- **TDD workflow** — Every feature starts with failing tests, then implementation. 72 tests covering all business logic.
- **Skill-based development** — `/requirements` for scoping, `/implementation` for TDD slabs, `/precommit` quality gates before every commit, `/debug` for hypothesis-driven bug fixing.
- **Structured slabs** — Features built one at a time, committed independently, never rushing multiple features into one untested commit.
- **Quality gates** — Pre-commit checks run tests + code review before every `git commit`. No skipping.
- **Multi-session continuity** — HANDOFF.md tracks progress across sessions so context is never lost.

## License

MIT
