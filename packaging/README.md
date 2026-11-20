# Packaging / 打包与分发

## Portable release / 便携版

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

To publish a version:

1. Sign in to GitHub as the package publisher.
2. Fork `microsoft/winget-pkgs`.
3. Copy `packaging/winget/yvgui2004.MediaFilter/<version>/` to
   `manifests/y/yvgui2004/MediaFilter/<version>/` in the fork.
4. Open a pull request. Accept the Microsoft CLA when the bot asks.
5. After merge, `winget install yvgui2004.MediaFilter` works.

The manifest is intentionally not submitted yet: the repository owner must open
the PR and accept the CLA under their own account.

## Scoop

`packaging/scoop/media-filter.json` is a ready manifest. A Scoop bucket is just a
GitHub repository containing a `bucket/` folder; to publish:

1. Create `<owner>/scoop-bucket` with `bucket/media-filter.json`.
2. `scoop bucket add <owner> https://github.com/<owner>/scoop-bucket`
3. `scoop install <owner>/media-filter`

`checkver` / `autoupdate` in the manifest follow new GitHub releases
automatically once the bucket is added.