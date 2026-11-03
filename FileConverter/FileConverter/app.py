"""
File Converter — Windows desktop app (PySide6 / Qt).

Drag files in, pick a target format, click Convert.
Run:  python app.py
"""
from __future__ import annotations

import os
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QObject, QSettings, Qt, QThread, Signal, QUrl
from PySide6.QtGui import QBrush, QColor, QDesktopServices, QFont, QIcon
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QComboBox,
                               QFileDialog, QFrame, QHBoxLayout, QHeaderView, QLabel,
                               QLineEdit, QMainWindow, QMessageBox, QPlainTextEdit,
                               QProgressBar, QPushButton, QRadioButton, QSplitter,
                               QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

import converter
from converter import (LABELS, ConversionError, describe_route, find_route,
                       format_of, input_formats)

APP_NAME = "File Converter"


@lru_cache(None)
def targets(fmt: str) -> tuple[str, ...]:
    return tuple(converter.targets_for(fmt))


# ---------------------------------------------------------------- worker
class Worker(QObject):
    log = Signal(str)
    row_status = Signal(int, str, bool)     # row, message, ok
    progress = Signal(int)
    finished = Signal(int, int, list)       # ok count, fail count, output files

    def __init__(self, files: list[str], fmt: str, out_dir: str | None):
        super().__init__()
        self.files, self.fmt, self.out_dir = files, fmt, out_dir
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        ok = fail = 0
        outputs: list[str] = []
        for i, f in enumerate(self.files):
            if self._stop:
                self.log.emit("Stopped.")
                break
            self.row_status.emit(i, "Converting…", True)
            try:
                outs = converter.convert(f, self.fmt, self.out_dir, log=self.log.emit)
                outputs += [str(o) for o in outs]
                names = ", ".join(o.name for o in outs[:3]) + (" …" if len(outs) > 3 else "")
                self.row_status.emit(i, f"✓ {names}", True)
                self.log.emit(f"   ✓ saved {names}")
                ok += 1
            except ConversionError as e:
                self.row_status.emit(i, f"✗ {e}", False)
                self.log.emit(f"   ✗ {e}")
                fail += 1
            except Exception as e:  # never crash the app
                self.row_status.emit(i, f"✗ Unexpected error: {e}", False)
                self.log.emit(f"   ✗ Unexpected error: {e!r}")
                fail += 1
            self.progress.emit(i + 1)
        self.finished.emit(ok, fail, outputs)


