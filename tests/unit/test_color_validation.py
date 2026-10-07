"""
Comprehensive color validation tests — regression guard against hardcoded colors.

If anyone adds a non-semantic hardcoded hex color to templates or non-theme CSS,
these tests will catch it before merge.
"""
import re
import pathlib

TEMPLATE_ROOT = pathlib.Path(__file__).parent.parent.parent / "app" / "templates"
CSS_FILE = pathlib.Path(__file__).parent.parent.parent / "app" / "static" / "style.css"

# ---------------------------------------------------------------------------
# Semantic color allowlists
# ---------------------------------------------------------------------------

# Greens: success / positive balance / confirmation states
GREEN_SEMANTIC = {
    "#34C759",  # Apple green — balance-positive
    "#30D158",  # Apple dark-mode green — btn-success dark
    "#16A34A",  # Tailwind green-600 — up arrow in hero card
    "#059669",  # Tailwind emerald-600 — auth success text
}

# Reds: error / danger / negative balance states
RED_SEMANTIC = {
    "#FF3B30",  # Apple red — balance-negative, text-error
    "#DC2626",  # Tailwind red-600 — danger zone, down arrow
    "#FF6961",  # Pastel red — dark mode alert text
    "#CD3D64",  # Dark pink-red — account settings error
}

# Other explicitly allowed semantic colors in templates
TEMPLATE_SEMANTIC_COLORS = GREEN_SEMANTIC | RED_SEMANTIC | {
    "#FFFFFF",  # White — text on accent-colored buttons
    "#0E6245",  # Dark green — account settings success text
    # Danger zone and alert tint backgrounds/borders (semantic: red-family = error/danger)
    "#FEF2F2",  # Very light red bg — danger zone card, delete section
    "#FECACA",  # Light red border — danger zone card
    "#FFF0F3",  # Light pink bg — account settings error banner
    "#FECDD3",  # Pink border — account settings error banner
    # Success banner tint (semantic: green-family = success/confirmation)
    "#ECFDF5",  # Very light green bg — account settings success banner
    "#A7F3D0",  # Light green border — account settings success banner
}

