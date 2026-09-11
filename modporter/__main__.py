# Copyright (c) 2026 Remyy
# SPDX-License-Identifier: MIT
"""Allow ``python -m modporter`` execution."""
from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
