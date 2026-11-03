"""
Creates "File Converter" shortcuts on the Desktop and in the Start menu,
with the app's own icon. The shortcut carries the same AppUserModelID the
app uses, so pinning it to the taskbar groups correctly with the open window
(instead of just showing the Python logo).
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

APP_ID = "FileConverter.App"   # must match app.py
NAME = "File Converter"

HERE = Path(__file__).resolve().parent
TARGET = HERE / ".venv" / "Scripts" / "pythonw.exe"
ARGS = f'"{HERE / "app.py"}"'
ICON = HERE / "icon.ico"


def folders() -> list[Path]:
    out = []
    try:  # real Desktop path (handles OneDrive-redirected desktops)
        import ctypes
        from ctypes import wintypes
        buf = ctypes.create_unicode_buffer(wintypes.MAX_PATH)
        ctypes.windll.shell32.SHGetFolderPathW(None, 0x0010, None, 0, buf)  # CSIDL_DESKTOPDIRECTORY
        out.append(Path(buf.value))
    except Exception:
        out.append(Path.home() / "Desktop")
    out.append(Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs")
    return out


def make_with_pywin32(lnk: Path) -> None:
    import pythoncom
    from win32com.propsys import propsys, pscon
    from win32com.shell import shell

    link = pythoncom.CoCreateInstance(shell.CLSID_ShellLink, None,
                                      pythoncom.CLSCTX_INPROC_SERVER, shell.IID_IShellLink)
    link.SetPath(str(TARGET))
    link.SetArguments(ARGS)
    link.SetWorkingDirectory(str(HERE))
    link.SetIconLocation(str(ICON), 0)
    link.SetDescription("Convert files between formats")
    store = link.QueryInterface(propsys.IID_IPropertyStore)
    store.SetValue(pscon.PKEY_AppUserModel_ID, propsys.PROPVARIANTType(APP_ID, pythoncom.VT_LPWSTR))
    store.Commit()
    link.QueryInterface(pythoncom.IID_IPersistFile).Save(str(lnk), 0)


def make_with_powershell(lnk: Path) -> None:
    """Fallback: plain shortcut (icon works; taskbar grouping may not)."""
    env = dict(os.environ, SC_LNK=str(lnk), SC_TARGET=str(TARGET), SC_ARGS=ARGS,
               SC_DIR=str(HERE), SC_ICON=f"{ICON},0")
    ps = ("$s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:SC_LNK);"
          "$s.TargetPath=$env:SC_TARGET;$s.Arguments=$env:SC_ARGS;"
          "$s.WorkingDirectory=$env:SC_DIR;$s.IconLocation=$env:SC_ICON;"
          "$s.Description='Convert files between formats';$s.Save()")
    subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
                   env=env, check=True, creationflags=0x08000000)


def main() -> int:
    if not TARGET.exists():
        print("Run run.bat once first (the app isn't set up yet).")
        return 1
    ok = True
    for folder in folders():
        lnk = folder / f"{NAME}.lnk"
        try:
            folder.mkdir(parents=True, exist_ok=True)
            try:
                make_with_pywin32(lnk)
            except Exception as e:
                print(f"  (note: using basic shortcut: {e})")
                make_with_powershell(lnk)
            print(f"  Created: {lnk}")
        except Exception as e:
            ok = False
            print(f"  Could not create {lnk}: {e}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
