"""Entry point for ``python -m scripts.commands.lint``."""

from __future__ import annotations

import sys

from scripts.commands.lint import main

if __name__ == "__main__":
    sys.exit(main())
