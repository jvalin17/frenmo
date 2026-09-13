"""Test that base template includes a keepalive heartbeat to prevent server idle spindown."""
from pathlib import Path


def test_base_template_has_keepalive_ping():
    """base.html should ping /health periodically to keep Render from spinning down."""
    template = Path("app/templates/base.html").read_text()
    assert "setInterval" in template, "Missing setInterval for keepalive"
    assert "/health" in template, "Keepalive should ping /health endpoint"
