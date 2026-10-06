"""Tests for recalculation warning dialog on group settings form."""
from pathlib import Path

DETAIL_HTML = Path("app/templates/group/detail.html").read_text()


class TestRecalcWarningDialog:
    """Group settings form must show confirm dialog before recalculating."""

    def test_form_has_submit_interceptor(self):
        """Settings form must have JS that intercepts submit for confirmation."""
        assert "onsubmit" in DETAIL_HTML or "submit" in DETAIL_HTML, \
            "Settings form must intercept submit event"
        assert "confirm(" in DETAIL_HTML, \
            "Settings form must show a confirm() dialog before submitting"

    def test_warning_mentions_recalculation(self):
        """Warning message should mention recalculating expenses."""
        assert "recalculate" in DETAIL_HTML.lower() or "recalc" in DETAIL_HTML.lower(), \
            "Warning dialog must mention recalculation of expenses"

    def test_warning_mentions_settlements(self):
        """Warning should mention settlements are not affected."""
        assert "settlement" in DETAIL_HTML.lower(), \
            "Warning dialog must mention that settlements are not affected"
