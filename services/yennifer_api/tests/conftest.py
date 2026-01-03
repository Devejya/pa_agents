"""
Pytest configuration for Yennifer API tests.

This file sets up the Python path so tests can import from the app module.
"""

import sys
from pathlib import Path

import pytest

# Add the yennifer_api directory to Python path so 'app' module can be found
yennifer_api_dir = Path(__file__).parent.parent
sys.path.insert(0, str(yennifer_api_dir))


# Configure pytest-asyncio
pytest_plugins = ('pytest_asyncio',)


@pytest.fixture(scope="session")
def event_loop_policy():
    """Use default event loop policy."""
    import asyncio
    return asyncio.DefaultEventLoopPolicy()

