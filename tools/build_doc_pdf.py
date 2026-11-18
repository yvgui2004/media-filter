"""Render 使用文档.md to a styled A4 PDF via headless Edge.

Usage: python tools/build_doc_pdf.py [input.md] [output.pdf]
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parents[1]
EDGE_CANDIDATES = (
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
)

CSS = """
@page { size: A4; margin: 15mm 14mm 16mm 14mm; }
* { box-sizing: border-box; }
body {
  font-family: "Microsoft YaHei", "微软雅黑", "Segoe UI", sans-serif;
  font-size: 9.8pt; line-height: 1.46; color: #333; margin: 0;
  -webkit-print-color-adjust: exact; print-color-adjust: exact;
}
h1 { color: #00A6A7; font-size: 21pt; margin: 0 0 6px; padding-bottom: 8px;
     border-bottom: 2.5px solid #00A6A7; letter-spacing: 0.5px; }
h2 { color: #00898a; font-size: 13.4pt; margin: 14px 0 6px; padding: 3px 8px;
     border-left: 5px solid #00A6A7; background: #F1FAFA;
     break-after: avoid; page-break-after: avoid; }
h3 { color: #333; font-size: 11.4pt; margin: 12px 0 4px;
     break-after: avoid; page-break-after: avoid; }
p { margin: 4px 0; }
p:has(+ pre), ul:has(+ pre), ol:has(+ pre),
p:has(+ table), p:has(+ ul), p:has(+ ol),
h1, h2, h3 { break-after: avoid; page-break-after: avoid; }
h1 + *, h2 + *, h3 + * { break-before: avoid; page-break-before: avoid; }
ul, ol { margin: 4px 0 7px; padding-left: 22px; }
li { margin: 1.5px 0; }
blockquote { margin: 8px 0; padding: 2px 12px; border-left: 3px solid #9fd8d9;
             color: #666; background: #fafefe; }
table { border-collapse: collapse; width: 100%; margin: 8px 0 12px;
        font-size: 9.3pt; break-inside: auto; }
th, td { border: 1px solid #d5d9dd; padding: 4px 7px; vertical-align: top; }
th { background: #F1FAFA; color: #006f70; font-weight: 700; text-align: left; }
tr { break-inside: avoid; }
code { font-family: Consolas, "Cascadia Mono", monospace; font-size: 9pt;
       background: #f3f5f7; padding: 1px 4px; border-radius: 3px; color: #b5312f; }
pre { background: #f7f9fa; border: 1px solid #e2e6e9; border-radius: 5px;
      padding: 9px 12px; margin: 7px 0 8px; white-space: pre-wrap;
      overflow-wrap: break-word; break-inside: avoid; page-break-inside: avoid; }
pre code { background: none; padding: 0; color: #333; font-size: 8.3pt; line-height: 1.42; }
hr { border: none; border-top: 1px solid #e5e8ea; margin: 12px 0; }
a { color: #00898a; text-decoration: none; }
strong { color: #222; }
"""


KEEP_SCRIPT = """
<script>
// Chromium ignores break-after:avoid between a heading and a list/table,
// so wrap the heading together with its first following block.
document.querySelectorAll('h1, h2, h3').forEach(function (h) {
  var next = h.nextElementSibling;
  if (!next) return;
  var tag = next.tagName;
  if (tag === 'UL' || tag === 'OL') {
    if (next.children.length > 8) return;   // never make a long list unbreakable
  } else if (tag !== 'PRE' && tag !== 'TABLE' && tag !== 'P') {
    return;
  }
  var box = document.createElement('div');
  box.style.breakInside = 'avoid';
  box.style.pageBreakInside = 'avoid';
  h.parentNode.insertBefore(box, h);
  box.appendChild(h);
  box.appendChild(next);
});
</script>
"""


def build_html(md_text: str) -> str:
    body = markdown.markdown(
        md_text,
        extensions=["tables", "fenced_code", "sane_lists", "nl2br"],
    )
    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>media-filter-ai 使用文档</title>
<style>{CSS}</style></head><body>{body}{KEEP_SCRIPT}</body></html>"""


def find_edge() -> Path:
    for p in EDGE_CANDIDATES:
        if p.is_file():
            return p
    raise SystemExit("Microsoft Edge not found")


def stamp_footer(pdf: Path) -> None:
    """Add a centered 'page x / n' footer using a built-in CJK font."""
    try:
        import pymupdf
    except ImportError:  # footers are cosmetic; skip when unavailable
        return
    doc = pymupdf.open(pdf)
    total = doc.page_count
    doc.set_metadata({"title": "media-filter-ai 使用文档", "creator": "build_doc_pdf.py"})
    for i, page in enumerate(doc, start=1):
        w, h = page.rect.width, page.rect.height
        page.insert_textbox(
            pymupdf.Rect(0, h - 30, w, h - 12),
            f"media-filter-ai 使用文档  ·  {i} / {total}",
            fontsize=8,
            fontname="china-s",
            color=(0.6, 0.63, 0.65),
            align=pymupdf.TEXT_ALIGN_CENTER,
        )
    doc.saveIncr()
    doc.close()


def main() -> int:
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "使用文档.md"
    dst = Path(sys.argv[2]) if len(sys.argv) > 2 else src.with_suffix(".pdf")
    src, dst = src.resolve(), dst.resolve()
    if not src.is_file():
        raise SystemExit(f"missing {src}")

    html = build_html(src.read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory() as tmp:
        html_path = Path(tmp) / "doc.html"
        html_path.write_text(html, encoding="utf-8")
        cmd = [
            str(find_edge()),
            "--headless=new",
            "--disable-gpu",
            f"--user-data-dir={Path(tmp) / 'profile'}",
            "--no-pdf-header-footer",
            "--virtual-time-budget=8000",
            f"--print-to-pdf={dst}",
            html_path.as_uri(),
        ]
        proc = subprocess.run(cmd, capture_output=True, timeout=180)
        stderr = proc.stderr.decode("utf-8", "replace")
        if not dst.is_file():
            print(f"edge exited {proc.returncode}")
            print(stderr[-2000:])
            raise SystemExit("PDF generation failed")
    stamp_footer(dst)
    print(f"written {dst} ({dst.stat().st_size / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())