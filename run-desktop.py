"""
Clyre API launcher.
Starts the FastAPI server, and also runs any necessary startup side effects (downloading files, starting llama.cpp server, etc.)

Usage:
    poetry run python run-desktop.py
"""

import os
import sys
from pathlib import Path

from scripts.build_db_url import build_database_url
from scripts.downloader import from_files
from scripts.llama_launcher import start_llama_server
from shared.pyutils.logs import setup_logging

if __name__ == "__main__":
    setup_logging()
    from_files("binaries.yaml", "models.yaml")
    start_llama_server()

    # Build DATABASE_URL and export it so the API picks it up via env
    os.environ["DATABASE_URL"] = build_database_url()

    # Add api/ to sys.path so internal imports (from app, from utils, etc.) work
    api_dir = Path(__file__).parent / "api"
    sys.path.insert(0, str(api_dir))

    from api.main import main

    main()
