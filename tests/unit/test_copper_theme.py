"""Tests for copper palette migration — ensures old blue accent is replaced."""
import re
from pathlib import Path

STYLE_CSS = Path("app/static/style.css").read_text()


def _root_block(css: str) -> str:
    """Extract the :root { ... } block from CSS."""
    match = re.search(r':root\s*\{([^}]+)\}', css)
    return match.group(1) if match else ""


def _dark_block(css: str) -> str:
    """Extract the [data-theme='dark'] block from CSS."""
    match = re.search(r'\[data-theme="dark"\]\s*\{([^}]+)\}', css)
    return match.group(1) if match else ""


class TestCSSVariablesLightMode:
    """Light mode CSS variables should use copper palette."""

    def test_accent_is_copper(self):
        root = _root_block(STYLE_CSS)
        assert "#C07A45" in root, "Light mode --accent should be copper #C07A45"

    def test_bg_page_is_warm(self):
        root = _root_block(STYLE_CSS)
        assert "#FAF9F7" in root, "Light mode --bg-page should be warm off-white #FAF9F7"

    def test_bg_card_is_warm(self):
        root = _root_block(STYLE_CSS)
        assert "#F2EFEA" in root, "Light mode --bg-card should be #F2EFEA"

    def test_text_primary_is_warm(self):
        root = _root_block(STYLE_CSS)
        assert "#1A1410" in root, "Light mode --text-primary should be warm #1A1410"

    def test_no_apple_blue_in_root(self):
        root = _root_block(STYLE_CSS)
        assert "#007AFF" not in root, "No Apple blue #007AFF should remain in :root"


class TestCSSVariablesDarkMode:
    """Dark mode CSS variables should use copper palette."""

    def test_dark_accent_is_bright_copper(self):
        dark = _dark_block(STYLE_CSS)
        assert "#D4925C" in dark, "Dark mode --accent should be bright copper #D4925C"

    def test_dark_bg_page_is_warm_near_black(self):
        dark = _dark_block(STYLE_CSS)
        assert "#0E0C09" in dark, "Dark mode --bg-page should be warm near-black #0E0C09"

    def test_dark_bg_card_is_warm(self):
        dark = _dark_block(STYLE_CSS)
        assert "#1C1A17" in dark, "Dark mode --bg-card should be #1C1A17"

    def test_dark_text_primary_is_cream(self):
        dark = _dark_block(STYLE_CSS)
        assert "#EBE3CC" in dark, "Dark mode --text-primary should be warm cream #EBE3CC"

    def test_no_apple_dark_blue_in_dark(self):
        dark = _dark_block(STYLE_CSS)
        assert "#0A84FF" not in dark, "No Apple dark blue #0A84FF should remain in dark block"


class TestCSSClassColors:
    """Hardcoded class-level colors should use copper."""

    def test_btn_primary_uses_copper(self):
        assert "#C07A45" in STYLE_CSS and ".btn-primary" in STYLE_CSS, \
            "btn-primary should use copper accent"

    def test_no_apple_blue_in_btn_primary(self):
        # Find the btn-primary rule and check no blue
        btn_section = STYLE_CSS[STYLE_CSS.index(".btn-primary"):STYLE_CSS.index(".btn-primary") + 500]
        assert "#007AFF" not in btn_section, "btn-primary should not contain Apple blue"

    def test_hero_card_uses_copper(self):
        assert "#C07A45" in STYLE_CSS or "#8B6F4E" in STYLE_CSS, \
            "hero-card gradient should use copper tones"

    def test_link_primary_uses_copper(self):
        link_idx = STYLE_CSS.index(".link-primary")
        link_section = STYLE_CSS[link_idx:link_idx + 300]
        assert "#007AFF" not in link_section, "link-primary should not contain Apple blue"


BASE_HTML = Path("app/templates/base.html").read_text()


class TestBaseTemplate:
    """base.html should use copper palette."""

    def test_theme_color_meta_is_copper(self):
        assert 'content="#C07A45"' in BASE_HTML, "theme-color meta should be copper"

    def test_no_apple_blue_in_base(self):
        assert "#007AFF" not in BASE_HTML, "No Apple blue should remain in base.html"

    def test_avatar_gradient_is_copper(self):
        assert "#C07A45" in BASE_HTML, "Avatar gradient should use copper"


