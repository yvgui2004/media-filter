# Packaging / 打包与分发

## Automated release / 自动发布

Pushing a version tag runs `.github/workflows/release.yml`:

```powershell
# bump version in pyproject.toml and add the CHANGELOG section first
git tag v0.2.1
git push origin v0.2.1
```

The workflow checks that the tag matches `pyproject.toml`, runs pytest and
pyright, downloads the pinned FFmpeg and model inputs (verifying both SHA-256
hashes), builds the portable zip, writes the `.sha256` file and release notes,
then publishes the GitHub Release. Re-running a tag uploads over the existing
assets (`--clobber`) instead of failing.

Pinned inputs live at the top of the workflow:

- FFmpeg shared build (BtbN) with URL + SHA-256;
- `model-v1` release asset on this repository (YOLOv8n ONNX, AGPL-3.0).

To exercise the build without publishing, run the workflow manually
(**Actions → Release → Run workflow**, `dry_run` is on by default); the zip is
kept as a workflow artifact for 7 days.

### Optional: winget pull request

Add a classic GitHub PAT with the `public_repo` scope as the repository secret
`WINGET_TOKEN`. When present, the release workflow calls
`scripts/winget_submit.py`, which updates the `yvgui2004/winget-pkgs` fork and
opens a new manifest PR for the version. Without the secret the step prints a
notice and the release still succeeds; submit the manifest manually as below.

The owner must have accepted the Microsoft CLA once (done for 0.1.1).

## Manual build / 手动打包

```powershell
$env:MEDIAFILTER_FFMPEG_DIR = "C:\ffmpeg\bin"   # a shared (DLL) or static build
.venv\Scripts\python.exe packaging\build.py
```

The default Gyan "full" build is static and adds ~560 MB to the folder; use the
**essentials/shared** build (ffmpeg.exe + DLLs, ~190 MB) for releases. The script
copies every file except `ffplay.exe`, so shared builds keep working.

## Winget / winget-pkgs

The manifest lives in `packaging/winget/yvgui2004.MediaFilter/<version>/` and is
validated locally:

```powershell
winget validate --manifest packaging\winget\yvgui2004.MediaFilter\0.1.1
```

Current status: the first submission (`0.1.1`, new package) is open as
[microsoft/winget-pkgs#484604](https://github.com/microsoft/winget-pkgs/pull/484604)
and has passed validation. Submit `0.2.0` only after that PR merges — winget
rejects an update when the base package does not exist yet. Once merged, either
configure `WINGET_TOKEN` before the next tag, or run the script manually:

```powershell
$env:WINGET_TOKEN = "<classic PAT with public_repo>"
.venv\Scripts\python.exe scripts\winget_submit.py --version 0.2.0 `
  --url https://github.com/yvgui2004/media-filter/releases/download/v0.2.0/MediaFilter-0.2.0-win64.zip `
  --sha256 211331abec823fd7559e27033922557a5640444f23d75650a02900830d929566
```

## Scoop

`packaging/scoop/media-filter.json` is a ready manifest. A Scoop bucket is just a
GitHub repository containing a `bucket/` folder; to publish:

1. Create `<owner>/scoop-bucket` with `bucket/media-filter.json`.
2. `scoop bucket add <owner> https://github.com/<owner>/scoop-bucket`
3. `scoop install <owner>/media-filter`

`checkver` / `autoupdate` in the manifest follow new GitHub releases
automatically once the bucket is added.