"""
Tests that HTML templates use CSS variables instead of hardcoded hex colors.
These enforce theme-awareness: templates must not embed color-specific hex values
that would break dark/copper/custom themes.
"""
import re
import pathlib

TEMPLATE_ROOT = pathlib.Path(__file__).parent.parent.parent / "app" / "templates"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def read(rel_path: str) -> str:
    return (TEMPLATE_ROOT / rel_path).read_text()


# ---------------------------------------------------------------------------
# dashboard.html — hero card
# ---------------------------------------------------------------------------

DASHBOARD_POSITIVE_HEX = ["#BBF7D0", "#DCFCE7", "#86EFAC"]
DASHBOARD_NEGATIVE_HEX = ["#FED7AA", "#FFEDD5", "#FDBA74"]
DASHBOARD_SHADOW_RGBA = [
    r"rgba\(34,197,94",
    r"rgba\(249,115,22",
]


def test_dashboard_hero_no_hardcoded_green_hex():
    """Hero card must not embed green hex gradients — should use CSS vars."""
    html = read("dashboard.html")
    for color in DASHBOARD_POSITIVE_HEX:
        assert color not in html, (
            f"dashboard.html hero card still contains hardcoded green hex {color!r}. "
            "Replace with CSS variables (var(--bg-hover), var(--bg-card), var(--border))."
        )


def test_dashboard_hero_no_hardcoded_orange_hex():
    """Hero card must not embed orange hex gradients — should use CSS vars."""
    html = read("dashboard.html")
    for color in DASHBOARD_NEGATIVE_HEX:
        assert color not in html, (
            f"dashboard.html hero card still contains hardcoded orange hex {color!r}. "
            "Replace with CSS variables."
        )


def test_dashboard_hero_shadow_no_hardcoded_rgba():
    """Hero card box-shadow must use var(--accent-rgb) fallback, not hardcoded rgba values."""
    html = read("dashboard.html")
    for pattern in DASHBOARD_SHADOW_RGBA:
        assert not re.search(pattern, html), (
            f"dashboard.html hero card shadow still contains hardcoded rgba matching {pattern!r}. "
            "Use rgba(var(--accent-rgb, ...), 0.12) instead."
        )


# ---------------------------------------------------------------------------
# group/detail.html — Add Friends avatar & kid-friendly badge
# ---------------------------------------------------------------------------

def test_detail_add_friends_avatar_no_hardcoded_green():
    """'Add Friends' avatar must use var(--accent), not #34C759."""
    html = read("group/detail.html")
    # Check only the avatar in the Add Friends section, not semantic colours elsewhere
    # The offending string is style="background: #34C759"
    assert "#34C759" not in html, (
        "group/detail.html Add Friends avatar still uses #34C759. "
        "Replace with var(--accent)."
    )


def test_detail_kid_friendly_badge_no_hardcoded_colors():
    """Kid-friendly badge must not hardcode #FEF3C7 or #92400E — use CSS vars."""
    html = read("group/detail.html")
    assert "#FEF3C7" not in html, (
        "group/detail.html kid-friendly badge still uses #FEF3C7. "
        "Replace with var(--bg-hover)."
    )
    assert "#92400E" not in html, (
        "group/detail.html kid-friendly badge still uses #92400E. "
        "Replace with var(--accent)."
    )


# ---------------------------------------------------------------------------
# statement/upload.html — drop zone JS
# ---------------------------------------------------------------------------

def test_upload_dropzone_no_hardcoded_green():
    """Drop zone JS must not embed #34C759 — use CSS var(--accent)."""
    html = read("statement/upload.html")
    assert "#34C759" not in html, (
        "statement/upload.html drop zone still hardcodes #34C759. "
        "Use var(--accent) for the border color."
    )


def test_upload_dropzone_no_hardcoded_ecfdf5():
    """Drop zone JS must not embed #ECFDF5 — use CSS var(--bg-hover)."""
    html = read("statement/upload.html")
    assert "#ECFDF5" not in html, (
        "statement/upload.html drop zone still hardcodes #ECFDF5. "
        "Use var(--bg-hover) for the background."
    )


# ---------------------------------------------------------------------------
# group/charts.html — Chart.js bar chart copper-specific rgba values
# ---------------------------------------------------------------------------

CHARTS_COPPER_RGBA = [
    r"rgba\(192,122,69",
    r"rgba\(212,146,92",
]


def test_charts_no_hardcoded_copper_rgba():
    """Monthly bar chart must not embed copper-specific rgba — use --accent-rgb CSS var."""
    html = read("group/charts.html")
    for pattern in CHARTS_COPPER_RGBA:
        assert not re.search(pattern, html), (
            f"group/charts.html still contains copper-specific rgba matching {pattern!r}. "
            "Read --accent-rgb from getComputedStyle and use it dynamically."
        )