# ---------------------------------------------------------------- window
class MainWindow(QMainWindow):
    COL_FILE, COL_TYPE, COL_STATUS = range(3)

    def __init__(self):
        super().__init__()
        self.settings = QSettings("FileConverter", "FileConverter")
        self.setWindowTitle(APP_NAME)
        self.resize(900, 620)
        self.setAcceptDrops(True)
        self.thread: QThread | None = None
        self.worker: Worker | None = None
        self._build()
        self._refresh()

    # ---------- layout
    def _build(self):
        root = QWidget()
        lay = QVBoxLayout(root)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(10)

        title = QLabel(APP_NAME)
        title.setObjectName("title")
        hint = QLabel("Drop files here, or use Add files. PDF, Word, HTML, Markdown, text, "
                      "images, spreadsheets, audio and video.")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        lay.addWidget(title)
        lay.addWidget(hint)

        # file list
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["File", "Type", "Status"])
        self.tree.setRootIsDecorated(False)
        self.tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.tree.setAlternatingRowColors(True)
        h = self.tree.header()
        h.setSectionResizeMode(self.COL_FILE, QHeaderView.Stretch)
        h.setSectionResizeMode(self.COL_TYPE, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(self.COL_STATUS, QHeaderView.Interactive)
        h.resizeSection(self.COL_STATUS, 300)
        self.tree.setAcceptDrops(False)  # the window handles drops

        self.empty = QLabel("⇩  Drag & drop files here")
        self.empty.setAlignment(Qt.AlignCenter)
        self.empty.setObjectName("dropzone")

        btns = QHBoxLayout()
        self.b_add = QPushButton("Add files…")
        self.b_folder = QPushButton("Add folder…")
        self.b_remove = QPushButton("Remove")
        self.b_clear = QPushButton("Clear")
        for b in (self.b_add, self.b_folder, self.b_remove, self.b_clear):
            btns.addWidget(b)
        btns.addStretch()
        self.b_add.clicked.connect(self.add_files_dialog)
        self.b_folder.clicked.connect(self.add_folder_dialog)
        self.b_remove.clicked.connect(self.remove_selected)
        self.b_clear.clicked.connect(self.clear)

        top = QWidget()
        tl = QVBoxLayout(top)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.addWidget(self.empty, 1)
        tl.addWidget(self.tree, 1)
        tl.addLayout(btns)

        # options panel
        opts = QFrame()
        opts.setObjectName("panel")
        ol = QVBoxLayout(opts)
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Convert to:"))
        self.combo = QComboBox()
        self.combo.setMinimumWidth(260)
        self.combo.currentIndexChanged.connect(self._update_route)
        row1.addWidget(self.combo)
        self.route = QLabel("")
        self.route.setObjectName("route")
        row1.addWidget(self.route, 1)
        ol.addLayout(row1)

        row2 = QHBoxLayout()
        self.r_same = QRadioButton("Save next to the original")
        self.r_folder = QRadioButton("Save to:")
        self.out_edit = QLineEdit(self.settings.value("out_dir", str(Path.home() / "Documents" / "Converted")))
        self.b_browse = QPushButton("Browse…")
        self.b_browse.clicked.connect(self.pick_out_dir)
        (self.r_folder if self.settings.value("use_folder", "false") == "true" else self.r_same).setChecked(True)
        row2.addWidget(self.r_same)
        row2.addSpacing(12)
        row2.addWidget(self.r_folder)
        row2.addWidget(self.out_edit, 1)
        row2.addWidget(self.b_browse)
        ol.addLayout(row2)

        row3 = QHBoxLayout()
        self.c_open = QCheckBox("Open output folder when done")
        self.c_open.setChecked(self.settings.value("open_after", "true") == "true")
        row3.addWidget(self.c_open)
        row3.addStretch()
        self.progress = QProgressBar()
        self.progress.setTextVisible(True)
        self.progress.setMinimumWidth(220)
        row3.addWidget(self.progress)
        self.b_convert = QPushButton("Convert")
        self.b_convert.setObjectName("primary")
        self.b_convert.setMinimumWidth(130)
        self.b_convert.clicked.connect(self.start_or_stop)
        row3.addWidget(self.b_convert)
        ol.addLayout(row3)

        self.logbox = QPlainTextEdit()
        self.logbox.setReadOnly(True)
        self.logbox.setFont(QFont("Consolas", 9))
        self.logbox.setPlaceholderText("Conversion log")

        split = QSplitter(Qt.Vertical)
        split.addWidget(top)
        split.addWidget(self.logbox)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 1)

        lay.addWidget(split, 1)
        lay.addWidget(opts)
        self.setCentralWidget(root)

    # ---------- drag & drop
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        paths = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        self.add_paths(paths)

    # ---------- file list
    def add_paths(self, paths):
        supported = set(input_formats())
        existing = {self.tree.topLevelItem(i).data(0, Qt.UserRole)
                    for i in range(self.tree.topLevelItemCount())}
        skipped = []
        for p in paths:
            pp = Path(p)
            files = [f for f in pp.rglob("*") if f.is_file()] if pp.is_dir() else [pp]
            for f in files:
                fmt = format_of(f)
                if fmt not in supported:
                    if not pp.is_dir():
                        skipped.append(f.name)
                    continue
                if str(f) in existing:
                    continue
                it = QTreeWidgetItem([f.name, fmt.upper(), "Ready"])
                it.setData(0, Qt.UserRole, str(f))
                it.setToolTip(0, str(f))
                self.tree.addTopLevelItem(it)
                existing.add(str(f))
        if skipped:
            self.log(f"Skipped unsupported files: {', '.join(skipped[:10])}"
                     + (" …" if len(skipped) > 10 else ""))
        self._refresh()

    def add_files_dialog(self):
        exts = " ".join(f"*.{f}" for f in input_formats())
        start = self.settings.value("last_dir", str(Path.home()))
        files, _ = QFileDialog.getOpenFileNames(self, "Add files", start,
                                                f"Supported files ({exts});;All files (*)")
        if files:
            self.settings.setValue("last_dir", str(Path(files[0]).parent))
            self.add_paths(files)

    def add_folder_dialog(self):
        d = QFileDialog.getExistingDirectory(self, "Add every supported file in a folder",
                                             self.settings.value("last_dir", str(Path.home())))
        if d:
            self.add_paths([d])

    def remove_selected(self):
        for it in self.tree.selectedItems():
            self.tree.takeTopLevelItem(self.tree.indexOfTopLevelItem(it))
        self._refresh()

    def clear(self):
        self.tree.clear()
        self._refresh()

    def files(self) -> list[str]:
        return [self.tree.topLevelItem(i).data(0, Qt.UserRole)
                for i in range(self.tree.topLevelItemCount())]

    # ---------- format choices
    def _refresh(self):
        files = self.files()
        has = bool(files)
        self.empty.setVisible(not has)
        self.tree.setVisible(has)
        fmts = sorted({format_of(f) for f in files})
        previous = self.combo.currentData() or self.settings.value("last_target", "")
        self.combo.blockSignals(True)
        self.combo.clear()
        if fmts:
            # formats every selected file can reach (a file already in that format is skipped)
            common = set.intersection(*(set(targets(f)) | {f} for f in fmts))
            if len(fmts) == 1:
                common.discard(fmts[0])
            for t in sorted(common):
                self.combo.addItem(f"{t.upper()}  —  {LABELS.get(t, t)}", t)
        idx = self.combo.findData(previous)
        self.combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.combo.blockSignals(False)
        if has and self.combo.count() == 0:
            self.route.setText("These file types have no common target format — "
                               "convert them in separate batches.")
        self._update_route()
        self.b_convert.setEnabled(has and self.combo.count() > 0 or self.thread is not None)

    def _update_route(self):
        t = self.combo.currentData()
        if not t:
            if self.combo.count():
                self.route.setText("")
            return
        routes = []
        for f in sorted({format_of(x) for x in self.files()}):
            if f == t:
                routes.append(f"{f}: already {t}, skipped")
                continue
            r = find_route(f, t)
            if r:
                routes.append(describe_route(r))
        self.route.setText("   ".join(routes[:3]) + ("   …" if len(routes) > 3 else ""))

    def pick_out_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Output folder", self.out_edit.text())
        if d:
            self.out_edit.setText(d)
            self.r_folder.setChecked(True)

    # ---------- conversion
    def log(self, msg: str):
        self.logbox.appendPlainText(msg)

    def start_or_stop(self):
        if self.thread:
            self.worker.stop()
            self.b_convert.setText("Stopping…")
            self.b_convert.setEnabled(False)
            return
        target = self.combo.currentData()
        all_files = self.files()
        files = [f for f in all_files if format_of(f) != target]
        if not target or not files:
            return
        out_dir = self.out_edit.text().strip() if self.r_folder.isChecked() else None
        if out_dir:
            try:
                Path(out_dir).mkdir(parents=True, exist_ok=True)
            except OSError as e:
                QMessageBox.warning(self, APP_NAME, f"Can't use that output folder:\n{e}")
                return
        self.settings.setValue("last_target", target)
        self.settings.setValue("use_folder", "true" if self.r_folder.isChecked() else "false")
        self.settings.setValue("out_dir", self.out_edit.text())
        self.settings.setValue("open_after", "true" if self.c_open.isChecked() else "false")

        self._rows = [all_files.index(f) for f in files]
        for i in range(self.tree.topLevelItemCount()):
            self._set_status(i, "Waiting" if i in self._rows else "Skipped (same format)", True)
        self.progress.setRange(0, len(files))
        self.progress.setValue(0)
        self.log(f"── Converting {len(files)} file(s) to {target.upper()} ──")
        self._set_busy(True)

        self.thread = QThread(self)
        self.worker = Worker(files, target, out_dir)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.log.connect(self.log)
        self.worker.progress.connect(self.progress.setValue)
        self.worker.row_status.connect(lambda i, m, ok: self._set_status(self._rows[i], m, ok))
        self.worker.finished.connect(self._done)
        self.worker.finished.connect(self.thread.quit)
        self.thread.finished.connect(self._cleanup_thread)
        self.thread.start()

    def _set_status(self, row: int, msg: str, ok: bool):
        it = self.tree.topLevelItem(row)
        if it:
            it.setText(self.COL_STATUS, msg)
            it.setToolTip(self.COL_STATUS, msg)
            it.setForeground(self.COL_STATUS, QBrush(QColor("#c0392b") if not ok else self.palette().text().color()))

    def _set_busy(self, busy: bool):
        for w in (self.b_add, self.b_folder, self.b_remove, self.b_clear, self.combo,
                  self.r_same, self.r_folder, self.out_edit, self.b_browse):
            w.setEnabled(not busy)
        self.b_convert.setText("Stop" if busy else "Convert")
        self.b_convert.setEnabled(True)

    def _done(self, ok: int, fail: int, outputs: list):
        self.log(f"── Done: {ok} converted, {fail} failed ──\n")
        if outputs and self.c_open.isChecked():
            open_folder(outputs[0])
        if fail and not ok:
            QMessageBox.warning(self, APP_NAME, "No files could be converted. See the log for details.")

    def _cleanup_thread(self):
        self.worker.deleteLater()
        self.thread.deleteLater()
        self.thread = self.worker = None
        self._set_busy(False)
        self._refresh()

    def closeEvent(self, e):
        if self.thread:
            self.worker.stop()
            self.thread.quit()
            self.thread.wait(3000)
        e.accept()


