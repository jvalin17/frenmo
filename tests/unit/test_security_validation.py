"""Tests for security validations: paid_by membership check, split_type allowlist."""
import re
from pathlib import Path

EXPENSE_ROUTE = Path("app/routes/expense.py").read_text()


class TestPaidByValidation:
    """paid_by must be validated as a group member before creating expense."""

    def test_create_route_validates_paid_by(self):
        """Create expense route must check paid_by is a group member."""
        # Look for a membership check on paid_by before creating the expense
        create_fn_start = EXPENSE_ROUTE.index("async def create_expense(")
        # Find where create_expense_with_splits is called
        create_call = EXPENSE_ROUTE.index("create_expense_with_splits", create_fn_start)
        # The validation must happen between the function start and the service call
        section = EXPENSE_ROUTE[create_fn_start:create_call]
        assert "paid_by" in section and ("member" in section.lower() or "group_member" in section.lower()), \
            "Create expense must validate paid_by is a group member before calling service"
        # Must have a query checking membership
        assert "GroupMember" in section and "paid_by" in section, \
            "Must query GroupMember to validate paid_by"

    def test_edit_route_validates_paid_by(self):
        """Edit expense route must also check paid_by membership."""
        edit_fn_start = EXPENSE_ROUTE.index("async def edit_expense(")
        section = EXPENSE_ROUTE[edit_fn_start:]
        assert "paid_by" in section and "GroupMember" in section, \
            "Edit expense must validate paid_by is a group member"


class TestSplitTypeAllowlist:
    """split_type must be validated against a known set."""

    def test_valid_split_types_defined(self):
        """An allowlist of valid split types must exist."""
        assert "VALID_SPLIT_TYPES" in EXPENSE_ROUTE or \
            re.search(r'split_type\s*(not\s+)?in\s*[\{\(]\s*["\']equal', EXPENSE_ROUTE), \
            "Route must define VALID_SPLIT_TYPES or check split_type against an allowlist"

    def test_invalid_split_type_rejected(self):
        """Invalid split_type values must be rejected or defaulted."""
        # There should be a check that defaults or rejects unknown split types
        assert re.search(
            r'(VALID_SPLIT_TYPES|split_type\s+not\s+in|split_type\s+in\s+\{)',
            EXPENSE_ROUTE
        ), "Route must validate split_type against allowlist"
