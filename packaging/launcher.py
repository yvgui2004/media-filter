"""Entry point used by PyInstaller.

``mediafilter/__main__.py`` handles argparse (including the optional folder
argument), so reuse its ``main`` instead of calling ``run()`` directly — the
frozen exe then accepts ``MediaFilter.exe D:\\footage`` exactly like
``python -m mediafilter D:\\footage``.
"""

from __future__ import annotations

from mediafilter.__main__ import main

if __name__ == "__main__":
    main()