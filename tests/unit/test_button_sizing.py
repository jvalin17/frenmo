"""Tests for button sizing and WCAG tap target compliance."""
from pathlib import Path


class TestGroupDetailButtons:
    """Group detail toolbar buttons should meet WCAG tap target minimums."""

    def test_import_button_uses_pill_style(self):
        """Import button should use pill-style rounded-full for fintech toolbar."""
        template = Path("app/templates/group/detail.html").read_text()
        assert 'rounded-full' in template, \
            "Import button should use rounded-full pill style"

    def test_import_button_label(self):
        """Import button should say 'Import Expenses' for clarity."""
        template = Path("app/templates/group/detail.html").read_text()
        assert "Import Expenses" in template, "Import button should be labeled 'Import Expenses'"


class TestStatementPageButtons:
    """Statement upload page buttons should be prominent primary CTAs."""

    def test_extract_button_is_large(self):
        """Extract Transactions button should be btn-lg for primary CTA."""
        template = Path("app/templates/statement/upload.html").read_text()
        assert "btn-lg" in template and "Extract Transactions" in template, \
            "Extract button should use btn-lg"

    def test_add_selected_button_is_large(self):
        """Add Selected button should be btn-lg for primary CTA."""
        template = Path("app/templates/statement/upload.html").read_text()
        assert "btn-lg" in template and "Add Selected" in template, \
            "Add Selected button should use btn-lg"
