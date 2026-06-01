#!/usr/bin/env python3
"""tgit – top-level entry point (can be run directly with ``python tgit.py``)."""

import sys
from pathlib import Path

# Ensure the package is importable when running from the project directory
sys.path.insert(0, str(Path(__file__).parent))

from tgit.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
