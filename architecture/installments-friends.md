# Architecture: Installment Settlements + Friends Balance Dashboard

> Based on requirements/installments-friends.md
> Date: 2026-10-11

## Design Decisions

### AD-1: No new tables for installments
Partial payments are already supported by the data model — each settlement is an `Expense(expense_type='settlement')` with `ExpenseSplit` rows. Multiple settlements between the same pair in the same group naturally accumulate. Payment history = query settlements between two users.

### AD-2: Friends balance via bilateral per-group aggregation
`get_overall_balances` currently returns aggregate net per other user but no group breakdown. New function `get_friend_balance_detail(db, user_id, friend_id)` returns per-group balances + settlement history. Uses existing `get_group_balances` + `simplify_debts` per shared group.

### AD-3: Auto-friendship uses existing model
On group join, iterate existing members and call `send_friend_request` + auto-accept. Skip if friendship exists (unique constraint handles duplicates). No new tables.

## Data Flow

### Installment Settlement
```
User slides partial amount → POST /settlements/new/{group_id}
  → create_expense_with_splits(expense_type='settlement', amount=partial)
  → ExpenseSplit rows created (payer paid_amount, recipient owed_amount)
  → get_group_balances recalculates net (includes all settlements)
  → simplify_debts shows reduced remaining balance
```

### Friends Balance
```
GET /friends → for each friend:
  → find shared groups (groups where both are members)
  → per group: get_group_balances → simplify_debts → extract bilateral balance
  → aggregate across groups → net total
  → query settlements between the pair → payment history
```

### Auto-Friendship
```
POST /groups/join/{token} → add GroupMember
  → for each existing member: ensure_friendship(new_user, member)
  → recalculate_splits_for_new_member (existing)
```

## Files to Modify

| File | Change |
|------|--------|
| `app/services/balance.py` | Add `get_friend_balance_detail()` |
| `app/services/friendship.py` | Add `ensure_friendship()`, `get_shared_groups()` |
| `app/routes/friend.py` | Add balance data to friends page |
| `app/routes/group.py` | Call `ensure_friendship` on join |
| `app/routes/settlement.py` | No change needed (already accepts any amount) |
| `app/templates/friends/index.html` | Show balances, group breakdown, payment history |
| `app/templates/group/detail.html` | Update settle-up to show remaining + allow partial amount input |
