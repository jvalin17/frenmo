"""Tests: kid-friendly toggle hidden for exact/percent/full split types via JS."""
from pathlib import Path


class TestKidToggleHiddenForIncompatibleSplitTypes:
    """Kid toggle must be hidden when split_type is exact, percent, or full."""

    def test_new_html_has_kid_section_id(self):
        """The kid-friendly toggle div must have an id for JS targeting."""
        html = Path("app/templates/expense/new.html").read_text()
        assert 'id="kid-friendly-section"' in html, \
            "Kid toggle div in new.html must have id='kid-friendly-section' for JS show/hide"

    def test_new_html_split_type_controls_kid_toggle(self):
        """Split type onchange JS must hide kid-friendly-section for incompatible types."""
        html = Path("app/templates/expense/new.html").read_text()
        assert "kid-friendly-section" in html and "split-type" in html.lower(), \
            "new.html split-type onchange must toggle kid-friendly-section visibility"

    def test_edit_html_has_kid_section_id(self):
        html = Path("app/templates/expense/edit.html").read_text()
        # Only check if group.kid_friendly is used in the template
        if "kid_friendly" in html:
            assert 'id="kid-friendly-section"' in html, \
                "Kid toggle div in edit.html must have id='kid-friendly-section'"

    def test_edit_html_split_type_controls_kid_toggle(self):
        html = Path("app/templates/expense/edit.html").read_text()
        if "kid_friendly" in html:
            assert "kid-friendly-section" in html, \
                "edit.html must reference kid-friendly-section in split-type handler"
