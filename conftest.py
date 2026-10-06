"""
Pytest configuration for AgileOps Prod Console.

Adds the `python/` directory to sys.path so tests can import the
pipeline modules by their flat names (e.g. `import adapter`),
matching the module convention used by `python/main.py`.
"""

import sys
from pathlib import Path

PYTHON_DIR = Path(__file__).parent / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))