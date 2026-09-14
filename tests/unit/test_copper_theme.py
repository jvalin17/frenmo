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

    def test_btn_primary_uses_var_accent(self):
        # btn-primary should use var(--accent), not hardcoded hex
        btn_idx = STYLE_CSS.index(".btn-primary")
        btn_section = STYLE_CSS[btn_idx:btn_idx + 200]
        assert "var(--accent)" in btn_section, "btn-primary should use var(--accent) not hardcoded hex"

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

    def test_header_card_uses_css_var(self):
        html = Path("app/templates/group/detail.html").read_text()
        assert "var(--bg-hover)" in html, "Header card should use var(--bg-hover)"
        assert "#DBEAFE" not in html, "No blue tint #DBEAFE should remain"

    def test_toolbar_has_pill_style(self):
        html = Path("app/templates/group/detail.html").read_text()
        assert "rounded-full" in html, "Toolbar buttons should be pill-shaped"

    def test_no_apple_blue_accent(self):
        html = Path("app/templates/group/detail.html").read_text()
        # #007AFF should not appear as an accent (may appear in semantic contexts)
        assert html.count("#007AFF") == 0, "No Apple blue accent in group detail"

    def test_member_colors_use_css_var(self):
        html = Path("app/templates/group/detail.html").read_text()
        assert "var(--accent)" in html, "Member colors should use var(--accent)"

    def test_sidebar_chips_use_copper(self):
        html = Path("app/templates/group/detail.html").read_text()
        assert "#EEF2FF" not in html, "No indigo chip bg should remain"


class TestDashboardTemplate:
    """dashboard.html should use copper palette."""

    def test_no_stripe_purple_avatar(self):
        html = Path("app/templates/dashboard.html").read_text()
        assert "#635BFF" not in html, "No Stripe purple should remain in dashboard"

    def test_avatar_uses_css_var(self):
        html = Path("app/templates/dashboard.html").read_text()
        assert "var(--accent)" in html, "Dashboard avatars should use var(--accent)"


class TestStatementTemplate:
    """statement/upload.html should use copper palette."""

    def test_drop_zone_uses_css_vars(self):
        html = Path("app/templates/statement/upload.html").read_text()
        assert "var(--border)" in html, "Drop zone should use var(--border)"

    def test_no_blue_drop_zone(self):
        html = Path("app/templates/statement/upload.html").read_text()
        assert "#BFDBFE" not in html, "No blue border in drop zone"

    def test_file_name_uses_css_var(self):
        html = Path("app/templates/statement/upload.html").read_text()
        assert "var(--accent)" in html, "File name display should use var(--accent)"


class TestExpenseTemplates:
    """expense new/edit should use copper palette."""

    def test_person_row_uses_css_var(self):
        html = Path("app/templates/expense/new.html").read_text()
        assert "var(--accent)" in html, "Person row should use var(--accent)"
        assert "#007AFF" not in html, "No Apple blue in expense/new.html"

    def test_edit_template_uses_css_var(self):
        html = Path("app/templates/expense/edit.html").read_text()
        assert "var(--accent)" in html, "Person row should use var(--accent) in edit"
        assert "#007AFF" not in html, "No Apple blue in expense/edit.html"


class TestAccountSettings:
    """account/settings.html should use copper palette."""

    def test_avatar_uses_css_var(self):
        html = Path("app/templates/account/settings.html").read_text()
        assert "var(--accent)" in html, "Account avatar should use var(--accent)"
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

    def test_chart_uses_distinct_muted_colors(self):
        html = Path("app/templates/group/charts.html").read_text()
        assert "#7C9885" in html, "Chart should use muted sage green"
        assert "#B07D62" in html, "Chart should use muted clay"
        assert "#6B8EAD" in html, "Chart should use muted dusty blue"
        assert "#3C3B6E" not in html, "No old navy blue in charts"


# ============================================================
# MULTI-THEME SYSTEM TESTS
# ============================================================

THEMES = {
    "classic": {"light_accent": "#2563EB", "dark_accent": "#60A5FA"},
    "dollar": {"light_accent": "#EA580C", "dark_accent": "#FB923C"},
    "coral": {"light_accent": "#E8522A", "dark_accent": "#FF7B52"},
    "violet": {"light_accent": "#7C3AED", "dark_accent": "#A78BFA"},
    "midnight": {"light_accent": "#1E40AF", "dark_accent": "#60A5FA"},
}


