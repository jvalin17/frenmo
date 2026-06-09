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
- **Bank Statement Import** — Upload PDF bank statement, auto-detect bank (Discover, Chase, BoA, Amex, Apple Card, HDFC, SBI), extract transactions with auto-categorization, review and select which to add. Dedup prevents double-imports. PDF never stored — processed in memory and wiped.
- **Per-Member Expense View** — Collapsible sections grouped by who paid, each with unique color (blue, purple, pink, orange, green). Shows expense count and total per person.
- **Bulk Delete** — Checkbox multi-select to delete multiple expenses at once
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
- **Bank statements:** PDF processed in memory (server-side on mobile) or client-side in browser (desktop). Never stored to disk. Bytes wiped immediately after extraction.

## Built With Agent Toolkit

This app was built from scratch to production in a single day using the [Agent Toolkit](https://github.com/jvalin17/agent-toolkit) — an open-source harness for structured AI-assisted development.

**How it worked:**

1. **`/requirements`** — Gathered scope, user stories, and priorities. Researched Splitwise, Tricount, Settle Up, and Splid to identify feature gaps and opportunities.
2. **`/architecture`** — Designed the system: FastAPI + Jinja2 + HTMX monolith, PostgreSQL with integer cents, derived balances, greedy debt simplification. 11 architecture decisions logged with evidence.
3. **`/implementation`** — Built feature-by-feature in TDD slabs. Each slab: write failing tests → implement → verify → commit. No slab started until the previous one was committed and working.
4. **`/precommit`** — Quality gate ran before every commit: tests must pass, code must be clean, app must be verified running. 72 tests, zero skipped gates.
5. **`/debug`** — Hypothesis-driven debugging when production broke (asyncpg timezone mismatch, SSL connection issues). Root cause identified, test written, then fixed.

**What the toolkit provides:**
- **Skill workflows** — Structured prompts that enforce TDD, prevent shortcuts, and catch regressions before they ship
- **Quality gates** — Pre-commit hooks that block commits until tests pass and code is reviewed
- **Session continuity** — HANDOFF.md preserves context across sessions so nothing is forgotten
- **Auto mode** — Skills chain together: requirements → architecture → implementation → deploy, with evidence at every step

The entire app — auth, groups, 5 split types, friends, charts, comments, password reset, currency converter, bank statement import, Apple-inspired theme — was built in ~4 hours of active development across 3 sessions.

**Repo:** [github.com/jvalin17/agent-toolkit](https://github.com/jvalin17/agent-toolkit)

## License

MIT
