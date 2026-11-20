"""Open a winget-pkgs pull request for a released version.

Called by the release workflow when ``WINGET_TOKEN`` is configured. Without a
token it prints a notice and exits 0, so releases still work manually.

``WINGET_TOKEN`` must be a classic PAT with the ``public_repo`` scope belonging
to the package owner (yvgui2004). The PR needs the owner to have accepted the
Microsoft CLA once; later versions reuse that agreement.

Usage:
    python scripts/winget_submit.py --version 0.1.2 \
        --url https://github.com/.../MediaFilter-0.1.2-win64.zip \
        --sha256 <hash>
    python scripts/winget_submit.py ... --dry-run   # print manifests only
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import time
import urllib.error
import urllib.request
from typing import Any

API = "https://api.github.com"
PACKAGE_ID = "yvgui2004.MediaFilter"
PUBLISHER = "yvgui2004"
UPSTREAM = "microsoft/winget-pkgs"
MANIFEST_VERSION = "1.28.0"


def _request(method: str, path: str, token: str, payload=None) -> tuple[int, Any]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        API + path,
        method=method,
        data=data,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "media-filter-release",
            "X-GitHub-Api-Version": "2022-11-28",
            **({"Content-Type": "application/json"} if data else {}),
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            body = response.read()
            return response.status, json.loads(body) if body else None
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return 404, None
        raise RuntimeError(f"{method} {path} -> {exc.code}: {exc.read()[:400]!r}") from exc


def manifests(version: str, url: str, sha256: str) -> dict[str, str]:
    folder = f"MediaFilter-{version}-win64"
    version_yaml = f"""# yaml-language-server: $schema=https://aka.ms/winget-manifest.version.1.28.0.schema.json
PackageIdentifier: {PACKAGE_ID}
PackageVersion: {version}
DefaultLocale: en-US
ManifestType: version
ManifestVersion: {MANIFEST_VERSION}
"""
    installer_yaml = f"""# yaml-language-server: $schema=https://aka.ms/winget-manifest.installer.1.28.0.schema.json
PackageIdentifier: {PACKAGE_ID}
PackageVersion: {version}
Platform:
  - Windows.Desktop
MinimumOSVersion: 10.0.17763.0
InstallerType: zip
NestedInstallerType: portable
NestedInstallerFiles:
  - RelativeFilePath: {folder}\\MediaFilter.exe
    PortableCommandAlias: mediafilter
Installers:
  - Architecture: x64
    InstallerUrl: {url}
    InstallerSha256: {sha256.upper()}
ManifestType: installer
ManifestVersion: {MANIFEST_VERSION}
"""
    locale_yaml = f"""# yaml-language-server: $schema=https://aka.ms/winget-manifest.defaultLocale.1.28.0.schema.json
PackageIdentifier: {PACKAGE_ID}
PackageVersion: {version}
PackageLocale: en-US
Publisher: {PUBLISHER}
PublisherUrl: https://github.com/{PUBLISHER}
PublisherSupportUrl: https://github.com/{PUBLISHER}/media-filter/issues
PackageName: Media Filter
PackageUrl: https://github.com/{PUBLISHER}/media-filter
License: MIT
LicenseUrl: https://github.com/{PUBLISHER}/media-filter/blob/master/LICENSE
Copyright: Copyright (c) 2026 {PUBLISHER}
ShortDescription: Local-first AI video organizer for Windows with batch FFmpeg.
Description: >-
  Scan a folder, tag video and audio with local YOLOv8n or any OpenAI-compatible
  vision model, filter by content, and turn the selection into batch FFmpeg
  commands. Scanning and local tagging stay offline; the API key is encrypted
  with Windows DPAPI.
Moniker: mediafilter
Tags:
  - video
  - ffmpeg
  - ai
  - tagging
  - media
  - organizer
  - transcoding
