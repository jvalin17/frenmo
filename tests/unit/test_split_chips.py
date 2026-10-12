"""Test that split breakdown uses avatar chip style in group detail template."""
from pathlib import Path

DETAIL_HTML = Path("app/templates/group/detail.html").read_text()


def test_split_breakdown_uses_chip_style():
    """Each split should render as a pill with avatar initial + name + amount."""
    assert "rounded-full" in DETAIL_HTML or "border-radius: 20px" in DETAIL_HTML, \
        "Split breakdown should use pill/chip shape (rounded-full or border-radius: 20px)"


def test_split_breakdown_has_avatar_circle():
    """Each split chip should have a colored avatar circle showing the member's initial."""
    assert "avatar_colors[loop.index0 % avatar_colors|length]" in DETAIL_HTML, \
        "Split chips should cycle through avatar_colors for the circle background"
    assert "{{ name[0]|upper }}" in DETAIL_HTML, \
        "Split chip avatar circle should show the member's uppercased initial"


def test_old_arrow_style_removed():
    """The old plain-text arrow style should be replaced."""
    # Old style was: → Name($amount), Name($amount)
    assert "→ {% for s in splits %}" not in DETAIL_HTML, \
        "Old arrow-prefix split style should be replaced with avatar chips"


def test_avatar_color_index_skips_zero_amount_splits():
    """Color cycling should only count rendered chips, not splits with owed_amount == 0.

    Reviewer finding (avatar-chips, medium): using loop.index0 over the raw
    splits list skips a color whenever a zero-amount split is filtered out.
    """
    assert 'selectattr("owed_amount", "gt", 0)' in DETAIL_HTML, \
        "Splits should be filtered to owed_amount > 0 before the chip loop so loop.index0 counts only rendered chips"
