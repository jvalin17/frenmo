"""Tests that .person-row CSS lives in style.css, not duplicated in templates."""
from pathlib import Path


class TestPersonRowInStyleCSS:
    """person-row styles must be in style.css, not inline in templates."""

    def test_person_row_in_style_css(self):
        css = Path("app/static/style.css").read_text()
        assert ".person-row" in css, \
            ".person-row must be defined in style.css, not inline in templates"

    def test_no_person_row_style_block_in_new(self):
        html = Path("app/templates/expense/new.html").read_text()
        # person-row class can be USED in HTML, but should not be DEFINED in a <style> block
        style_blocks = html.split("<style>")
        for block in style_blocks[1:]:  # skip content before first <style>
            style_content = block.split("</style>")[0]
            assert ".person-row" not in style_content, \
                "expense/new.html must not define .person-row in inline <style> — move to style.css"

    def test_no_person_row_style_block_in_edit(self):
        html = Path("app/templates/expense/edit.html").read_text()
        style_blocks = html.split("<style>")
        for block in style_blocks[1:]:
            style_content = block.split("</style>")[0]
            assert ".person-row" not in style_content, \
                "expense/edit.html must not define .person-row in inline <style> — move to style.css"
