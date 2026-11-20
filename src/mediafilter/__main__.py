"""Entry point: ``python -m mediafilter [folder]`` or the ``mediafilter`` script."""

from __future__ import annotations

import argparse
import sys

from .app import run


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="mediafilter",
        description="Desktop media browser: scan, tag, and batch-transcode.",
    )
    parser.add_argument(
        "folder",
        nargs="?",
        help="folder to scan on launch (same as opening it from the window)",
    )
    args = parser.parse_args()
    sys.exit(run(args.folder))


if __name__ == "__main__":
    main()