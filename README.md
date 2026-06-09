# Rup-Split

Free Splitwise alternative. Split expenses with friends, simplify debts, settle up — no paywalls.

**Live:** [rup-split.onrender.com](https://rup-split.onrender.com)

## Features

- **5 Split Types** — Equal, exact amounts, percentage, shares (e.g., 3 shares for you + parents), and full (one person owes all)
- **Multi-currency** — USD, INR, EUR, GBP, AED, JPY, CAD, AUD. Each group has its own currency. Expenses can be in any currency — auto-converted to group currency.
- **Currency Converter** — Live exchange rates (cached 12h) with converter widget in every group. Converted values marked with `*` (approximate).
- **Groups** — Create groups (trip, home, couple) with their own currency, invite via shareable link
- **Friends** — Search by email, send/accept/reject requests, add friends to groups directly
- **Debt Simplification** — Greedy algorithm minimizes transactions needed to settle up
- **Spending Charts** — Category pie chart, monthly bar chart, per-member spending bars
- **Comments** — Threaded comments on each expense
- **Edit Expenses** — Update description, amount, split type, category after creation
- **Password Reset** — Forgot password flow sends a signed reset link via email (Resend API). Link expires in 30 minutes.
- **Account Settings** — Edit nickname, email, default currency, change password
- **Dashboard** — Hero balance card (green when owed, orange when owing, blue when settled), quick actions, per-group balances
- **Sidebar Layout** — Members panel with balances on left, content on right (responsive — stacks on mobile)

## Tech Stack

- **Backend:** Python 3.11+, FastAPI, SQLAlchemy 2.0 (async)
- **Frontend:** Jinja2 + HTMX + Tailwind CSS + DaisyUI + Chart.js
- **Database:** SQLite (dev) / PostgreSQL (prod, Neon)
- **Auth:** Session-based (bcrypt + HTTP-only cookies + signed reset tokens)
- **Email:** Resend API
- **Exchange Rates:** open.er-api.com (free, no key)
- **Hosting:** Render + Neon PostgreSQL (both free tier)
- **Theme:** Apple-inspired light with color-faded cards (blue, green, orange)

## Project Structure

```
app/
  models/           user, group, expense, friendship, comment
  routes/           auth, password_reset, account, dashboard, expense, friend, group, comment, settlement
  services/         balance, expense (5 split types), friendship, charts, comments, password_reset, email, currency
  templates/        Jinja2 templates (base, auth, dashboard, group, expense, friends, account)
  static/           Apple-inspired CSS theme
tests/unit/         72 unit tests
```

## Privacy & Security

- **Minimal data:** Only nickname + email. No real name, phone, or address collected.
- **Passwords:** Bcrypt hashed (never stored in plain text)
- **Sessions:** HTTP-only signed cookies
- **In transit:** HTTPS enforced by Render
- **At rest:** Neon PostgreSQL encrypts data at rest
- **Data usage:** Only for expense splitting and charts. No analytics, no tracking, no third-party sharing.

## Built With Claude Code + Agent Toolkit

This entire app was built using [Claude Code](https://claude.ai/claude-code) with the [Agent Toolkit](https://github.com/anthropics/claude-code) harness:

- **TDD workflow** — Every feature starts with failing tests, then implementation. 72 tests covering all business logic.
- **Skill-based development** — `/requirements` for scoping, `/implementation` for TDD slabs, `/precommit` quality gates before every commit, `/debug` for hypothesis-driven bug fixing.
- **Structured slabs** — Features built one at a time, committed independently, never rushing multiple features into one untested commit.
- **Quality gates** — Pre-commit checks run tests + code review before every `git commit`. No skipping.
- **Multi-session continuity** — HANDOFF.md tracks progress across sessions so context is never lost.

## License

MIT
