"""Text documents via pandoc: docx, odt, rtf, html, md, txt, epub, tex, rst, ipynb."""
from __future__ import annotations

from pathlib import Path

from .engine import register
from .util import pandoc_path, run

READERS = {
    "md": "markdown", "html": "html", "docx": "docx", "odt": "odt",
    "rtf": "rtf", "epub": "epub", "txt": "markdown+hard_line_breaks",
    "tex": "latex", "rst": "rst", "ipynb": "ipynb",
}
WRITERS = {
    "md": "gfm", "html": "html5", "docx": "docx", "odt": "odt",
    "rtf": "rtf", "epub": "epub3", "txt": "plain", "tex": "latex",
    "rst": "rst", "ipynb": "ipynb",
}
# Formats that keep pictures as separate files next to the output.
EXTRACT_MEDIA = {"md", "rst", "tex"}


def _pandoc(src: Path, dst: Path) -> list[Path]:
    s_fmt, d_fmt = src.suffix[1:].lower(), dst.suffix[1:].lower()
    s_fmt = {"htm": "html", "markdown": "md", "text": "txt"}.get(s_fmt, s_fmt)
    d_fmt = {"htm": "html", "markdown": "md", "text": "txt"}.get(d_fmt, d_fmt)
    writer = WRITERS[d_fmt]
    if s_fmt == "html" and d_fmt == "md":
        writer = "gfm-raw_html"          # drop web-page layout junk
    cmd = [pandoc_path(), str(src), "-f", READERS[s_fmt], "-t", writer,
           "-o", str(dst), "--resource-path", str(src.parent)]
    if d_fmt in ("html", "tex", "rtf"):
        cmd.append("--standalone")
    if d_fmt == "html":
        cmd += ["--embed-resources", "--metadata", f"pagetitle={src.stem}"]
    if d_fmt == "epub":
        cmd += ["--metadata", f"title={src.stem}"]
    if d_fmt in EXTRACT_MEDIA and s_fmt in ("docx", "odt", "epub", "ipynb"):
        cmd.append(f"--extract-media={dst.stem}_media")
    if d_fmt in ("txt", "md", "rst"):
        cmd += ["--wrap=none"]
    run(cmd, cwd=dst.parent)
    return [dst]


_ok = lambda: pandoc_path() is not None  # noqa: E731
register([r for r in READERS if r != "txt"], WRITERS.keys(), _pandoc, name="pandoc",
         cost=10, available=_ok)
# Plain text has no structure, so prefer richer routes (e.g. pdf -> docx -> md).
register(["txt"], WRITERS.keys(), _pandoc, name="pandoc", cost=12, available=_ok)
