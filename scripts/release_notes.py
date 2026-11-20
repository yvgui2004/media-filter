"""Write release notes for a version.

Prefers a hand-written ``docs/releases/v<version>.md``; otherwise extracts the
matching section from ``CHANGELOG.md``. Appends the asset name and SHA-256 so a
release page is self-verifying.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def changelog_section(text: str, version: str) -> str:
    pattern = re.compile(
        rf"^## \[{re.escape(version)}\][^\n]*\n(.*?)(?=^## \[|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(text)
    return match.group(1).strip() if match else ""


def build_notes(version: str, asset: str, sha256: str) -> str:
    hand_written = ROOT / "docs" / "releases" / f"v{version}.md"
    if hand_written.is_file():
        body = hand_written.read_text(encoding="utf-8").strip()
    else:
        body = changelog_section(
            (ROOT / "CHANGELOG.md").read_text(encoding="utf-8"), version
        )
        if not body:
            raise SystemExit(f"No release notes found for {version}")
        body = f"# Media Filter {version}\n\n{body}"

    if sha256 and sha256 not in body:
        body += (
            "\n\n---\n\n"
            f"**Asset / 文件**: `{asset}`\n\n"
            f"**SHA-256**:\n\n```text\n{sha256}\n```\n"
        )
    return body + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--asset", default="")
    parser.add_argument("--sha256", default="")
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    args.out.write_text(
        build_notes(args.version, args.asset, args.sha256), encoding="utf-8"
    )
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())