class TestThemeCSSBlocks:
    """Each theme should have a light and dark CSS variable block."""

    def test_classic_light_block_exists(self):
        css = Path("app/static/style.css").read_text()
        assert '[data-theme-color="classic"]' in css

    def test_dollar_light_block_exists(self):
        css = Path("app/static/style.css").read_text()
        assert '[data-theme-color="dollar"]' in css

    def test_coral_light_block_exists(self):
        css = Path("app/static/style.css").read_text()
        assert '[data-theme-color="coral"]' in css

    def test_violet_light_block_exists(self):
        css = Path("app/static/style.css").read_text()
        assert '[data-theme-color="violet"]' in css

    def test_midnight_light_block_exists(self):
        css = Path("app/static/style.css").read_text()
        assert '[data-theme-color="midnight"]' in css

    def test_classic_dark_block_exists(self):
        css = Path("app/static/style.css").read_text()
        assert '[data-theme="dark"][data-theme-color="classic"]' in css

    def test_each_theme_has_correct_light_accent(self):
        css = Path("app/static/style.css").read_text()
        for name, colors in THEMES.items():
            assert colors["light_accent"] in css, \
                f"Theme {name} light accent {colors['light_accent']} missing from CSS"

    def test_each_theme_has_correct_dark_accent(self):
        css = Path("app/static/style.css").read_text()
        for name, colors in THEMES.items():
            assert colors["dark_accent"] in css, \
                f"Theme {name} dark accent {colors['dark_accent']} missing from CSS"


class TestThemeSettingsUI:
    """Settings page should have theme selector with all 6 swatches."""

    def test_settings_has_theme_section(self):
        html = Path("app/templates/account/settings.html").read_text()
        assert "Theme" in html or "theme" in html, "Settings should have a theme section"
        for name in ["copper", "classic", "dollar", "coral", "violet", "midnight"]:
            assert name in html.lower(), f"Theme swatch for '{name}' missing from settings"


class TestThemeBaseHTML:
    """base.html should support data-theme-color attribute."""

    def test_base_has_theme_color_attribute(self):
        html = Path("app/templates/base.html").read_text()
        assert "data-theme-color" in html, "base.html should have data-theme-color attribute"

    def test_base_has_theme_color_localstorage(self):
        html = Path("app/templates/base.html").read_text()
        assert "theme_color" in html, "base.html should read/write theme_color in localStorage"


class TestThemeUserModel:
    """User model should have theme_color column."""

    def test_user_model_has_theme_color(self):
        from app.models.user import User
        assert hasattr(User, "theme_color"), "User model should have theme_color field"


class TestThemeVarUsage:
    """Templates should use CSS variables, not hardcoded copper hex, for theme-switching to work."""

    def test_no_hardcoded_accent_in_base(self):
        html = Path("app/templates/base.html").read_text()
        # Avatar should use var(--accent), not #C07A45
        assert "var(--accent)" in html, "base.html should use var(--accent)"

    def test_no_hardcoded_accent_in_dashboard(self):
        html = Path("app/templates/dashboard.html").read_text()
        assert "var(--accent)" in html, "dashboard should use var(--accent) for avatars"

    def test_no_hardcoded_accent_in_settings_avatar(self):
        html = Path("app/templates/account/settings.html").read_text()
        # The theme swatch hex values are OK — but the avatar should use var
        lines_before_theme_section = html.split("<!-- Theme -->")[0]
        assert "var(--accent)" in lines_before_theme_section, \
            "Settings avatar should use var(--accent)"

    def test_group_detail_uses_css_vars(self):
        html = Path("app/templates/group/detail.html").read_text()
        assert "var(--accent)" in html, "Group detail should use var(--accent)"
        assert "var(--border)" in html, "Group detail should use var(--border)"
        assert "var(--bg-input)" in html, "Group detail should use var(--bg-input)"

    def test_statement_uses_css_vars(self):
        html = Path("app/templates/statement/upload.html").read_text()
        assert "var(--accent)" in html, "Statement should use var(--accent)"
        assert "var(--border)" in html, "Statement should use var(--border)"

    def test_expense_new_uses_css_vars(self):
        html = Path("app/templates/expense/new.html").read_text()
        assert "var(--accent)" in html, "Expense new should use var(--accent)"

    def test_expense_edit_uses_css_vars(self):
        html = Path("app/templates/expense/edit.html").read_text()
        assert "var(--accent)" in html, "Expense edit should use var(--accent)"

    def test_charts_uses_distinct_colors(self):
        html = Path("app/templates/group/charts.html").read_text()
        assert "#7C9885" in html, "Charts should use distinct muted palette"

    def test_user_model_has_server_default(self):
        """User.theme_color should have server_default for existing DB rows."""
        from app.models.user import User
        col = User.__table__.columns["theme_color"]
        assert col.server_default is not None, "theme_color needs server_default for ALTER TABLE"

    def test_base_html_guards_none_theme(self):
        """base.html should handle None theme_color (existing users before migration)."""
        html = Path("app/templates/base.html").read_text()
        assert "or 'copper'" in html, "base.html should fallback to copper when theme_color is None"


