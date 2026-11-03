# FileConverter 🗂️
Drag &amp; Drop Windows Applications that converts documents, PDFs, images, spreadsheets, audio and video into different formats

Conversions run as chains when there's no direct converter. For example, `pdf → docx → md` or `md → html → pdf`. The app picks the best chain for you and shows it before you convert, but you can convert to whatever extension you want.

<img alt="Screen Recording 2026-11-02 201007" src="https://github.com/user-attachments/assets/509af6bd-6f30-4be9-a342-94d09363a35f" />

## What it converts

| Category | Formats |
|---|---|
| Documents | docx, doc*, odt, rtf, html, md, txt, epub, tex, rst, ipynb, pdf |
| Presentations | pptx*, ppt*, odp* → pdf / images (* needs LibreOffice) |
| Spreadsheets / data | xlsx, xls*, ods*, csv, json → each other, plus html, md, pdf |
| Images | png, jpg, bmp, gif, tiff, webp, ico, and image → pdf, pdf → images |
| Audio | mp3, wav, flac, ogg, m4a, aac |
| Video | mp4, mkv, avi, mov, webm, video → audio (e.g. mp4 → mp3), video → gif |

To see the exact list on your machine, run `python cli.py --list`.

## Quick start (run from source)

1. Install **Python 3.10 or newer** from python.org. During installation, tick **"Add python.exe to PATH"**.
2. Double-click **`setup.bat`**. It runs once and installs everything into a local `.venv` folder.
3. Double-click **`run.bat`** to start the app.

## Build a standalone .exe

Double-click **`build.bat`**. It produces `dist\FileConverter\FileConverter.exe`. You can copy the whole `dist\FileConverter` folder to any Windows PC, and it runs without Python installed.

## Optional: LibreOffice (best quality for Office → PDF)

If [LibreOffice](https://www.libreoffice.org/download/) is installed, the app finds it automatically and uses it for:

- docx/odt/rtf/pptx/xlsx → **pdf** (closest match to the original layout)
- old formats: **doc, ppt, xls**

Without LibreOffice, documents still convert to PDF through a built-in renderer. It keeps headings, lists, tables, images, bold and italic text, and links, but it's simpler than Word's own layout.

## Command line

```bat
python cli.py report.pdf --to docx
python cli.py *.png --to webp --out converted
python cli.py notes.md --route pdf      :: show the steps it would take
python cli.py --list
```

## Project layout

```
app.py                 desktop window (PySide6 / Qt)
cli.py                 command-line version
converter/
  engine.py            registry + route finder (chains steps automatically)
  documents.py         pandoc: docx, odt, rtf, html, md, txt, epub, tex, rst, ipynb
  pdf.py               pdf → txt/docx/images, html → pdf, LibreOffice conversions
  pdfrender.py         built-in HTML → PDF renderer (ReportLab)
  images.py            Pillow image conversions
  data.py              csv / xlsx / json tables
  media.py             ffmpeg audio & video
```

### Adding a new conversion

Write a function `(src: Path, dst: Path) -> list[Path]` and register it. The route finder then automatically chains it with every other converter:

```python
from converter.engine import register

def svg_to_png(src, dst):
    import cairosvg
    cairosvg.svg2png(url=str(src), write_to=str(dst))
    return [dst]

register(["svg"], ["png"], svg_to_png, name="cairosvg")
```

`cost` (default 10) decides which route wins when there's more than one. Set `terminal=True` when nothing should be chained after a step.

## Limits to know about

- **Scanned PDFs** are only pictures of text, so converting them to docx or txt gives little or no text. You'd need an OCR tool such as Tesseract to read them.
- **PDF → Word** uses `pdf2docx`, which is good for normal documents. Complex magazine-style layouts won't be perfect.
- **Excel → CSV/JSON** uses the active sheet only.
- A PDF converted to images gives one image per page (`name_page001.png`, …).
- Existing files are never overwritten. New files get ` (1)`, ` (2)`, … added to the name.

