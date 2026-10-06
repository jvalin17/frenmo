"""Pure split computation functions — no DB, no async, no side effects.

Strategy dispatch replaces if/elif chains. All functions take amounts
in integer paise/cents and return {user_id: owed_amount_paise}.
"""

KID_SHARE_WEIGHT: float = 0.5


def compute_equal_splits(amount_paise: int, member_ids: list[int]) -> dict[int, int]:
    """Split amount equally. Distribute remainder paise to first N members."""
    count = len(member_ids)
    if count == 0:
        return {}
    base = amount_paise // count
    remainder = amount_paise % count

    splits = {}
    for index, member_id in enumerate(member_ids):
        splits[member_id] = base + (1 if index < remainder else 0)
    return splits


def compute_exact_splits(amount_paise: int, member_values: dict[int, float]) -> dict[int, int]:
    """Exact split — values are in rupees, convert to paise. Must sum to total."""
    splits = {}
    total = 0
    for member_id, value in member_values.items():
        paise = round(value * 100)
        splits[member_id] = paise
        total += paise

    if total != amount_paise and splits:
        last_id = list(splits.keys())[-1]
        splits[last_id] += amount_paise - total

    return splits


def compute_percent_splits(amount_paise: int, member_values: dict[int, float]) -> dict[int, int]:
    """Percentage split — values are percentages. Must sum to 100."""
    splits = {}
    total = 0
    for member_id, percent in member_values.items():
        paise = round(amount_paise * percent / 100)
        splits[member_id] = paise
        total += paise

    if total != amount_paise and splits:
        last_id = list(splits.keys())[-1]
        splits[last_id] += amount_paise - total

    return splits


def compute_shares_splits(
    amount_paise: int,
    member_shares: dict[int, float],
    total_splits: int | None = None,
) -> dict[int, int]:
    """Shares/weights split — distribute proportionally by share weights.

    If total_splits is provided, divide by total_splits instead of sum(member_shares).
    This allows "split by N" where N > current member count.
    """
    if not member_shares:
        return {}
    total_effective_shares = float(total_splits) if total_splits else sum(member_shares.values())
    if total_effective_shares == 0:
        raise ValueError("Cannot split: total effective shares is zero")

    splits = {}
    total_assigned = 0
    members = list(member_shares.items())
    for member_id, shares in members[:-1]:
        paise = round(amount_paise * shares / total_effective_shares)
        splits[member_id] = paise
        total_assigned += paise

    last_id, last_shares = members[-1]
    if total_splits:
        splits[last_id] = round(amount_paise * last_shares / total_effective_shares)
    else:
        splits[last_id] = amount_paise - total_assigned
    return splits


def compute_kid_aware_splits(
    amount_paise: int,
    member_shares: dict[int, float],
    parent_user_ids: list[int],
    total_splits: int | None = None,
) -> dict[int, int]:
    """Shares split with remainder assigned to first parent instead of last member.

    Used for kid-friendly expenses where the rounding remainder goes to the
    first parent (member with kid_count > 0, sorted by user_id ascending).
    Falls back to last-member remainder if no parents present.
    """
    if not member_shares:
        return {}
    total_effective_shares = float(total_splits) if total_splits else sum(member_shares.values())
    if total_effective_shares == 0:
        raise ValueError("Cannot split: total effective shares is zero")

    # Round all members individually
    splits = {}
    for user_id, shares in member_shares.items():
        splits[user_id] = round(amount_paise * shares / total_effective_shares)

    # When total_splits is set, remainder stays pending (unassigned to future members)
    # When no total_splits, assign remainder to first parent or last member
    if not total_splits:
        remainder = amount_paise - sum(splits.values())
        if remainder != 0:
            sorted_parents = sorted(pid for pid in parent_user_ids if pid in splits)
            target = sorted_parents[0] if sorted_parents else list(splits.keys())[-1]
            splits[target] += remainder

    return splits


def compute_full_split(
    amount_paise: int, owes_user_id: int, member_ids: list[int],
) -> dict[int, int]:
    """Full split — one person owes the entire amount, everyone else owes 0."""
    return {mid: amount_paise if mid == owes_user_id else 0 for mid in member_ids}


def compute_effective_shares(
    default_shares: int, kid_count: int, is_kid_friendly: bool,
) -> float:
    """Compute a member's effective share weight for an expense.

    Non-kid expense: kids count as full shares (additive).
    Kid-friendly expense: kids count as 0.5 shares each.
    """
    if is_kid_friendly:
        return default_shares + (kid_count * KID_SHARE_WEIGHT)
    return float(default_shares + kid_count)


# Strategy dispatch — replaces if/elif chains in create and update
def compute_splits(
    amount_paise: int,
    split_type: str,
    member_ids: list[int],
    member_values: dict[int, float] | None = None,
    total_splits: int | None = None,
) -> dict[int, int]:
    """Dispatch to the right split function based on split_type."""
    if split_type == "equal":
        if total_splits:
            equal_shares = dict.fromkeys(member_ids, 1.0)
            return compute_shares_splits(
                amount_paise, equal_shares, total_splits=total_splits,
            )
        return compute_equal_splits(amount_paise, member_ids)

    if split_type == "shares" and member_values:
        return compute_shares_splits(
            amount_paise, member_values, total_splits=total_splits,
        )

    if split_type == "exact" and member_values:
        return compute_exact_splits(amount_paise, member_values)

    if split_type == "percent" and member_values:
        return compute_percent_splits(amount_paise, member_values)

    if split_type == "full" and member_values and "full_owes" in member_values:
        return compute_full_split(
            amount_paise, int(member_values["full_owes"]), member_ids,
        )

    # Fallback: equal split
    return compute_equal_splits(amount_paise, member_ids)