ReleaseNotesUrl: https://github.com/{PUBLISHER}/media-filter/releases/tag/v{version}
ManifestType: defaultLocale
ManifestVersion: {MANIFEST_VERSION}
"""
    return {
        f"{PACKAGE_ID}.yaml": version_yaml,
        f"{PACKAGE_ID}.installer.yaml": installer_yaml,
        f"{PACKAGE_ID}.locale.en-US.yaml": locale_yaml,
    }


def submit(version: str, url: str, sha256: str, token: str) -> str:
    status, user = _request("GET", "/user", token)
    login = (user or {}).get("login", "")
    if login.lower() != PUBLISHER.lower():
        raise RuntimeError(
            f"WINGET_TOKEN belongs to {login}, but the package owner is {PUBLISHER}"
        )

    # 1. Make sure the fork exists and is ready.
    status, _ = _request("GET", f"/repos/{login}/{UPSTREAM.split('/')[1]}", token)
    if status == 404:
        _request("POST", f"/repos/{UPSTREAM}/forks", token, {})
    for _ in range(30):
        status, _ = _request("GET", f"/repos/{login}/{UPSTREAM.split('/')[1]}", token)
        if status == 200:
            break
        time.sleep(4)
    else:
        raise RuntimeError("fork did not become available")

    # 2. Branch from the fork's master.
    status, ref = _request(
        "GET", f"/repos/{login}/{UPSTREAM.split('/')[1]}/git/ref/heads/master", token
    )
    if status != 200 or not ref:
        raise RuntimeError("cannot read fork master")
    branch = f"mediafilter-{version}"
    status, _ = _request(
        "GET", f"/repos/{login}/{UPSTREAM.split('/')[1]}/git/ref/heads/{branch}", token
    )
    if status == 404:
        _request(
            "POST",
            f"/repos/{login}/{UPSTREAM.split('/')[1]}/git/refs",
            token,
            {"ref": f"refs/heads/{branch}", "sha": ref["object"]["sha"]},
        )

    # 3. Upload the three manifest files.
    base_dir = f"manifests/{PACKAGE_ID[0].lower()}/{PUBLISHER}/MediaFilter/{version}"
    for name, text in manifests(version, url, sha256).items():
        path = f"/repos/{login}/{UPSTREAM.split('/')[1]}/contents/{base_dir}/{name}"
        payload: dict[str, str] = {
            "message": f"Add {PACKAGE_ID} version {version}",
            "content": base64.b64encode(text.encode("utf-8")).decode("ascii"),
            "branch": branch,
        }
        status, existing = _request("GET", f"{path}?ref={branch}", token)
        if status == 200 and existing:
            payload["sha"] = existing["sha"]
        _request("PUT", path, token, payload)

    # 4. Open (or find) the pull request.
    status, pulls = _request(
        "GET",
        f"/repos/{UPSTREAM}/pulls?state=open&head={login}:{branch}",
        token,
    )
    if status == 200 and pulls:
        return pulls[0]["html_url"]

    body = f"""## 📖 Description

New package: **Media Filter {version}** (`{PACKAGE_ID}`).

Release: {url}

## ✅ Checklist

- [x] Signed the Contributor License Agreement
- [x] Linked to an issue (not applicable: new version)

## 📦 Manifest Checklist

- [x] Checked that there aren't other open pull requests for the same manifest update
- [x] This PR only modifies one (1) manifest
- [x] Validated manifest locally with `winget validate --manifest <path>`
- [x] Manifest conforms to the [1.28 schema](https://github.com/microsoft/winget-pkgs/tree/master/doc/manifest/schema/1.28.0)
"""
    status, pull = _request(
        "POST",
        f"/repos/{UPSTREAM}/pulls",
        token,
        {
            "title": f"New package: {PACKAGE_ID} version {version}",
            "head": f"{login}:{branch}",
            "base": "master",
            "body": body,
        },
    )
    if status not in (200, 201) or not pull:
        raise RuntimeError("pull request creation failed")
    return pull["html_url"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.dry_run:
        for name, text in manifests(args.version, args.url, args.sha256).items():
            print(f"--- {name} ---")
            print(text)
        return 0

    token = os.environ.get("WINGET_TOKEN") or os.environ.get("GH_TOKEN") or ""
    if not token:
        print("WINGET_TOKEN is not configured; skipping winget submission.")
        return 0

    print(submit(args.version, args.url, args.sha256, token))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())