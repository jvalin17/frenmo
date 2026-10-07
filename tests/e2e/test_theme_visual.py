"""Playwright E2E tests: validate theme colors visually + take screenshots.

Run: .venv/bin/python3 -m pytest tests/e2e/test_theme_visual.py -v --headed (to watch)
Run: .venv/bin/python3 -m pytest tests/e2e/test_theme_visual.py -v (headless, default)

Screenshots saved to: tests/e2e/screenshots/
"""
import os
import re

import pytest
from playwright.sync_api import sync_playwright

BASE_URL = os.environ.get("TEST_BASE_URL", "http://localhost:8040")
SCREENSHOT_DIR = os.path.join(os.path.dirname(__file__), "screenshots")

THEMES = {
    "sand":   {"accent": "#B8860B", "accent_rgb": (184, 134, 11)},
    "navy":   {"accent": "#1E3A5F", "accent_rgb": (30, 58, 95)},
    "teal":   {"accent": "#1A5C5A", "accent_rgb": (26, 92, 90)},
    "maroon": {"accent": "#6B1D2A", "accent_rgb": (107, 29, 42)},
    "sunset": {"accent": "#8B5E1A", "accent_rgb": (139, 94, 26)},
    "purple": {"accent": "#4A2072", "accent_rgb": (74, 32, 114)},
}


def rgb_to_tuple(rgb_string):
    """Parse 'rgb(R, G, B)' or 'rgba(R, G, B, A)' to (R, G, B)."""
    match = re.search(r'rgba?\((\d+),\s*(\d+),\s*(\d+)', rgb_string)
    if match:
        return (int(match.group(1)), int(match.group(2)), int(match.group(3)))
    return None


def color_close(actual_rgb, expected_rgb, tolerance=15):
    """Check if two RGB tuples are within tolerance."""
    if actual_rgb is None:
        return False
    return all(abs(a - e) <= tolerance for a, e in zip(actual_rgb, expected_rgb))


@pytest.fixture(scope="module")
def browser_context():
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        page = context.new_page()

        # Login
        page.goto(f"{BASE_URL}/auth/login")
        page.fill('input[name="email"]', "demo@frenmo.app")
        page.fill('input[name="password"]', "demo1234")
        page.click('button[type="submit"]')
        page.wait_for_url(f"{BASE_URL}/**")

        yield page

        context.close()
        browser.close()


class TestThemeSwitching:
    """Each theme swatch should switch the accent color immediately."""

    @pytest.mark.parametrize("theme_name", list(THEMES.keys()))
    def test_theme_applies_accent_color(self, browser_context, theme_name):
        page = browser_context
        theme = THEMES[theme_name]

        # Go to account settings
        page.goto(f"{BASE_URL}/account")
        page.wait_for_load_state("networkidle")

        # Click the theme swatch
        with page.expect_navigation():
            page.evaluate(f"document.querySelector('input[name=\"theme_color\"][value=\"{theme_name}\"]').click()")
        page.wait_for_load_state("networkidle")

        # Verify data-theme-color attribute is set
        theme_attr = page.evaluate("document.documentElement.getAttribute('data-theme-color')")
        assert theme_attr == theme_name, f"Expected data-theme-color='{theme_name}', got '{theme_attr}'"

        # Check the navbar logo uses the accent color
        accent_element = page.locator('span[style*="var(--accent)"]').first
        if accent_element.count() > 0:
            color = accent_element.evaluate("el => getComputedStyle(el).color")
            actual_rgb = rgb_to_tuple(color)
            assert color_close(actual_rgb, theme["accent_rgb"]), \
                f"Theme '{theme_name}': expected accent ~{theme['accent_rgb']}, got {actual_rgb} ({color})"

        # Take screenshot
        page.screenshot(path=os.path.join(SCREENSHOT_DIR, f"settings_{theme_name}_light.png"))


