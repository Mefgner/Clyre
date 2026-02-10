"""
Clyre API launcher.
Adds api/ to sys.path and runs the backend from the project root.

Usage:
    poetry run python run.py
"""

import sys
from pathlib import Path

# Add api/ to sys.path so internal imports (from app, from utils, etc.) work
api_dir = Path(__file__).parent / "api"
sys.path.insert(0, str(api_dir))

from api.main import main  # noqa: E402

if __name__ == "__main__":
    main()