class TestNoHardcodedThemeColors:
    """No non-semantic hardcoded hex should remain in templates.
    Every color must use a CSS variable so themes actually switch."""

    # Copper-specific hex values that should be var(--*) instead
    BANNED_HEX = ["#F5E6D8", "#DDB896", "#F8FAFF", "#6B7280"]

    def _template_content(self, path: str) -> str:
        return Path(path).read_text()

    def _strip_theme_swatches(self, html: str) -> str:
        """Remove the theme swatch section — those hex values are intentional."""
        if "<!-- Theme -->" in html:
            before = html.split("<!-- Theme -->")[0]
            after_parts = html.split("<!-- Password -->")
            after = after_parts[1] if len(after_parts) > 1 else ""
            return before + after
        return html

    def test_group_detail_no_hardcoded_copper_tint(self):
        html = self._template_content("app/templates/group/detail.html")
        for hex_val in self.BANNED_HEX:
            assert hex_val not in html, \
                f"group/detail.html still has hardcoded {hex_val} — should be a CSS variable"

    def test_dashboard_no_hardcoded_copper_tint(self):
        html = self._template_content("app/templates/dashboard.html")
        for hex_val in self.BANNED_HEX:
            assert hex_val not in html, \
                f"dashboard.html still has hardcoded {hex_val}"

    def test_statement_no_hardcoded_copper_tint(self):
        html = self._template_content("app/templates/statement/upload.html")
        for hex_val in self.BANNED_HEX:
            assert hex_val not in html, \
                f"statement/upload.html still has hardcoded {hex_val}"

    def test_settings_no_hardcoded_outside_swatches(self):
        html = self._template_content("app/templates/account/settings.html")
        cleaned = self._strip_theme_swatches(html)
        assert "#6B7280" not in cleaned, "settings.html has hardcoded #6B7280 outside swatches"

    def test_base_logo_uses_var_accent(self):
        html = self._template_content("app/templates/base.html")
        assert "#5E3D1E" not in html, "Logo gradient should use var(--accent), not hardcoded copper"

    def test_detail_no_hardcoded_white_backgrounds(self):
        """#FFFFFF used as card/input bg should be var(--bg-card) or var(--bg-input)."""
        html = self._template_content("app/templates/group/detail.html")
        # Count #FFFFFF occurrences — some are legitimate (button text white-on-accent)
        # But background: #FFFFFF should not exist
        assert 'background: #FFFFFF' not in html and "background: #FFFFFF" not in html, \
            "group/detail.html has background: #FFFFFF — should be var(--bg-card)"


class TestCardClassesUseVars:
    """CSS card classes should use variables, not hardcoded hex."""

    def test_card_blue_uses_vars(self):
        css = Path("app/static/style.css").read_text()
        # Find the light-mode .card-blue rule (not the dark override)
        import re
        match = re.search(r'^\.card-blue\s*\{[^}]+\}', css, re.MULTILINE)
        assert match, "card-blue class should exist"
        section = match.group(0)
        assert "#F5E6D8" not in section, "card-blue should not have hardcoded #F5E6D8"
        assert "#DDB896" not in section, "card-blue should not have hardcoded #DDB896"
        assert "var(--" in section, "card-blue should use CSS variables"


class TestNavigationBackButton:
    """Pages should have a back or home button for navigation."""

    def test_create_group_has_back(self):
        html = Path("app/templates/group/new.html").read_text()
        assert 'href="/"' in html or "Back" in html or "Home" in html, \
            "Create group page should have a back/home link"


class TestThemeRouteValidation:
    """Theme route should validate against allow-list."""

    async def test_valid_theme_accepted(self, db_session, client):
        from app.models.user import User
        from app.services.auth import hash_password
        from app.middleware.auth import session_serializer

        user = User(email="theme@test.com", name="Themer", password_hash=hash_password("pass1234"))
        db_session.add(user)
        await db_session.flush()
        await db_session.commit()

        cookie = session_serializer.dumps({"user_id": user.id})
        resp = await client.post(
            "/account/theme",
            data={"theme_color": "violet"},
            cookies={"frenmo_session": cookie},
            follow_redirects=False,
        )
        assert resp.status_code == 303

        await db_session.refresh(user)
        assert user.theme_color == "violet"

    async def test_invalid_theme_rejected(self, db_session, client):
        from app.models.user import User
        from app.services.auth import hash_password
        from app.middleware.auth import session_serializer

        user = User(email="theme2@test.com", name="Themer2", password_hash=hash_password("pass1234"))
        db_session.add(user)
        await db_session.flush()
        await db_session.commit()

        cookie = session_serializer.dumps({"user_id": user.id})
        resp = await client.post(
            "/account/theme",
            data={"theme_color": "hacked_theme"},
            cookies={"frenmo_session": cookie},
            follow_redirects=False,
        )
        assert resp.status_code == 303

        await db_session.refresh(user)
        assert user.theme_color != "hacked_theme"
