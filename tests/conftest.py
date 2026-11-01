"""Shared test fixtures/config.

Note: mediafilter is installed in editable mode, so tests import it directly.
"""

import os

# Qt core model tests below need no display, but staying offscreen is harmless.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")