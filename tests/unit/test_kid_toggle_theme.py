"""Tests for kid-friendly toggle: theme-aware colors, aligned member grid, dynamic JS."""
import re
from pathlib import Path

STYLE_CSS = Path("app/static/style.css").read_text()
DETAIL_HTML = Path("app/templates/group/detail.html").read_text()


class TestToggleUsesThemeAccent:
    """Kid toggle ON state must use var(--accent), not hardcoded green."""

    def test_checked_track_uses_var_accent(self):
        """The checked toggle track background should use var(--accent)."""
        # Find the checked rule for kid-toggle
        match = re.search(
            r'\.kid-toggle-wrap input:checked \+ \.kid-toggle-track\s*\{([^}]+)\}',
            STYLE_CSS,
        )
        assert match, "kid-toggle checked rule must exist in style.css"
        rule_body = match.group(1)
        assert "var(--accent)" in rule_body, \
            f"Checked toggle should use var(--accent), not hardcoded color. Got: {rule_body.strip()}"

    def test_no_hardcoded_green_in_toggle(self):
        """No #16a34a (green-600) should appear in kid-toggle rules."""
        # Extract all kid-toggle related CSS
        toggle_rules = re.findall(r'\.kid-toggle[^{]*\{[^}]+\}', STYLE_CSS)
        combined = " ".join(toggle_rules)
        assert "#16a34a" not in combined, \
            "Kid toggle should not have hardcoded green #16a34a — use var(--accent)"

    def test_off_state_uses_css_vars(self):
        """OFF state should use theme-aware CSS variables, not hardcoded hex."""
        match = re.search(r'\.kid-toggle-track\s*\{([^}]+)\}', STYLE_CSS)
        assert match, "kid-toggle-track rule must exist"
        rule_body = match.group(1)
        assert "var(--" in rule_body, \
            f"OFF state should use CSS variables for background/border. Got: {rule_body.strip()}"

    def test_dark_mode_checked_uses_var_accent(self):
        """Dark mode checked state should also use var(--accent)."""
        match = re.search(
            r'\[data-theme="dark"\]\s*\.kid-toggle-wrap input:checked \+ \.kid-toggle-track\s*\{([^}]+)\}',
            STYLE_CSS,
        )
        # If dark mode has a separate rule, it should use var(--accent)
        # If no separate dark rule exists, that's fine — the light rule already uses var(--accent)
        if match:
            rule_body = match.group(1)
            assert "var(--accent)" in rule_body, \
                "Dark mode checked toggle should use var(--accent)"


class TestMemberRowAlignment:
    """Member share rows must use card layout with fixed-width input group."""

    def test_member_card_class_exists_in_css(self):
        """A .member-shares-card class should exist in style.css."""
        assert ".member-shares-card" in STYLE_CSS, \
            "style.css must have .member-shares-card class for member rows"

    def test_member_fields_class_exists(self):
        """A .member-fields class should exist for the input group."""
        assert ".member-fields" in STYLE_CSS, \
            "style.css must have .member-fields class for aligned inputs"

    def test_detail_template_uses_card_class(self):
        """group/detail.html member rows should use the card class."""
        assert "member-shares-card" in DETAIL_HTML, \
            "group/detail.html should use member-shares-card class for member rows"


class TestDynamicToggleJS:
    """Toggle must dynamically show/hide kid columns without page reload."""

    def test_toggle_has_onchange_handler(self):
        """The kid_friendly checkbox should have a JS change handler."""
        # Look for JS that references the kid_friendly checkbox change
        assert "kid_friendly" in DETAIL_HTML and ("onchange" in DETAIL_HTML or "addEventListener" in DETAIL_HTML or "kidToggle" in DETAIL_HTML), \
            "group/detail.html must have JS handling kid_friendly toggle change"

    def test_kid_columns_always_rendered(self):
        """Kid count inputs should always be in the HTML (not server-conditional), hidden via JS."""
        # The kid count inputs should NOT be inside {% if group.kid_friendly %}
        # They should always render but be hidden when toggle is OFF
        assert 'kid-columns' in DETAIL_HTML or 'kid-col' in DETAIL_HTML, \
            "Kid count columns must have a CSS class for JS show/hide (kid-columns or kid-col)"

    def test_effective_shares_display_exists(self):
        """Each member row should show effective shares that update dynamically."""
        assert 'effective-shares' in DETAIL_HTML or 'data-effective' in DETAIL_HTML, \
            "Member rows must have an effective shares display element for JS updates"
