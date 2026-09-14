"""Tests for expense date grouping in group detail template."""
from pathlib import Path


DETAIL_HTML = Path("app/templates/group/detail.html").read_text()


class TestExpenseDateGrouping:
    """Expenses should be grouped by date, not by member."""

    def test_template_groups_by_date(self):
        """Template should use date-based grouping, not member-based."""
        assert "grouped by date" in DETAIL_HTML.lower() or "group_by_date" in DETAIL_HTML or \
            "date_groups" in DETAIL_HTML or "expenses_by_date" in DETAIL_HTML, \
            "Template should reference date-based grouping"

    def test_template_no_longer_groups_by_member(self):
        """Old member-based grouping should be removed."""
        assert "grouped by member" not in DETAIL_HTML.lower(), \
            "Old member-based grouping comment should be removed"

    def test_template_shows_payer_name(self):
        """Each expense should show who paid since we're no longer grouping by payer."""
        assert "paid_by" in DETAIL_HTML or "member_names.get(expense.paid_by" in DETAIL_HTML, \
            "Each expense should display the payer name"

    def test_date_sections_are_collapsible(self):
        """Date sections should be expandable/collapsible."""
        assert "toggleSection" in DETAIL_HTML, \
            "Date sections should use toggleSection for expand/collapse"

    def test_no_date_group_exists(self):
        """Expenses without dates should have a 'No date' section."""
        assert "No date" in DETAIL_HTML or "no_date" in DETAIL_HTML, \
            "Template should have a 'No date' group for dateless expenses"

    def test_date_headers_are_keyboard_accessible(self):
        """Collapsible date headers should have tabindex and role for a11y."""
        assert 'tabindex="0"' in DETAIL_HTML, "Date headers need tabindex for keyboard nav"
        assert 'role="button"' in DETAIL_HTML, "Date headers need role=button for screen readers"

    def test_no_n1_comments_query(self):
        """Comments should be fetched in a batch, not per-expense."""
        route_code = Path("app/routes/group.py").read_text()
        # The old N+1 pattern: for expense in expenses: get_comments(db, expense.id)
        assert "for expense in expenses" not in route_code or \
            "get_comments(db, expense.id)" not in route_code, \
            "Comments should be batched, not fetched per-expense in a loop"
