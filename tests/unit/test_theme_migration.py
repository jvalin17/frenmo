"""
Tests for server-side theme name migration.

Verifies that old theme names (copper, classic, dollar, coral, violet, midnight)
are properly migrated to new names (sand, slate, ocean, rose, mint, night) on the
server side — not just in JavaScript localStorage.

H1: The server renders data-theme-color with the raw DB value. If that value is
    "dollar" (an old name), the CSS has no matching selector → falls back to
    DaisyUI defaults → ugly UI.

H2/H3: base.html must map old→new in the Jinja expression itself so the rendered
        HTML attribute always contains a valid new name.
"""
import pathlib
import re

import pytest

ACCOUNT_PY = pathlib.Path("app/routes/account.py").read_text()
BASE_HTML = pathlib.Path("app/templates/base.html").read_text()

OLD_TO_NEW = {
    "copper": "sand",
    "classic": "slate",
    "dollar": "ocean",
    "coral": "rose",
    "violet": "mint",
    "midnight": "night",
}


# ---------------------------------------------------------------------------
# 1. account.py must define OLD_TO_NEW_THEME mapping
# ---------------------------------------------------------------------------

def test_account_route_has_old_to_new_mapping():
    """account.py must expose an OLD_TO_NEW_THEME dict so callers can migrate."""
    assert "OLD_TO_NEW_THEME" in ACCOUNT_PY, (
        "app/routes/account.py is missing OLD_TO_NEW_THEME dict. "
        "Add: OLD_TO_NEW_THEME = {'copper':'sand','classic':'slate',...}"
    )
    # Check all old names are present as keys
    for old_name in OLD_TO_NEW:
        assert f'"{old_name}"' in ACCOUNT_PY or f"'{old_name}'" in ACCOUNT_PY, (
            f"OLD_TO_NEW_THEME in account.py is missing key '{old_name}'"
        )


# ---------------------------------------------------------------------------
# 2. account_page() must migrate old theme before rendering
# ---------------------------------------------------------------------------

def test_account_page_migrates_old_theme():
    """account_page() must check OLD_TO_NEW_THEME and update DB if user has old theme."""
    # The function should use OLD_TO_NEW_THEME to remap before rendering
    assert "OLD_TO_NEW_THEME" in ACCOUNT_PY, (
        "account.py needs OLD_TO_NEW_THEME defined"
    )
    # The account_page function should reference the migration map
    # Find the account_page function body
    func_match = re.search(
        r'async def account_page\(.*?\nasync def ', ACCOUNT_PY, re.DOTALL
    )
    if not func_match:
        # last function — grab to end
        func_match = re.search(
            r'async def account_page\(.*', ACCOUNT_PY, re.DOTALL
        )
    func_body = func_match.group(0) if func_match else ACCOUNT_PY
    assert "OLD_TO_NEW_THEME" in func_body, (
        "account_page() does not reference OLD_TO_NEW_THEME. "
        "It must check if user.theme_color is an old name and migrate it before rendering."
    )


# ---------------------------------------------------------------------------
# 3. base.html must map old→new server-side (Jinja), not only in JS
# ---------------------------------------------------------------------------

def test_base_html_has_server_side_migration():
    """base.html Jinja expression must map old theme names to new before rendering attribute."""
    # The data-theme-color attribute must use a Jinja mapping — not raw user.theme_color
    # Look for {% set theme_map = ... %} or equivalent
    has_jinja_map = (
        "theme_map" in BASE_HTML
        or "OLD_TO_NEW" in BASE_HTML
    )
    assert has_jinja_map, (
        "base.html must have a server-side Jinja theme_map to convert old DB values "
        "(e.g. 'dollar') to new names before emitting data-theme-color. "
        "Currently the raw user.theme_color is emitted, which may be an old name "
        "that has no CSS selector. Add:\n"
        "  {% set theme_map = {'copper':'sand','classic':'slate',...} %}\n"
        "  data-theme-color=\"{{ theme_map.get(user.theme_color, user.theme_color) or 'sand' }}\""
    )

    # Confirm the data-theme-color line uses the map
    attr_line = next(
        (line for line in BASE_HTML.splitlines() if "data-theme-color" in line and "html" in line.lower()),
        None,
    )
    assert attr_line is not None, "Could not find data-theme-color in <html> tag"
    assert "theme_map" in attr_line or "OLD_TO_NEW" in attr_line, (
        f"data-theme-color attribute line does not use Jinja theme_map:\n  {attr_line}\n"
        "It should be: data-theme-color=\"{{ theme_map.get(user.theme_color, user.theme_color) or 'sand' }}\""
    )


# ---------------------------------------------------------------------------
# 4. update_theme() must accept and migrate old names via mapping
# ---------------------------------------------------------------------------

def test_theme_route_accepts_and_migrates_old_names():
    """update_theme() in account.py must map old → new names before saving."""
    # Find the update_theme function body
    func_match = re.search(
        r'async def update_theme\(.*?(?=\n@router|\nasync def |\Z)',
        ACCOUNT_PY,
        re.DOTALL,
    )
    assert func_match, "Could not find update_theme() in account.py"
    func_body = func_match.group(0)

    assert "OLD_TO_NEW_THEME" in func_body, (
        "update_theme() must apply OLD_TO_NEW_THEME mapping to the submitted value "
        "so that a user posting an old theme name gets it stored as the new name.\n"
        "Add: theme_color = OLD_TO_NEW_THEME.get(theme_color, theme_color)"
    )


# ---------------------------------------------------------------------------
# 5. Integration: old theme names must never be emitted in rendered <html> tag
# ---------------------------------------------------------------------------

def test_base_html_old_names_not_hardcoded_as_fallback():
    """base.html must not use any old theme name as a fallback value."""
    for old_name in OLD_TO_NEW:
        # The fallback should be 'sand', not 'copper', 'dollar', etc.
        assert f"or '{old_name}'" not in BASE_HTML, (
            f"base.html uses old name '{old_name}' as fallback — should be 'sand'"
        )
        assert f'or "{old_name}"' not in BASE_HTML, (
            f"base.html uses old name '{old_name}' as fallback — should be 'sand'"
        )
