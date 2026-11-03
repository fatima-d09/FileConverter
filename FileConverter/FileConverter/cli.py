"""
Command-line version.

  python cli.py report.pdf --to .docx
  python cli.py *.png --to .webp --out converted
  python cli.py --list            (show every supported conversion)
  python cli.py notes.md --route pdf   (show the steps it would take)
"""
from __future__ import annotations

import argparse
import glob
import sys

from converter import (ConversionError, convert, describe_route, find_route,
                       format_of, input_formats, targets_for)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Convert files between formats.")
    ap.add_argument("files", nargs="*", help="files to convert (wildcards ok)")
    ap.add_argument("--to", "-t", help="target format, e.g. docx, md, pdf, png")
    ap.add_argument("--out", "-o", help="output folder (default: next to each file)")
    ap.add_argument("--list", action="store_true", help="list supported conversions")
    ap.add_argument("--route", help="show the conversion steps to this format")
    a = ap.parse_args(argv)

    if a.list:
        for f in input_formats():
            print(f"{f:>6} -> {', '.join(targets_for(f))}")
        return 0

    files = [p for pat in a.files for p in (glob.glob(pat) or [pat])]
    if a.route:
        for f in files:
            r = find_route(format_of(f), a.route)
            print(f"{f}: {describe_route(r) if r else 'not possible'}")
        return 0
    if not files or not a.to:
        ap.print_help()
        return 1

    failed = 0
    for f in files:
        try:
            outs = convert(f, a.to, a.out, log=print)
            for o in outs:
                print(f"   ✓ {o}")
        except ConversionError as e:
            failed += 1
            print(f"   ✗ {e}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    sys.exit(main())
