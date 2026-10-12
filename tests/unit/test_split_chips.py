"""Test that split breakdown uses avatar chip style in group detail template."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DETAIL_HTML = (ROOT / "app/templates/group/detail.html").read_text()
STYLE_CSS = (ROOT / "app/static/style.css").read_text()

# White-on-colour contrast >= 4.5:1 (WCAG AA for small text), verified in the review
CHIP_PALETTE = [
    "#4338ca",
    "#be185d",
    "#0f766e",
    "#b45309",
    "#6d28d9",
    "#b91c1c",
    "#0e7490",
    "#4d7c0f",
]


def test_split_breakdown_uses_chip_classes():
    """Each split renders as a .split-chip with avatar, name and amount parts."""
    assert 'class="split-chip"' in DETAIL_HTML
    assert 'class="split-chip__name"' in DETAIL_HTML
    assert 'class="split-chip__amount"' in DETAIL_HTML
    assert (
        'style="display: inline-flex'
        not in DETAIL_HTML.split("Split breakdown")[1].split("Comments")[0]
    ), "Chip styling belongs in style.css, not inline"


def test_split_breakdown_has_avatar_circle():
    """The avatar circle cycles through 8 palette classes and shows the member's initial."""
    assert 'class="split-chip__avatar split-chip__avatar--{{ loop.index0 % 8 }}"' in DETAIL_HTML
    assert "{{ name[0]|upper }}" in DETAIL_HTML


def test_palette_defined_in_css_with_contrast_safe_colors():
    """Palette lives in :root variables (project rule: no raw hex in class rules)."""
    root_block = STYLE_CSS.split(":root {", 1)[1].split("}", 1)[0]
    for i, color in enumerate(CHIP_PALETTE):
        assert f"--chip-{i}: {color};" in root_block, f":root should define --chip-{i}: {color}"
        assert f".split-chip__avatar--{i} {{ background: var(--chip-{i}); }}" in STYLE_CSS
    assert "#f59e0b" not in STYLE_CSS and "#84cc16" not in STYLE_CSS, (
        "low-contrast swatches should be gone"
    )


def test_old_arrow_style_removed():
    """The old plain-text arrow style should be replaced."""
    assert "→ {% for s in splits %}" not in DETAIL_HTML


def test_avatar_color_index_skips_zero_amount_splits():
    """Colour cycling counts only rendered chips, not zero-amount splits (reviewer finding)."""
    assert 'selectattr("owed_amount", "gt", 0)' in DETAIL_HTML
    assert "{% for s in owed_splits %}" in DETAIL_HTML
