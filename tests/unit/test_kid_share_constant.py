"""Tests for KID_SHARE_WEIGHT constant and explicit kid_friendly=False in statement import."""
from pathlib import Path

SPLITS_PY = Path("app/services/splits.py").read_text()


class TestKidShareWeightConstant:
    """The kid share weight 0.5 must be a named constant, not a magic number."""

    def test_constant_defined(self):
        assert "KID_SHARE_WEIGHT" in SPLITS_PY, \
            "splits.py must define KID_SHARE_WEIGHT constant"

    def test_constant_value(self):
        from app.services.splits import KID_SHARE_WEIGHT
        assert KID_SHARE_WEIGHT == 0.5

    def test_compute_uses_constant(self):
        """compute_effective_shares should reference KID_SHARE_WEIGHT, not literal 0.5."""
        # Find the function body
        start = SPLITS_PY.index("def compute_effective_shares")
        end = SPLITS_PY.index("\ndef ", start + 1)
        func_body = SPLITS_PY[start:end]
        assert "KID_SHARE_WEIGHT" in func_body, \
            "compute_effective_shares must use KID_SHARE_WEIGHT, not magic 0.5"


class TestStatementImportExplicitKidFriendly:
    """Statement import route must explicitly pass kid_friendly=False."""

    def test_statement_route_passes_kid_friendly_false(self):
        statement_py = Path("app/routes/statement.py").read_text()
        assert "kid_friendly=False" in statement_py, \
            "Statement import must explicitly pass kid_friendly=False to create_expense_with_splits"
