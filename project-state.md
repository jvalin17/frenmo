# Project State

## Core Intent
- **What:** Free Splitwise clone with strong data consistency, debt simplification, and atomic expense operations
- **For whom:** ~50 friends/family members splitting expenses
- **Current workflow:** Using Splitwise (paywalled features) or manual tracking

## Last Skill Run
- **Skill:** /architecture
- **Date:** 2026-06-08
- **Status:** Complete — 11 architecture decisions documented
- **Mode:** auto

## Key Decisions

| ID | Decision | Evidence | Made By | Date |
|----|----------|----------|---------|------|
| D-REQ-1 | Single currency per group (INR default) | User constraint: 50 users, simplicity | user + requirements | 2026-06-08 |
| D-REQ-2 | No payment links — settlements recorded manually | User requirement | user | 2026-06-08 |
| D-REQ-3 | FastAPI + Jinja2 + HTMX (single deployment) | Cheapest hosting, Python-only [tech-stack-advisor] | requirements | 2026-06-08 |
| D-REQ-4 | PostgreSQL for strong consistency | SELECT FOR UPDATE, row-level locking [tech-stack-advisor] | requirements | 2026-06-08 |
| D-REQ-5 | Session-based auth (HTTP-only cookies) | Server-rendered app [tech-stack-advisor] | requirements | 2026-06-08 |
| D-REQ-6 | Fly.io hosting (~$4/mo) | Cheapest viable with persistent storage [tech-stack-advisor] | requirements | 2026-06-08 |
| D-REQ-7 | Amounts stored as integer cents | Avoids floating point errors [functional-researcher] | requirements | 2026-06-08 |
| D-REQ-8 | Balances derived, not stored | Prevents race conditions [functional-researcher] | requirements | 2026-06-08 |
| D-ARCH-1 | Normalized PostgreSQL schema | ACID, foreign keys, CHECK constraints | architecture | 2026-06-08 |
| D-ARCH-2 | No caching layer | ~50 users, stale cache risks financial accuracy | architecture | 2026-06-08 |
| D-ARCH-3 | Strong consistency (single PG instance) | Financial data must never be stale | architecture | 2026-06-08 |
| D-ARCH-4 | Session auth + bcrypt + CSRF | OWASP A07 aligned, server-rendered | architecture | 2026-06-08 |
| D-ARCH-5 | Owner + group membership authorization | OWASP A01, IDOR prevention | architecture | 2026-06-08 |
| D-ARCH-6 | Pydantic input validation | OWASP A03, native to FastAPI | architecture | 2026-06-08 |
| D-ARCH-10 | pytest + httpx + factory_boy testing | 60/30/10 pyramid, real Postgres for integration | architecture | 2026-06-08 |

## Parking Lot

| Item | Parked By | Is Core Intent? | Status |
|------|-----------|-----------------|--------|
| Multi-currency | /requirements | No | v2 |
| Receipt scanning | /requirements | No | v2 |
| OAuth/social login | /requirements | No | v2 |
| Push notifications | /requirements | No | v2 |
| Export CSV/PDF | /requirements | No | v2 |

## Active Warnings

None.

## Feature Tracker

| Feature | Status | Verified | Commit | Notes |
|---------|--------|----------|--------|-------|
| Project skeleton + DB setup | pending | | | slab-1 |
| Auth (register/login/logout) | pending | | | slab-2 |
| Groups (CRUD + invite links) | pending | | | slab-3 |
| Expenses (add/edit/delete, 3 split types) | pending | | | slab-4 |
| Balances (derived) + debt simplification | pending | | | slab-5 |
| Settlements (record + history) | pending | | | slab-6 |
| Activity feed + dashboard | pending | | | slab-7 |
| UI polish (Tailwind + DaisyUI) | pending | | | slab-8 |
| Currency selector (per-expense) | in-progress | | | slab-8b |
| Money-green theme | in-progress | | | slab-8c |
| Friends system (search + add + list) | pending | | | slab-10 |
| Spending charts (category + monthly + per-member) | pending | | | slab-11 |
| Deployment (Fly.io + Dockerfile) | pending | | | slab-12 |

## Handoff Summaries

### /requirements -> /architecture
Core: Splitwise clone with atomic expense ops and debt simplification. Must-haves: auth, groups, expenses (3 split types), derived balances, greedy debt simplification, settlements. Watch out for: concurrency (row-level locking), rounding (integer cents + remainder distribution), idempotency keys.

### /architecture -> /implementation
Pattern: Server-rendered monolith (FastAPI + Jinja2 + HTMX + PostgreSQL). Key decisions: normalized schema, integer cents, derived balances, session auth, Pydantic validation, SELECT FOR UPDATE for edits. Watch out for: split rounding (distribute remainder), idempotency key uniqueness constraint, CSRF on all mutation routes. Build order: skeleton -> auth -> groups -> expenses -> balances -> settlements -> activity -> UI -> deploy.