class TestThemeDarkMode:
    """Each theme should also work in dark mode."""

    @pytest.mark.parametrize("theme_name", list(THEMES.keys()))
    def test_dark_mode_renders(self, browser_context, theme_name):
        page = browser_context

        # Set theme
        page.goto(f"{BASE_URL}/account")
        page.wait_for_load_state("networkidle")
        with page.expect_navigation():
            page.evaluate(f"document.querySelector('input[name=\"theme_color\"][value=\"{theme_name}\"]').click()")
        page.wait_for_load_state("networkidle")

        # Toggle dark mode
        page.evaluate("document.documentElement.setAttribute('data-theme', 'dark'); localStorage.setItem('theme', 'dark');")
        page.wait_for_timeout(300)

        # Verify dark mode is applied
        bg_color = page.evaluate("getComputedStyle(document.body).backgroundColor")
        bg_rgb = rgb_to_tuple(bg_color)
        # Dark mode backgrounds should be dark (R+G+B < 150)
        assert bg_rgb is not None, "Could not read body background color"
        brightness = sum(bg_rgb)
        assert brightness < 150, f"Theme '{theme_name}' dark mode bg too bright: {bg_rgb} (sum={brightness})"

        # Take screenshot
        page.screenshot(path=os.path.join(SCREENSHOT_DIR, f"settings_{theme_name}_dark.png"))

        # Reset to light mode for next test
        page.evaluate("document.documentElement.setAttribute('data-theme', 'light'); localStorage.setItem('theme', 'light');")


class TestThemeOnGroupPage:
    """Theme should apply consistently on the group detail page."""

    @pytest.mark.parametrize("theme_name", ["sand", "navy", "teal"])
    def test_group_page_theme_consistency(self, browser_context, theme_name):
        page = browser_context

        # Set theme first
        page.goto(f"{BASE_URL}/account")
        page.wait_for_load_state("networkidle")
        with page.expect_navigation():
            page.evaluate(f"document.querySelector('input[name=\"theme_color\"][value=\"{theme_name}\"]').click()")
        page.wait_for_load_state("networkidle")

        # Navigate to group page
        page.goto(f"{BASE_URL}/groups/1")
        page.wait_for_load_state("networkidle")

        # Verify theme attribute persists
        theme_attr = page.evaluate("document.documentElement.getAttribute('data-theme-color')")
        assert theme_attr == theme_name, f"Theme didn't persist to group page: got '{theme_attr}'"

        # Check an element with accent background color exists
        accent_var = page.evaluate(
            "getComputedStyle(document.documentElement).getPropertyValue('--accent').trim()"
        )
        assert accent_var != "", f"--accent CSS variable is empty on group page for '{theme_name}'"

        # Screenshot
        page.screenshot(path=os.path.join(SCREENSHOT_DIR, f"group_{theme_name}_light.png"))


class TestDashboardTheme:
    """Dashboard hero card should follow theme."""

    @pytest.mark.parametrize("theme_name", ["sand", "navy", "purple"])
    def test_dashboard_hero_follows_theme(self, browser_context, theme_name):
        page = browser_context

        # Set theme
        page.goto(f"{BASE_URL}/account")
        page.wait_for_load_state("networkidle")
        with page.expect_navigation():
            page.evaluate(f"document.querySelector('input[name=\"theme_color\"][value=\"{theme_name}\"]').click()")
        page.wait_for_load_state("networkidle")

        # Go to dashboard
        page.goto(f"{BASE_URL}/")
        page.wait_for_load_state("networkidle")

        # Verify no old theme name in the HTML attribute
        theme_attr = page.evaluate("document.documentElement.getAttribute('data-theme-color')")
        old_names = {"copper", "classic", "dollar", "coral", "violet", "midnight"}
        assert theme_attr not in old_names, f"Old theme name '{theme_attr}' still rendered on dashboard"
        assert theme_attr == theme_name

        # Screenshot
        page.screenshot(path=os.path.join(SCREENSHOT_DIR, f"dashboard_{theme_name}_light.png"))