def open_folder(file_path: str):
    """Open Explorer with the file selected."""
    p = Path(file_path)
    if sys.platform.startswith("win"):
        subprocess.Popen(["explorer", "/select,", str(p)])
    else:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(p.parent)))


STYLE = """
QWidget { font-family: 'Segoe UI', sans-serif; font-size: 10pt; }
QLabel#title { font-size: 18pt; font-weight: 600; }
QLabel#hint { color: palette(mid); }
QLabel#route { color: #2a7ae2; padding-left: 8px; }
QLabel#dropzone { border: 2px dashed palette(mid); border-radius: 10px;
                  font-size: 14pt; color: palette(mid); min-height: 160px; }
QFrame#panel { border: 1px solid palette(midlight); border-radius: 8px; padding: 6px; }
QPushButton { padding: 6px 14px; border-radius: 5px; }
QPushButton#primary { background: #2a7ae2; color: white; font-weight: 600; border: none; }
QPushButton#primary:hover { background: #1f66c4; }
QPushButton#primary:disabled { background: #9bbbe6; }
QProgressBar { border: 1px solid palette(midlight); border-radius: 5px; text-align: center; height: 20px; }
QProgressBar::chunk { background: #2a7ae2; border-radius: 4px; }
"""


def _install_crash_handler():
    """Show errors in a dialog and save them to a log, instead of closing silently."""
    import traceback
    log_file = Path(os.environ.get("TEMP", Path.home())) / "fileconverter_error.txt"

    def hook(exc_type, exc, tb):
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        try:
            log_file.write_text(text, encoding="utf-8")
        except OSError:
            pass
        if QApplication.instance():
            QMessageBox.critical(None, APP_NAME, f"Something went wrong:\n\n{exc}\n\n"
                                 f"Details saved to:\n{log_file}")
    sys.excepthook = hook


def main():
    _install_crash_handler()
    if sys.platform.startswith("win"):
        try:  # own taskbar icon instead of python.exe's
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("FileConverter.App")
        except Exception:
            pass
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    icon = Path(__file__).with_name("icon.ico")
    if icon.exists():
        app.setWindowIcon(QIcon(str(icon)))
    w = MainWindow()
    if len(sys.argv) > 1:  # "Open with" / drag onto the .exe
        w.add_paths(sys.argv[1:])
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
