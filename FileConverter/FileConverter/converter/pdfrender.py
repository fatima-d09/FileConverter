"""
HTML -> PDF with ReportLab (pure Python, works everywhere without
Word or LibreOffice). Handles headings, paragraphs, bold/italic/links,
lists, tables, code blocks, quotes, rules and images.
"""
from __future__ import annotations

import base64
import io
import re
import sys
from html import escape
from pathlib import Path
from urllib.parse import unquote

from bs4 import BeautifulSoup, NavigableString, Tag
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (HRFlowable, Image, ListFlowable, ListItem,
                                Paragraph, Preformatted, SimpleDocTemplate,
                                Spacer, Table, TableStyle)

# ---------------------------------------------------------------- fonts
_FONT_CANDIDATES = [
    # (regular, bold, italic, bold-italic) — first family found wins
    ("C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/segoeuib.ttf",
     "C:/Windows/Fonts/segoeuii.ttf", "C:/Windows/Fonts/segoeuiz.ttf"),
    ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf",
     "C:/Windows/Fonts/ariali.ttf", "C:/Windows/Fonts/arialbi.ttf"),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
     "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
     "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf",
     "/usr/share/fonts/truetype/dejavu/DejaVuSans-BoldOblique.ttf"),
]
_MONO_CANDIDATES = ["C:/Windows/Fonts/consola.ttf",
                    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"]
_fonts: tuple[str, str] | None = None


def _setup_fonts() -> tuple[str, str]:
    """Register a Unicode TTF font so accents, Cyrillic, etc. render."""
    global _fonts
    if _fonts:
        return _fonts
    body, mono = "Helvetica", "Courier"
    for fam in _FONT_CANDIDATES:
        if all(Path(f).is_file() for f in fam):
            try:
                names = ["Body", "Body-Bold", "Body-Italic", "Body-BoldItalic"]
                for n, f in zip(names, fam):
                    pdfmetrics.registerFont(TTFont(n, f))
                pdfmetrics.registerFontFamily("Body", normal="Body", bold="Body-Bold",
                                              italic="Body-Italic", boldItalic="Body-BoldItalic")
                body = "Body"
                break
            except Exception:
                pass
    for f in _MONO_CANDIDATES:
        if Path(f).is_file():
            try:
                pdfmetrics.registerFont(TTFont("Mono", f))
                mono = "Mono"
                break
            except Exception:
                pass
    _fonts = (body, mono)
    return _fonts


# ---------------------------------------------------------------- styles
def _styles(body: str, mono: str) -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    s = {
        "p": ParagraphStyle("p", parent=base["BodyText"], fontName=body,
                            fontSize=10.5, leading=15, spaceAfter=6, alignment=TA_LEFT),
        "pre": ParagraphStyle("pre", fontName=mono, fontSize=8.5, leading=11,
                              backColor=colors.HexColor("#f4f4f4"), borderPadding=6,
                              spaceBefore=4, spaceAfter=10),
        "quote": ParagraphStyle("quote", fontName=body, fontSize=10.5, leading=15,
                                leftIndent=14, textColor=colors.HexColor("#555555"),
                                spaceAfter=6),
        "cell": ParagraphStyle("cell", fontName=body, fontSize=9, leading=12),
    }
    sizes = {1: 22, 2: 17, 3: 14, 4: 12, 5: 11, 6: 10.5}
    for lvl, size in sizes.items():
        s[f"h{lvl}"] = ParagraphStyle(f"h{lvl}", fontName=body, fontSize=size,
                                      leading=size * 1.3, spaceBefore=size * 0.7,
                                      spaceAfter=size * 0.35,
                                      textColor=colors.HexColor("#1a1a1a"))
    return s


# ---------------------------------------------------------------- inline
_INLINE_MAP = {"b": "b", "strong": "b", "i": "i", "em": "i", "u": "u",
               "s": "strike", "strike": "strike", "del": "strike",
               "sub": "sub", "sup": "super"}


def _inline(node, mono: str) -> str:
    """Convert inline HTML into ReportLab's mini-markup."""
    if isinstance(node, NavigableString):
        if node.__class__.__name__ in ("Comment", "Doctype", "Declaration"):
            return ""
        return escape(re.sub(r"\s+", " ", str(node)), quote=False)
    if not isinstance(node, Tag):
        return ""
    name = node.name
    if name in ("script", "style", "head", "title", "meta", "img", "svg"):
        return ""
    if name == "br":
        return "<br/>"
    inner = "".join(_inline(c, mono) for c in node.children)
    if not inner.strip():
        return inner
    if name in _INLINE_MAP:
        t = _INLINE_MAP[name]
        return f"<{t}>{inner}</{t}>"
    if name in ("code", "kbd", "samp", "tt"):
        return f'<font face="{mono}">{inner}</font>'
    if name == "a" and node.get("href", "").startswith(("http", "mailto")):
        href = escape(node["href"], quote=True)
        return f'<link href="{href}" color="#1a5fb4"><u>{inner}</u></link>'
    return inner


# ---------------------------------------------------------------- blocks
BLOCK_TAGS = {"p", "div", "section", "article", "main", "header", "footer",
              "nav", "aside", "figure", "figcaption", "h1", "h2", "h3", "h4",
              "h5", "h6", "ul", "ol", "li", "table", "pre", "blockquote", "hr",
              "img", "dl", "dt", "dd", "body", "html", "center", "form"}


class _Builder:
    def __init__(self, base_dir: Path, width: float):
        self.body, self.mono = _setup_fonts()
        self.st = _styles(self.body, self.mono)
        self.base_dir = base_dir
        self.width = width

    def para(self, markup: str, style: str = "p"):
        markup = markup.strip()
        if not markup or not re.sub(r"<[^>]+>", "", markup).strip():
            return []
        try:
            return [Paragraph(markup, self.st[style])]
        except Exception:  # malformed markup -> plain text
            return [Paragraph(escape(re.sub(r"<[^>]+>", "", markup)), self.st[style])]

    def image(self, tag: Tag):
        src = tag.get("src", "")
        try:
            if src.startswith("data:"):
                data = io.BytesIO(base64.b64decode(src.split(",", 1)[1]))
            else:
                p = Path(unquote(src))
                if not p.is_absolute():
                    p = self.base_dir / p
                if not p.is_file():
                    return []
                data = str(p)
            reader = ImageReader(data)
            iw, ih = reader.getSize()
            scale = min(1.0, self.width / iw, (A4[1] * 0.6) / ih)
            if isinstance(data, io.BytesIO):
                data.seek(0)
            return [Image(data, width=iw * scale, height=ih * scale), Spacer(1, 6)]
        except Exception:
            return []

    def table(self, tag: Tag):
        rows = []
        for tr in tag.find_all("tr"):
            if tr.find_parent("table") is not tag:
                continue
            cells = tr.find_all(["td", "th"], recursive=False)
            rows.append([Paragraph(_inline(c, self.mono) or "", self.st["cell"]) for c in cells])
        if not rows:
            return []
        ncol = max(len(r) for r in rows)
        rows = [r + [""] * (ncol - len(r)) for r in rows]
        t = Table(rows, colWidths=[self.width / ncol] * ncol, repeatRows=1)
        has_header = bool(tag.find("th"))
        style = [("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#bbbbbb")),
                 ("VALIGN", (0, 0), (-1, -1), "TOP"),
                 ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]
        if has_header:
            style.append(("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#ececec")))
        t.setStyle(TableStyle(style))
        return [t, Spacer(1, 8)]

    def lst(self, tag: Tag):
        items = []
        for li in tag.find_all("li", recursive=False):
            flow = self.blocks(li)
            if flow:
                items.append(ListItem(flow, leftIndent=14))
        if not items:
            return []
        if tag.name == "ol":
            return [ListFlowable(items, bulletType="1", start=tag.get("start", "1"), bulletFormat="%s.",
                                 bulletFontName=self.body, bulletFontSize=10, leftIndent=16)]
        return [ListFlowable(items, bulletType="bullet", start="•",
                             bulletFontName=self.body, bulletFontSize=9, leftIndent=16)]

    def blocks(self, parent: Tag) -> list:
        """Walk children; group consecutive inline content into paragraphs."""
        out, buf = [], []

        def flush():
            if buf:
                out.extend(self.para("".join(buf)))
                buf.clear()

        for node in parent.children:
            if isinstance(node, Tag) and node.name in BLOCK_TAGS | {"script", "style", "head"}:
                flush()
                n = node.name
                if n in ("script", "style", "head"):
                    continue
                if re.fullmatch(r"h[1-6]", n):
                    out.extend(self.para(_inline(node, self.mono), n))
                elif n == "p":
                    out.extend(self.para(_inline(node, self.mono)))
                    for img in node.find_all("img"):
                        out.extend(self.image(img))
                elif n in ("ul", "ol"):
                    out.extend(self.lst(node))
                elif n == "table":
                    out.extend(self.table(node))
                elif n == "pre":
                    out.append(Preformatted(node.get_text(), self.st["pre"]))
                elif n == "blockquote":
                    parts = node.find_all("p") or [node]
                    for part in parts:
                        out.extend(self.para(_inline(part, self.mono), "quote"))
                elif n == "hr":
                    out.append(HRFlowable(width="100%", color=colors.HexColor("#cccccc"),
                                          spaceBefore=6, spaceAfter=6))
                elif n == "img":
                    out.extend(self.image(node))
                elif n == "dt":
                    out.extend(self.para(f"<b>{_inline(node, self.mono)}</b>"))
                else:  # containers: div, section, li, dd, ...
                    out.extend(self.blocks(node))
            else:
                buf.append(_inline(node, self.mono))
        flush()
        return out


def html_to_pdf(src: Path, dst: Path) -> list[Path]:
    html = Path(src).read_text(encoding="utf-8", errors="replace")
    soup = BeautifulSoup(html, "lxml" if "lxml" in sys.modules or _has_lxml() else "html.parser")
    title = (soup.title.string if soup.title and soup.title.string else Path(src).stem).strip()
    body = soup.body or soup
    margin = 18 * mm
    doc = SimpleDocTemplate(str(dst), pagesize=A4, leftMargin=margin, rightMargin=margin,
                            topMargin=margin, bottomMargin=margin, title=title)
    b = _Builder(Path(src).parent, A4[0] - 2 * margin)
    story = b.blocks(body) or [Paragraph(" ", b.st["p"])]

    def footer(canvas, d):
        canvas.saveState()
        canvas.setFont(b.body, 8)
        canvas.setFillColor(colors.grey)
        canvas.drawRightString(A4[0] - margin, 10 * mm, str(d.page))
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return [dst]


def _has_lxml() -> bool:
    try:
        import lxml  # noqa: F401
        return True
    except ImportError:
        return False
