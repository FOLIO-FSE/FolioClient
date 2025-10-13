"""
Pytest configuration for FolioClient tests.
"""

import pytest


def pytest_addoption(parser):
    """Add command line option to enable integration tests."""
    parser.addoption(
        "--run-integration",
        action="store_true",
        default=False,
        help="Run integration tests against FOLIO snapshot",
    )
    parser.addoption(
        "--integration-server",
        action="store",
        default=None,
        help="Limit integration tests to a single server config name"
    )

def pytest_collection_modifyitems(config, items):
    """Skip integration tests unless --run-integration is passed."""
    if config.getoption("--run-integration"):
        return
    
    skip_integration = pytest.mark.skip(reason="need --run-integration option to run")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip_integration)