"""
Tests for the CSS theme refactor.
All colors must be theme-aware via CSS variables; no copper-specific hardcoded
values should appear in class rules.
"""
import re
import pytest

CSS_PATH = "app/static/style.css"


def read_css():
    with open(CSS_PATH) as f:
        return f.read()


# ---------------------------------------------------------------------------
# Helper: extract blocks by selector
# ---------------------------------------------------------------------------

def extract_block(css: str, selector: str) -> str:
    """Return the content between { } for the given selector (first match)."""
    pattern = re.escape(selector) + r"\s*\{([^}]*)\}"
    m = re.search(pattern, css)
    return m.group(1) if m else ""


# ---------------------------------------------------------------------------
# 1. Every theme block has --accent-rgb defined
# ---------------------------------------------------------------------------

THEME_BLOCKS = [
    # (human name, selector)
    ("sand root",          ":root"),
    ("sand dark",          '[data-theme="dark"]'),
    ("slate light",        '[data-theme-color="slate"]'),
    ("slate dark",         '[data-theme="dark"][data-theme-color="slate"]'),
    ("ocean light",        '[data-theme-color="ocean"]'),
    ("ocean dark",         '[data-theme="dark"][data-theme-color="ocean"]'),
    ("rose light",         '[data-theme-color="rose"]'),
    ("rose dark",          '[data-theme="dark"][data-theme-color="rose"]'),
    ("mint light",         '[data-theme-color="mint"]'),
    ("mint dark",          '[data-theme="dark"][data-theme-color="mint"]'),
    ("night light",        '[data-theme-color="night"]'),
    ("night dark",         '[data-theme="dark"][data-theme-color="night"]'),
]


@pytest.mark.parametrize("name,selector", THEME_BLOCKS)
def test_accent_rgb_defined_in_theme_block(name, selector):
    css = read_css()
    block = extract_block(css, selector)
    assert block, f"Could not find theme block for {name!r} (selector: {selector})"
    assert "--accent-rgb" in block, (
        f"Theme block {name!r} is missing --accent-rgb\n"
        f"Block content: {block.strip()}"
    )


# ---------------------------------------------------------------------------
# 2. .card-green, .card-orange, .card-yellow use var(-- not hardcoded hex
# ---------------------------------------------------------------------------

CARD_VARIANTS = [".card-green", ".card-orange", ".card-yellow"]


@pytest.mark.parametrize("selector", CARD_VARIANTS)
def test_card_variant_no_hardcoded_hex(selector):
    css = read_css()
    block = extract_block(css, selector)
    assert block, f"Could not find {selector} block"
    # Must use CSS variables
    assert "var(--" in block, (
        f"{selector} must use var(-- but got: {block.strip()}"
    )
    # Must NOT contain hex color literals (e.g. #D1FAE5, #FFFFFF, #A7F3D0)
    hex_matches = re.findall(r"#[0-9A-Fa-f]{3,8}", block)
    assert not hex_matches, (
        f"{selector} still contains hardcoded hex values: {hex_matches}"
    )


# ---------------------------------------------------------------------------
# 3. No [data-theme="dark"] [style*="background: workaround selectors
# ---------------------------------------------------------------------------

def test_no_dark_mode_inline_style_workarounds():
    css = read_css()
    # Match the pattern used in the workaround block
    pattern = r'\[data-theme="dark"\]\s+\[style\*="background'
    matches = re.findall(pattern, css)
    assert not matches, (
        f"Found {len(matches)} dark-mode inline-style workaround selector(s). "
        "These should be removed after template fixes.\n"
        f"Matches: {matches[:5]}"
    )


# ---------------------------------------------------------------------------
# 4. .hero-card box-shadow uses var(--accent-rgb) not hardcoded 192,122,69
# ---------------------------------------------------------------------------

def test_hero_card_shadow_uses_accent_rgb():
    css = read_css()
    block = extract_block(css, ".hero-card")
    assert block, "Could not find .hero-card block"
    assert "192,122,69" not in block and "192, 122, 69" not in block, (
        ".hero-card box-shadow still uses hardcoded copper rgba(192,122,69,...)"
    )
    assert "var(--accent-rgb)" in block, (
        ".hero-card box-shadow must use rgba(var(--accent-rgb), ...)"
    )


# ---------------------------------------------------------------------------
# 5. .person-row checked state uses var(--accent-rgb) not hardcoded rgba
# ---------------------------------------------------------------------------

def test_person_row_checked_uses_accent_rgb():
    css = read_css()
    # Check .p-status rule inside person-row checked
    assert "192,122,69" not in css or _only_in_comments(css, "192,122,69"), (
        "Found hardcoded copper 192,122,69 in CSS outside comments"
    )
    # The checked p-status rule specifically
    checked_pattern = r'\.person-row:has\(:checked\)\s+\.p-status\s*\{([^}]*)\}'
    m = re.search(checked_pattern, css)
    assert m, "Could not find .person-row:has(:checked) .p-status rule"
    block = m.group(1)
    assert "192,122,69" not in block and "192, 122, 69" not in block, (
        ".person-row:has(:checked) .p-status still uses hardcoded rgba(192,122,69,...)"
    )
    assert "var(--accent-rgb)" in block, (
        ".person-row:has(:checked) .p-status must use rgba(var(--accent-rgb), ...)"
    )


def _only_in_comments(css: str, pattern: str) -> bool:
    """Return True if all occurrences of pattern are inside CSS comments."""
    # Remove comments and check if pattern still exists
    no_comments = re.sub(r'/\*.*?\*/', '', css, flags=re.DOTALL)
    return pattern not in no_comments


# ---------------------------------------------------------------------------
# 6. Dark mode .card overrides use var() not hardcoded hex
# ---------------------------------------------------------------------------

def test_dark_mode_card_override_no_hardcoded_hex():
    css = read_css()
    # Find the [data-theme="dark"] .card block
    pattern = r'\[data-theme="dark"\]\s+\.card\s*\{([^}]*)\}'
    m = re.search(pattern, css)
    assert m, 'Could not find [data-theme="dark"] .card block'
    block = m.group(1)
    hex_matches = re.findall(r"#[0-9A-Fa-f]{3,8}", block)
    assert not hex_matches, (
        f'[data-theme="dark"] .card still contains hardcoded hex: {hex_matches}'
    )


def test_dark_mode_hero_card_override_no_hardcoded_hex():
    css = read_css()
    # Find [data-theme="dark"] .hero-card block
    pattern = r'\[data-theme="dark"\]\s+\.hero-card\s*\{([^}]*)\}'
    m = re.search(pattern, css)
    if not m:
        # If the block doesn't exist that's also fine (was removed)
        return
    block = m.group(1)
    hex_matches = re.findall(r"#[0-9A-Fa-f]{3,8}", block)
    assert not hex_matches, (
        f'[data-theme="dark"] .hero-card still has hardcoded hex: {hex_matches}'
    )
