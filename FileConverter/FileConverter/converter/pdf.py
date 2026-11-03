"""PDF in and out, plus LibreOffice for high-fidelity Office conversions."""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from .engine import ConversionError, register
from .util import run, soffice_path


def _has(module: str) -> bool:
    try:
        __import__(module)
        return True
    except Exception:
        return False


# ------------------------------------------------------------ PDF -> text
def pdf_to_txt(src: Path, dst: Path) -> list[Path]:
    from pypdf import PdfReader
    reader = PdfReader(str(src))
    if reader.is_encrypted:
        try:
            reader.decrypt("")
        except Exception:
            raise ConversionError("This PDF is password-protected.")
    pages = [(p.extract_text() or "").strip() for p in reader.pages]
    text = "\n\n".join(pages).strip()
    if not text:
        raise ConversionError("No text found in this PDF (it may be a scan / image-only).")
    dst.write_text(text + "\n", encoding="utf-8")
    return [dst]


# ------------------------------------------------------------ PDF -> Word
def pdf_to_docx(src: Path, dst: Path) -> list[Path]:
    if _has("pdf2docx"):  # keeps layout, tables, images
        from pdf2docx import Converter
        cv = Converter(str(src))
        try:
            cv.convert(str(dst))
        finally:
            cv.close()
        return [dst]
    # Fallback: text only, one paragraph per text block
    from docx import Document
    from pypdf import PdfReader
    doc = Document()
    reader = PdfReader(str(src))
    for i, page in enumerate(reader.pages):
        if i:
            doc.add_page_break()
        for block in (page.extract_text() or "").split("\n\n"):
            if block.strip():
                doc.add_paragraph(" ".join(block.split("\n")))
    doc.save(str(dst))
    return [dst]


# ------------------------------------------------------------ PDF -> images
def _pdf_to_image(src: Path, dst: Path, dpi: int = 150) -> list[Path]:
    import pypdfium2 as pdfium
    pdf = pdfium.PdfDocument(str(src))
    outs = []
    n = len(pdf)
    fmt = dst.suffix[1:].lower()
    for i in range(n):
        img = pdf[i].render(scale=dpi / 72).to_pil()
        out = dst if n == 1 else dst.with_name(f"{dst.stem}_page{i + 1:03d}{dst.suffix}")
        if fmt in ("jpg", "jpeg", "bmp"):
            img = img.convert("RGB")
        img.save(out, quality=92) if fmt in ("jpg", "jpeg", "webp") else img.save(out)
        outs.append(out)
    pdf.close()
    return outs


# ------------------------------------------------------------ HTML -> PDF
def html_to_pdf(src: Path, dst: Path) -> list[Path]:
    from .pdfrender import html_to_pdf as render
    return render(src, dst)


# ------------------------------------------------------------ LibreOffice
def _libreoffice(src: Path, dst: Path) -> list[Path]:
    target = dst.suffix[1:].lower()
    profile = Path(tempfile.gettempdir()) / "fileconv_lo_profile"
    with tempfile.TemporaryDirectory(prefix="fileconv_lo_") as out:
        run([soffice_path(), f"-env:UserInstallation={profile.as_uri()}",
             "--headless", "--norestore", "--convert-to", target,
             "--outdir", out, str(src)], timeout=300)
        produced = Path(out) / f"{src.stem}.{target}"
        if not produced.exists():
            raise ConversionError("LibreOffice produced no output (is the file damaged?)")
        shutil.move(str(produced), str(dst))
    return [dst]


register(["pdf"], ["txt"], pdf_to_txt, name="pypdf", cost=10,
         available=lambda: _has("pypdf"))
register(["pdf"], ["docx"], pdf_to_docx,
         name="pdf2docx" if _has("pdf2docx") else "python-docx (text only)",
         cost=10, available=lambda: _has("docx") or _has("pdf2docx"))
register(["pdf"], ["png", "jpg", "webp", "bmp", "tiff"], _pdf_to_image, name="pdfium",
         cost=10, terminal=True, available=lambda: _has("pypdfium2") and _has("PIL"))
register(["html"], ["pdf"], html_to_pdf, name="ReportLab", cost=12,
         available=lambda: _has("reportlab") and _has("bs4"))

_lo = lambda: soffice_path() is not None  # noqa: E731
register(["docx", "doc", "odt", "rtf", "pptx", "ppt", "odp", "xlsx", "xls", "ods"],
         ["pdf"], _libreoffice, name="LibreOffice", cost=5, available=_lo)
register(["doc"], ["docx", "odt"], _libreoffice, name="LibreOffice", cost=5, available=_lo)
register(["ppt", "odp"], ["pptx"], _libreoffice, name="LibreOffice", cost=5, available=_lo)
register(["pptx"], ["odp"], _libreoffice, name="LibreOffice", cost=5, available=_lo)
register(["xls", "ods"], ["xlsx"], _libreoffice, name="LibreOffice", cost=5, available=_lo)
register(["xlsx"], ["ods"], _libreoffice, name="LibreOffice", cost=5, available=_lo)