class TestGroupDetailTemplate:
    """group/detail.html should use copper palette with pill toolbar."""

    def test_header_card_uses_copper_tint(self):
        html = Path("app/templates/group/detail.html").read_text()
        assert "#F5E6D8" in html, "Header card should use copper tint #F5E6D8"
        assert "#DBEAFE" not in html, "No blue tint #DBEAFE should remain"

    def test_toolbar_has_pill_style(self):
        html = Path("app/templates/group/detail.html").read_text()
        assert "rounded-full" in html, "Toolbar buttons should be pill-shaped"

    def test_no_apple_blue_accent(self):
        html = Path("app/templates/group/detail.html").read_text()
        # #007AFF should not appear as an accent (may appear in semantic contexts)
        assert html.count("#007AFF") == 0, "No Apple blue accent in group detail"

    def test_member_colors_are_warm(self):
        html = Path("app/templates/group/detail.html").read_text()
        assert "#C07A45" in html, "Member colors should include copper"

    def test_sidebar_chips_use_copper(self):
        html = Path("app/templates/group/detail.html").read_text()
        assert "#EEF2FF" not in html, "No indigo chip bg should remain"


class TestDashboardTemplate:
    """dashboard.html should use copper palette."""

    def test_no_stripe_purple_avatar(self):
        html = Path("app/templates/dashboard.html").read_text()
        assert "#635BFF" not in html, "No Stripe purple should remain in dashboard"

    def test_copper_avatar(self):
        html = Path("app/templates/dashboard.html").read_text()
        assert "#C07A45" in html, "Dashboard avatars should use copper"


class TestStatementTemplate:
    """statement/upload.html should use copper palette."""

    def test_drop_zone_uses_copper(self):
        html = Path("app/templates/statement/upload.html").read_text()
        assert "#DDB896" in html, "Drop zone border should be copper #DDB896"

    def test_no_blue_drop_zone(self):
        html = Path("app/templates/statement/upload.html").read_text()
        assert "#BFDBFE" not in html, "No blue border in drop zone"

    def test_file_name_color_is_copper(self):
        html = Path("app/templates/statement/upload.html").read_text()
        assert "#C07A45" in html, "File name display should use copper"


class TestExpenseTemplates:
    """expense new/edit should use copper palette."""

    def test_person_row_avatar_is_copper(self):
        html = Path("app/templates/expense/new.html").read_text()
        assert "#C07A45" in html, "Person row avatar should use copper"
        assert "#007AFF" not in html, "No Apple blue in expense/new.html"

    def test_edit_template_matches(self):
        html = Path("app/templates/expense/edit.html").read_text()
        assert "#C07A45" in html, "Person row avatar should use copper in edit"
        assert "#007AFF" not in html, "No Apple blue in expense/edit.html"


class TestAccountSettings:
    """account/settings.html should use copper palette."""

    def test_avatar_is_copper(self):
        html = Path("app/templates/account/settings.html").read_text()
        assert "#C07A45" in html, "Account avatar should use copper"
        assert "#635BFF" not in html, "No Stripe purple in settings"


class TestManifest:
    """PWA manifest should use copper palette."""

    def test_manifest_theme_color_is_copper(self):
        html = Path("app/static/manifest.json").read_text()
        assert "#007AFF" not in html, "PWA manifest should not have Apple blue"
        assert "#C07A45" in html, "PWA manifest theme_color should be copper"

    def test_manifest_bg_is_warm(self):
        html = Path("app/static/manifest.json").read_text()
        assert "#FBFBFD" not in html, "PWA manifest bg should not be cold white"


class TestNoBlueTailwindClasses:
    """No Tailwind blue utility classes in templates."""

    def test_no_bg_blue_in_dashboard(self):
        html = Path("app/templates/dashboard.html").read_text()
        assert "bg-blue" not in html, "No bg-blue Tailwind class should remain"


class TestChartsTemplate:
    """group/charts.html should use copper palette."""

    def test_progress_bars_use_copper(self):
        html = Path("app/templates/group/charts.html").read_text()
        assert "#C07A45" in html, "Progress bars should use copper"
        assert "#3C3B6E" not in html, "No old navy blue in charts"
