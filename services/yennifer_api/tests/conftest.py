"""
Pytest configuration for Yennifer API tests.

This file sets up the Python path so tests can import from the app module.
"""

import sys
from pathlib import Path

# Add the yennifer_api directory to Python path so 'app' module can be found
yennifer_api_dir = Path(__file__).parent.parent
sys.path.insert(0, str(yennifer_api_dir))

