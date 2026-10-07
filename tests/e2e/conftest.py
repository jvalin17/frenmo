"""E2E conftest — override root conftest's async fixtures for sync Playwright tests."""
import pytest


@pytest.fixture(autouse=True)
def setup_database():
    """Override the root conftest's async setup_database — e2e tests use the live app."""
    yield
