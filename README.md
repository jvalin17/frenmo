# 💰 Frenmo

Free expense splitting app. Split costs with friends, simplify debts, settle up — no paywalls, no limits.

**Live:** [frenmo.onrender.com](https://frenmo.onrender.com)

## Features

- **5 Split Types** — Equal, exact amounts, percentage, shares (e.g., 3 shares for you + parents), and full (one person owes all)
- **Multi-currency** — USD, INR, EUR, GBP, AED, JPY, CAD, AUD. Each group has its own currency. Expenses in any currency auto-convert to group currency with `*` (approximate).
- **Currency Converter** — Live exchange rates (cached 12h) with converter widget in every group sidebar.
- **Bank Statement Import** — Upload PDF bank statement, auto-detect bank and extract transactions. Supports 10 banks: Chase, Amex, Bank of America, Capital One, Citi, Wells Fargo, Apple Card, US Bank, Discover, HDFC/SBI. Auto-categorizes expenses (food, transport, shopping, etc.). Dedup prevents double-imports. PDF never stored — processed in memory and wiped immediately.
- **Groups** — Create groups (trip, home, couple) with their own currency, invite via shareable link. Editable name and currency.
- **Per-Member Expense View** — Collapsible sections grouped by who paid, each with unique color. Shows expense count and total per person.
- **Friends** — Search by email, send/accept/reject requests, add friends to groups directly
- **Debt Simplification** — Greedy algorithm minimizes transactions needed to settle up
- **Spending Charts** — Category pie chart, monthly bar chart, per-member spending with progress bars
- **Comments** — Threaded comments on each expense
- **Edit Expenses** — Update description, amount, date, split type, category after creation
- **Bulk Delete** — Checkbox multi-select to delete multiple expenses at once
- **Date Picker** — Set expense date for past-date expenses (trips, receipts, etc.)
- **Password Reset** — Email-based via Resend API. Signed token, 30-minute expiry. Doesn't reveal whether email exists (security).
- **Account Settings** — Edit nickname, email, default currency, change password, delete account
- **Dashboard** — Hero balance card (green when owed, orange when owing, blue when settled), quick actions, per-group balances with emoji icons
- **Sidebar Layout** — Members panel with balances on left, converter widget, content on right (responsive — stacks on mobile)

## Supported Banks

| Bank | Date Format | Status |
|------|-------------|--------|
| Chase (CC & Checking) | MM/DD | ✅ Tested |
| American Express | MM/DD/YY | ✅ Tested |
| Bank of America (CC & Checking) | MM/DD + Post Date | ✅ Tested |
| Capital One | Mon DD (named months) | ✅ Tested |
| Citi | MM/DD | ✅ Tested |
| Wells Fargo | MM/DD | ✅ Tested |
| Apple Card | MM/DD/YYYY | ✅ Tested |
| US Bank | MM/DD | ✅ Tested |
| Discover | MM/DD | ✅ Tested |
| HDFC / SBI | MM/DD | ✅ Generic |

Adding a new bank requires only a regex pattern + detection keywords — no structural changes.

## Tech Stack

- **Backend:** Python 3.11+, FastAPI, SQLAlchemy 2.0 (async)
- **Frontend:** Jinja2 + HTMX + Tailwind CSS + DaisyUI + Chart.js
- **Database:** SQLite (dev) / PostgreSQL (prod, Neon)
- **Auth:** Session-based (bcrypt + HTTP-only cookies + signed reset tokens)
- **Email:** Resend API
- **Exchange Rates:** open.er-api.com (free, no key)
- **PDF Parsing:** pdfplumber (server-side, memory-only)
- **Hosting:** Render + Neon PostgreSQL (both free tier)
- **Theme:** Apple-inspired light with color-faded cards, per-member colors, USA flag gradient logo

## Project Structure

```
app/
  models/              user, group, expense, friendship, comment
  routes/              auth, password_reset, account, dashboard, expense,
                       friend, group, comment, settlement, statement
  services/
    expense.py         5 split type calculators
    balance.py         Derived balance computation
    friendship.py      Friend request logic
    charts.py          Chart data aggregation
    comments.py        Comment CRUD
    currency.py        Exchange rate fetching + caching + conversion
    password_reset.py  Token generation/validation
    email.py           Resend API integration
    statement/
      parser.py        Bank detection + 10 bank-specific transaction parsers
      extractor.py     PDF text extraction (pdfplumber, memory-only)
  templates/           Jinja2 (base, auth, dashboard, group, expense, friends, account, statement)
  static/style.css     Apple-inspired CSS theme
tests/unit/            99 unit tests
```

## Privacy & Security

- **Minimal data:** Only nickname + email. No real name, phone, or address.
- **Passwords:** Bcrypt hashed
- **Sessions:** HTTP-only signed cookies
- **In transit:** HTTPS enforced
- **At rest:** Neon PostgreSQL encrypts at rest
- **Data usage:** Expense splitting and charts only. No analytics, no tracking, no third-party sharing.
- **Password reset:** Doesn't reveal whether email exists (prevents enumeration)
- **Account deletion:** Permanently deletes all user data
- **Bank statements:** PDF processed in memory, never stored to disk, bytes wiped immediately after extraction. Only transactions the user explicitly selects are added to the group.

## Built With Agent Toolkit

Frenmo was built from zero to production using the [Agent Toolkit](https://github.com/jvalin17/agent-toolkit) — an open-source harness for structured AI-assisted development with Claude Code.

**How it worked:**

1. **`/requirements`** — Gathered scope, user stories, and priorities. Researched existing expense-splitting apps to identify feature gaps.
2. **`/architecture`** — Designed the system with 11 logged decisions: FastAPI monolith, PostgreSQL with integer cents, derived balances, greedy debt simplification.
3. **`/implementation`** — Built feature-by-feature in TDD slabs. Each slab: failing tests → implement → verify → commit. No slab started until the previous was committed and working.
4. **`/precommit`** — Quality gate before every commit. Tests must pass, code reviewed, app verified running. Zero skipped gates across 99 tests.
5. **`/debug`** — Hypothesis-driven debugging for production issues (asyncpg timezone mismatch, SSL connections). Root cause → test → fix.

**What the toolkit provides:**
- **Skill workflows** — Enforce TDD, prevent shortcuts, catch regressions before they ship
- **Quality gates** — Pre-commit hooks block commits until tests pass
- **Session continuity** — HANDOFF.md preserves context across sessions
- **Auto mode** — Skills chain: requirements → architecture → implementation → deploy

The entire app — auth, groups, 5 split types, friends, charts, comments, password reset, currency converter, bank statement import for 10 banks, Apple-inspired theme — was built across 3 sessions.

**Repo:** [github.com/jvalin17/agent-toolkit](https://github.com/jvalin17/agent-toolkit)

## License

MIT
