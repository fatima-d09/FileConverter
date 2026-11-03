"""Tabular data: csv, xlsx, json -> each other, and to html / md tables."""
from __future__ import annotations

import csv
import json
from datetime import date, datetime
from html import escape
from pathlib import Path

from .engine import ConversionError, register


def _has(m):
    try:
        __import__(m)
        return True
    except ImportError:
        return False


# ---------- readers: every format becomes a list of rows (first row = header)
def _read_csv(p: Path) -> list[list]:
    raw = p.read_bytes()
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    return [row for row in csv.reader(text.splitlines(), dialect)]


def _read_xlsx(p: Path) -> list[list]:
    from openpyxl import load_workbook
    wb = load_workbook(p, read_only=True, data_only=True)
    ws = wb.active
    rows = [["" if v is None else v for v in r] for r in ws.iter_rows(values_only=True)]
    wb.close()
    while rows and not any(str(v).strip() for v in rows[-1]):
        rows.pop()
    return rows


def _read_json(p: Path) -> list[list]:
    data = json.loads(p.read_text(encoding="utf-8-sig"))
    if isinstance(data, dict):  # {"items": [...]} or a single record
        lists = [v for v in data.values() if isinstance(v, list)]
        data = lists[0] if len(lists) == 1 else [data]
    if not isinstance(data, list) or not data:
        raise ConversionError("JSON must be a list of records to convert to a table.")
    if all(isinstance(d, dict) for d in data):
        header: list[str] = []
        for d in data:
            header += [k for k in d if k not in header]
        return [header] + [[_cell(d.get(k, "")) for k in header] for d in data]
    if all(isinstance(d, list) for d in data):
        return [[_cell(v) for v in r] for r in data]
    return [["value"]] + [[_cell(v)] for v in data]


def _cell(v):
    return json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v


READERS = {"csv": _read_csv, "xlsx": _read_xlsx, "json": _read_json}


# ---------- writers
def _plain(v):
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    return "" if v is None else v


def _write_csv(rows, p: Path):
    with p.open("w", newline="", encoding="utf-8-sig") as f:  # BOM so Excel opens UTF-8 correctly
        csv.writer(f).writerows([[_plain(v) for v in r] for r in rows])


def _write_xlsx(rows, p: Path):
    from openpyxl import Workbook
    from openpyxl.styles import Font
    from openpyxl.utils import get_column_letter
    wb = Workbook()
    ws = wb.active
    ws.title = p.stem[:31] or "Sheet1"
    for r in rows:
        ws.append([_number(v) for v in r])
    if rows:
        for c in ws[1]:
            c.font = Font(bold=True)
        ws.freeze_panes = "A2"
        for i in range(1, max(len(r) for r in rows) + 1):
            width = max((len(str(r[i - 1])) for r in rows if len(r) >= i), default=8)
            ws.column_dimensions[get_column_letter(i)].width = min(max(8, width + 2), 60)
    wb.save(p)


def _number(v):
    """'42' -> 42, '3.5' -> 3.5 so Excel treats numbers as numbers."""
    if isinstance(v, str):
        s = v.strip()
        try:
            if s.lstrip("-").isdigit() and not (len(s.lstrip("-")) > 1 and s.lstrip("-")[0] == "0"):
                return int(s)
            if s and s.count(".") == 1 and s.replace(".", "", 1).lstrip("-").isdigit():
                return float(s)
        except ValueError:
            pass
    return v


def _write_json(rows, p: Path):
    if not rows:
        data = []
    else:
        header = [str(h) if str(h).strip() else f"column{i + 1}" for i, h in enumerate(rows[0])]
        data = [{h: _plain(_number(r[i]) if i < len(r) else "") for i, h in enumerate(header)}
                for r in rows[1:]]
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _write_html(rows, p: Path):
    head, body = (rows[0], rows[1:]) if rows else ([], [])
    th = "".join(f"<th>{escape(str(_plain(v)))}</th>" for v in head)
    trs = "\n".join("<tr>" + "".join(f"<td>{escape(str(_plain(v)))}</td>" for v in r) + "</tr>"
                    for r in body)
    p.write_text(f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{escape(p.stem)}</title>
<style>body{{font-family:Segoe UI,Arial,sans-serif;margin:2em}}
table{{border-collapse:collapse}}th,td{{border:1px solid #ccc;padding:4px 8px;text-align:left}}
th{{background:#eee}}</style></head><body>
<table>
<thead><tr>{th}</tr></thead>
<tbody>
{trs}
</tbody></table></body></html>
""", encoding="utf-8")


def _write_md(rows, p: Path):
    if not rows:
        p.write_text("", encoding="utf-8")
        return
    n = max(len(r) for r in rows)
    fix = lambda r: [str(_plain(v)).replace("|", "\\|").replace("\n", " ") for v in r] + [""] * (n - len(r))  # noqa
    lines = ["| " + " | ".join(fix(rows[0])) + " |", "|" + "---|" * n]
    lines += ["| " + " | ".join(fix(r)) + " |" for r in rows[1:]]
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")


WRITERS = {"csv": _write_csv, "xlsx": _write_xlsx, "json": _write_json,
           "html": _write_html, "md": _write_md}


def convert_table(src: Path, dst: Path) -> list[Path]:
    rows = READERS[src.suffix[1:].lower()](src)
    WRITERS[dst.suffix[1:].lower()](rows, dst)
    return [dst]


register(["csv", "json"], WRITERS.keys(), convert_table, name="tables", cost=8)
register(["xlsx"], WRITERS.keys(), convert_table, name="openpyxl", cost=8,
         available=lambda: _has("openpyxl"))