# These may appear in :root / [data-theme*] blocks in style.css (theme palette definitions)
# and in semantic utility classes (balance-positive, balance-negative, etc.)
CSS_SEMANTIC_COLORS = GREEN_SEMANTIC | RED_SEMANTIC | {
    "#FFFFFF",  # White — toggle thumb, button text
    "#FFF2F2",  # Very light red — alert-error background (light mode)
    "#FEF2F2",  # Very light red — danger zone card background
    "#FECACA",  # Light red border — danger zone card border
    "#FEF2F2",  # p-exempt background (same value, listed once)
    "#3A1C1E",  # Very dark red — dark mode alert-error background
    "#5C2C2E",  # Dark red — dark mode alert-error border
    "#3D3830",  # Dark border — dark mode checkbox border (repeated from theme block)
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

HEX_RE = re.compile(r"#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b")
INLINE_STYLE_HEX_RE = re.compile(r'style="[^"]*#[0-9a-fA-F]{3,6}[^"]*"')
COPPER_RGBA_RE = re.compile(r"rgba\(\s*192\s*,\s*122\s*,\s*69|rgba\(\s*212\s*,\s*146\s*,\s*92")


def _normalize_hex(h: str) -> str:
    """Normalize a 3-digit hex to 6-digit uppercase, or just uppercase if already 6."""
    h = h.upper()
    if len(h) == 4:  # '#' + 3 chars
        return "#" + h[1] * 2 + h[2] * 2 + h[3] * 2
    return h


def _hex_matches_in_inline_styles(html: str) -> list[tuple[int, str, str]]:
    """Return list of (line_no, full_style_attr, hex_color) for inline styles with hex."""
    results = []
    for lineno, line in enumerate(html.splitlines(), start=1):
        for style_match in INLINE_STYLE_HEX_RE.finditer(line):
            style_attr = style_match.group(0)
            for hex_match in HEX_RE.finditer(style_attr):
                color = _normalize_hex(hex_match.group(0))
                results.append((lineno, style_attr[:80], color))
    return results


def _css_non_theme_blocks(css: str) -> list[tuple[int, str]]:
    """
    Return lines that are inside class rules (NOT :root or [data-theme*] blocks).
    Returns list of (line_no, line_text).
    """
    results = []
    # Track whether we're inside a :root or [data-theme*] block
    in_theme_block = False
    brace_depth = 0
    theme_block_depth = 0

    for lineno, line in enumerate(css.splitlines(), start=1):
        stripped = line.strip()

        # Detect theme block start
        if re.match(r"^(:root|\[data-theme)", stripped):
            in_theme_block = True
            theme_block_depth = brace_depth

        opens = stripped.count("{")
        closes = stripped.count("}")
        brace_depth += opens - closes

        # Exit theme block once we close back to the starting depth
        if in_theme_block and brace_depth <= theme_block_depth and (opens > 0 or closes > 0):
            in_theme_block = False

        if not in_theme_block:
            results.append((lineno, line))

    return results


# ---------------------------------------------------------------------------
# Test 1: No non-semantic hex in template inline styles
# ---------------------------------------------------------------------------

def test_no_non_semantic_hex_in_templates():
    """
    Scan all .html templates for inline style= attributes containing hex colors.
    Only semantic/approved colors are allowed; everything else must use var(--.
    """
    violations = []
    for html_path in sorted(TEMPLATE_ROOT.glob("**/*.html")):
        html = html_path.read_text()
        for lineno, style_snippet, color in _hex_matches_in_inline_styles(html):
            if color not in TEMPLATE_SEMANTIC_COLORS:
                rel = html_path.relative_to(TEMPLATE_ROOT)
                violations.append(
                    f"  {rel}:{lineno} — {color!r} in inline style: {style_snippet!r}"
                )

    assert not violations, (
        "Non-semantic hex colors found in template inline styles.\n"
        "Use var(-- CSS variables instead, or add to TEMPLATE_SEMANTIC_COLORS if truly semantic:\n"
        + "\n".join(violations)
    )


# ---------------------------------------------------------------------------
# Test 2: No copper-specific rgba in templates
# ---------------------------------------------------------------------------

def test_no_copper_specific_rgba_in_templates():
    """
    Scan all .html templates for rgba(192,122,69 or rgba(212,146,92 — copper-specific
    values that must use var(--accent-rgb) instead.
    """
    violations = []
    for html_path in sorted(TEMPLATE_ROOT.glob("**/*.html")):
        html = html_path.read_text()
        for lineno, line in enumerate(html.splitlines(), start=1):
            if COPPER_RGBA_RE.search(line):
                rel = html_path.relative_to(TEMPLATE_ROOT)
                violations.append(
                    f"  {rel}:{lineno} — copper rgba found: {line.strip()[:100]!r}"
                )

    assert not violations, (
        "Copper-specific rgba() values found in templates.\n"
        "Use rgba(var(--accent-rgb), 0.XX) instead:\n"
        + "\n".join(violations)
    )


# ---------------------------------------------------------------------------
# Test 3: CSS class rules use vars not hex (outside theme blocks)
# ---------------------------------------------------------------------------

def test_css_class_rules_use_vars_not_hex():
    """
    Scan style.css for hex colors that appear in class rule blocks
    (not :root or [data-theme*] blocks). Only semantic colors are allowed.
    """
    css = CSS_FILE.read_text()
    non_theme_lines = _css_non_theme_blocks(css)

    violations = []
    for lineno, line in non_theme_lines:
        stripped = line.strip()
        # Skip comments and empty lines
        if stripped.startswith("/*") or stripped.startswith("*") or not stripped:
            continue
        for hex_match in HEX_RE.finditer(stripped):
            color = _normalize_hex(hex_match.group(0))
            if color not in CSS_SEMANTIC_COLORS:
                violations.append(
                    f"  style.css:{lineno} — {color!r} in: {stripped[:100]!r}"
                )

    assert not violations, (
        "Non-semantic hex colors found in CSS class rules (outside theme blocks).\n"
        "Use var(-- CSS variables, or add to CSS_SEMANTIC_COLORS if truly semantic:\n"
        + "\n".join(violations)
    )


# ---------------------------------------------------------------------------
# Test 4: Every theme block defines all required variables
# ---------------------------------------------------------------------------

REQUIRED_VARS = [
    "--accent",
    "--accent-rgb",
    "--bg-page",
    "--bg-card",
    "--bg-input",
    "--bg-hover",
    "--text-primary",
    "--text-secondary",
    "--text-muted",
    "--border",
    "--border-light",
]

THEME_BLOCKS = [
    # sand (default :root + dark)
    (":root", None, None),
    ("[data-theme=\"dark\"]", None, None),
    # slate
    ("[data-theme-color=\"slate\"]", "slate", "light"),
    ("[data-theme=\"dark\"][data-theme-color=\"slate\"]", "slate", "dark"),
    # ocean
    ("[data-theme-color=\"ocean\"]", "ocean", "light"),
    ("[data-theme=\"dark\"][data-theme-color=\"ocean\"]", "ocean", "dark"),
    # rose
    ("[data-theme-color=\"rose\"]", "rose", "light"),
    ("[data-theme=\"dark\"][data-theme-color=\"rose\"]", "rose", "dark"),
    # mint
    ("[data-theme-color=\"mint\"]", "mint", "light"),
    ("[data-theme=\"dark\"][data-theme-color=\"mint\"]", "mint", "dark"),
    # night
    ("[data-theme-color=\"night\"]", "night", "light"),
    ("[data-theme=\"dark\"][data-theme-color=\"night\"]", "night", "dark"),
]


def _extract_block_vars(css: str, selector: str) -> set[str]:
    """
    Extract all CSS variable names defined within the block matching `selector`.
    Returns a set of variable names like '--accent', '--bg-page', etc.
    """
    # Find the selector in the CSS
    # Escape for regex
    escaped = re.escape(selector)
    # Match selector followed by { ... }
    pattern = re.compile(escaped + r"\s*\{([^}]*)\}", re.DOTALL)
    match = pattern.search(css)
    if not match:
        return set()
    block_content = match.group(1)
    # Extract all --var-name occurrences
    return set(re.findall(r"(--[\w-]+)\s*:", block_content))


def test_every_theme_has_required_variables():
    """
    Check that each of the 12 theme blocks (sand, slate, ocean, rose, mint,
    night — each in light and dark) defines ALL required CSS variables.
    """
    css = CSS_FILE.read_text()
    violations = []

    for selector, theme_name, mode in THEME_BLOCKS:
        defined_vars = _extract_block_vars(css, selector)
        missing = [v for v in REQUIRED_VARS if v not in defined_vars]
        if missing:
            label = selector if not theme_name else f"{theme_name} {mode}"
            violations.append(
                f"  [{label}] missing: {', '.join(missing)}"
            )

    assert not violations, (
        "Some theme blocks are missing required CSS variables:\n"
        + "\n".join(violations)
    )


# ---------------------------------------------------------------------------
# Test 5: Hero card component classes exist in style.css
# ---------------------------------------------------------------------------

def test_hero_card_components_exist():
    """
    Check that .hero-card--positive, .hero-card--negative, and .hero-card--settled
    CSS component classes exist in style.css.
    """
    css = CSS_FILE.read_text()
    missing = []
    for cls in (".hero-card--positive", ".hero-card--negative", ".hero-card--settled"):
        if cls not in css:
            missing.append(cls)

    assert not missing, (
        "Missing hero card component classes in style.css: "
        + ", ".join(missing)
        + "\nAdd .hero-card--positive, .hero-card--negative, .hero-card--settled rules."
    )


# ---------------------------------------------------------------------------
# Test 6: dashboard.html hero card uses CSS class, not inline gradient styles
# ---------------------------------------------------------------------------

def test_dashboard_hero_uses_css_class():
    """
    dashboard.html hero card must use class='hero-card hero-card--' pattern
    and must NOT have inline background gradient or inline box-shadow on the hero card div.
    """
    html = (TEMPLATE_ROOT / "dashboard.html").read_text()

    # Must have at least one hero-card-- variant class
    assert re.search(r'class="[^"]*hero-card--', html), (
        "dashboard.html hero card does not use a hero-card-- variant class.\n"
        "Use class=\"hero-card hero-card--positive\" (etc.) based on balance state."
    )

    # Must NOT have inline linear-gradient on the hero card div
    # Look for the hero-card div — check if it has style with linear-gradient
    hero_div_re = re.compile(
        r'<div[^>]*class="[^"]*hero-card[^"]*"[^>]*style="[^"]*linear-gradient',
        re.DOTALL,
    )
    assert not hero_div_re.search(html), (
        "dashboard.html hero card div still has an inline linear-gradient style.\n"
        "Remove the inline style and use the .hero-card-- CSS component class instead."
    )

    # Must NOT have inline box-shadow on the hero card div
    hero_shadow_re = re.compile(
        r'<div[^>]*class="[^"]*hero-card[^"]*"[^>]*style="[^"]*box-shadow',
        re.DOTALL,
    )
    assert not hero_shadow_re.search(html), (
        "dashboard.html hero card div still has an inline box-shadow style.\n"
        "Remove the inline style and use the .hero-card-- CSS component class instead."
    )
