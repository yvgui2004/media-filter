# Security policy / 安全说明

## Supported versions / 支持版本

Only the latest release receives security fixes.

| Version | Supported |
| --- | --- |
| 0.1.x | ✅ |

## Reporting / 报告方式

Please **do not** open a public issue for security problems. Use GitHub's private
vulnerability reporting: **Security → Advisories → Report a vulnerability** on
<https://github.com/yvgui2004/media-filter>.

请**不要**在公开 issue 里报告安全问题，改用仓库的 **Security → Advisories →
Report a vulnerability** 私密上报。

Useful details: affected version, Windows version, reproduction steps, and the
tail of `%LOCALAPPDATA%\media-filter-v2\mediafilter.log`. The app masks API keys
in logs, but check attachments before uploading them.

## What is in scope / 范围

- The application source in `src/`.
- The portable release (`MediaFilter.exe` and bundled files).

Third-party components (FFmpeg, Ultralytics YOLOv8, Qt / PySide6) should be
reported upstream; their licenses and sources are listed in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Design notes / 设计说明

- The cloud API key is encrypted with Windows DPAPI for the current user and is
  never written to logs, exports or error messages.
- Scanning and local tagging are offline. Cloud / hybrid modes send selected
  frames only after the user confirms the upload card.
- No telemetry is collected.

## Response / 响应

Reports are usually acknowledged within a few days. Once a fix ships, the
advisory is published with credit unless you prefer to stay anonymous.