"""Entry point used by PyInstaller.

``mediafilter/__main__.py`` uses a relative import, which only works under
``python -m mediafilter``. A frozen app needs a top-level script instead.
"""

from __future__ import annotations

import sys

from mediafilter.app import run

if __name__ == "__main__":
    sys.exit(run())