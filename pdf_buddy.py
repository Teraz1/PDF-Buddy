"""PDF Buddy - a friendly, offline PDF toolkit.

Run:  python pdf_buddy.py
Needs: pip install PySide6 pypdf pymupdf pillow
"""
import sys
from pathlib import Path

import pymupdf as fitz  # PyMuPDF
from PIL import Image
from pypdf import PdfReader, PdfWriter
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QComboBox, QFileDialog, QFrame,
    QGridLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMainWindow, QMessageBox, QPushButton, QScrollArea, QStackedWidget,
    QVBoxLayout, QWidget,
)

PDF, IMG = "PDF files (*.pdf)", "Images (*.jpg *.jpeg *.png *.webp *.bmp)"


# ---------------------------------------------------------------- tool logic
def soft(hex_color, alpha=0.18):
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{alpha})"


def parse_ranges(text, total):
    """'1-3, 5' -> [[0,1,2],[4]] (zero-based page indexes)."""
    groups = []
    for part in text.replace(" ", "").split(","):
        if not part:
            continue
        a, _, b = part.partition("-")
        start, end = int(a), int(b or a)
        if not (1 <= start <= end <= total):
            raise ValueError(f"'{part}' is outside this PDF (it has {total} pages).")
        groups.append(list(range(start - 1, end)))
    if not groups:
        raise ValueError("Type the pages you want, for example 1-3, 5.")
    return groups


def merge(files, opts, out):
    w = PdfWriter()
    for f in files:
        w.append(f)
    with open(out, "wb") as fh:
        w.write(fh)
    return f"Merged {len(files)} PDFs into one file."


def split(files, opts, out):
    r = PdfReader(files[0])
    n = len(r.pages)
    if opts["mode"].startswith("Every"):
        groups = [[i] for i in range(n)]
    else:
        groups = parse_ranges(opts["ranges"], n)
    stem = Path(files[0]).stem
    for k, pages in enumerate(groups, 1):
        w = PdfWriter()
        for p in pages:
            w.add_page(r.pages[p])
        with open(Path(out) / f"{stem}_part{k}.pdf", "wb") as fh:
            w.write(fh)
    return f"Created {len(groups)} files."


def rotate(files, opts, out):
    r, w = PdfReader(files[0]), PdfWriter()
    deg = int(opts["angle"].split("°")[0])
    for p in r.pages:
        p.rotate(deg)
        w.add_page(p)
    with open(out, "wb") as fh:
        w.write(fh)
    return "Rotated every page."


def compress(files, opts, out):
    src = Path(files[0])
    doc = fitz.open(src)
    level = opts["level"]
    if not level.startswith("Light"):
        dpi, q = (150, 70) if level.startswith("Balanced") else (96, 50)
        try:
            doc.rewrite_images(dpi_threshold=dpi + 30, dpi_target=dpi, quality=q)
        except Exception:
            pass  # older PyMuPDF: fall back to lossless cleanup only
    doc.save(out, garbage=4, deflate=True, clean=True)
    before, after = src.stat().st_size, Path(out).stat().st_size
    saved = max(0, 100 - after * 100 // max(before, 1))
    return f"{before/1e6:.2f} MB → {after/1e6:.2f} MB ({saved}% smaller)."


def images_to_pdf(files, opts, out):
    imgs = [Image.open(f).convert("RGB") for f in files]
    imgs[0].save(out, save_all=True, append_images=imgs[1:])
    return f"Made a PDF from {len(imgs)} images."


def pdf_to_images(files, opts, out):
    doc, fmt = fitz.open(files[0]), opts["format"].lower()
    stem = Path(files[0]).stem
    for i, page in enumerate(doc, 1):
        page.get_pixmap(dpi=150).save(Path(out) / f"{stem}_page{i}.{fmt}")
    return f"Saved {len(doc)} images."


def protect(files, opts, out):
    if not opts["password"]:
        raise ValueError("Choose a password first.")
    w = PdfWriter(clone_from=files[0])
    w.encrypt(opts["password"])
    with open(out, "wb") as fh:
        w.write(fh)
    return "Your PDF now needs a password to open."


def unlock(files, opts, out):
    r = PdfReader(files[0])
    if r.is_encrypted and not r.decrypt(opts["password"]):
        raise ValueError("That password didn't work. Check it and try again.")
    w = PdfWriter(clone_from=r)
    with open(out, "wb") as fh:
        w.write(fh)
    return "Password removed."


# name, blurb, emoji, colour, file filter, many files?, output kind, suffix, options, function
TOOLS = [
    ("Merge PDF", "Join several PDFs into one", "🧩", "#FF8A65", PDF, True, "file", "merged", [], merge),
    ("Split PDF", "Pull out pages or ranges", "✂️", "#4DB6AC", PDF, False, "dir", "", [
        ("mode", "Split", ["Every page", "Page ranges"]), ("ranges", "Pages (e.g. 1-3, 5)", None)], split),
    ("Rotate PDF", "Turn pages the right way up", "🔄", "#7986CB", PDF, False, "file", "rotated", [
        ("angle", "Rotate by", ["90° clockwise", "180°", "270° (90° counter-clockwise)"])], rotate),
    ("Compress PDF", "Make big files smaller", "🗜️", "#F06292", PDF, False, "file", "small", [
        ("level", "Compression", ["Balanced (recommended)", "Strong (smallest file)", "Light (best quality)"])], compress),
    ("Images to PDF", "Turn photos into a PDF", "🖼️", "#FFB74D", IMG, True, "file", "images", [], images_to_pdf),
    ("PDF to Images", "Save each page as a picture", "📸", "#64B5F6", PDF, False, "dir", "", [
        ("format", "Format", ["JPG", "PNG"])], pdf_to_images),
    ("Protect PDF", "Lock it with a password", "🔒", "#9575CD", PDF, False, "file", "protected", [
        ("password", "Password", "secret")], protect),
    ("Unlock PDF", "Remove a password", "🔓", "#81C784", PDF, False, "file", "unlocked", [
        ("password", "Current password", "secret")], unlock),
]

STYLE = """
* { font-family: 'Segoe UI', 'SF Pro Text', 'Helvetica Neue', Arial; font-size: 14px; color: #243044; }
QMainWindow, #page { background: #F4F7FB; }
#title { font-size: 30px; font-weight: 700; }
#sub { color: #6B778C; font-size: 15px; }
#card { background: white; border-radius: 20px; border: 1px solid #E6EBF2; }
#card:hover { border: 2px solid #5B7CFA; }
#toolTitle { font-size: 16px; font-weight: 600; }
#toolSub { color: #6B778C; font-size: 13px; }
#panel { background: white; border-radius: 18px; border: 1px solid #E6EBF2; }
QListWidget { border: 2px dashed #C5D0E3; border-radius: 14px; background: #FAFBFE; padding: 6px; outline: 0; }
QListWidget::item { padding: 9px 10px; border-radius: 8px; }
QListWidget::item:selected { background: #E3EAFF; color: #243044; }
QLineEdit, QComboBox { border: 1px solid #D5DDEB; border-radius: 10px; padding: 8px 12px; background: white; min-height: 22px; }
QLineEdit:focus, QComboBox:focus { border: 2px solid #5B7CFA; }
QPushButton { border-radius: 12px; padding: 10px 18px; background: #EAEFF8; font-weight: 600; border: none; }
QPushButton:hover { background: #DCE4F3; }
QPushButton#primary { background: #5B7CFA; color: white; font-size: 16px; padding: 14px 22px; }
QPushButton#primary:hover { background: #4968E6; }
QPushButton#primary:disabled { background: #BAC6F0; }
#status { color: #2E7D5B; font-weight: 600; }
"""


class DropList(QListWidget):
    """File list that accepts dropped files and lets you reorder by dragging."""

    def __init__(self, exts, many):
        super().__init__()
        self.exts, self.many = exts, many
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)

    def add_paths(self, paths):
        ok = tuple(e.lstrip("*") for e in self.exts.split("(")[1].rstrip(")").split())
        for p in paths:
            if not p.lower().endswith(ok):
                continue
            if not self.many:
                self.clear()
            self.addItem(QListWidgetItem(p))

    def dragEnterEvent(self, e):
        (e.acceptProposedAction() if e.mimeData().hasUrls() else super().dragEnterEvent(e))

    def dragMoveEvent(self, e):
        (e.acceptProposedAction() if e.mimeData().hasUrls() else super().dragMoveEvent(e))

    def dropEvent(self, e):
        if e.mimeData().hasUrls():
            self.add_paths([u.toLocalFile() for u in e.mimeData().urls()])
            e.acceptProposedAction()
        else:
            super().dropEvent(e)

    def paths(self):
        return [self.item(i).text() for i in range(self.count())]


class ToolPage(QWidget):
    def __init__(self, tool, go_home):
        super().__init__()
        self.name, blurb, icon, color, self.exts, many, self.out_kind, self.suffix, opts, self.fn = tool
        self.many, self.fields = many, {}
        root = QVBoxLayout(self)
        root.setContentsMargins(40, 28, 40, 28)
        root.setSpacing(16)

        top = QHBoxLayout()
        back = QPushButton("‹  All tools")
        back.clicked.connect(go_home)
        top.addWidget(back)
        top.addStretch()
        root.addLayout(top)

        head = QHBoxLayout()
        badge = QLabel(icon)
        badge.setFixedSize(64, 64)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setStyleSheet(f"background:{soft(color)}; border-radius:18px; font-size:30px;")
        head.addWidget(badge)
        names = QVBoxLayout()
        t = QLabel(self.name)
        t.setObjectName("title")
        s = QLabel(blurb)
        s.setObjectName("sub")
        names.addWidget(t)
        names.addWidget(s)
        head.addLayout(names)
        head.addStretch()
        root.addLayout(head)

        self.list = DropList(self.exts, many)
        self.list.model().rowsInserted.connect(self.refresh)
        self.list.model().rowsRemoved.connect(self.refresh)
        root.addWidget(self.list, 1)

        row = QHBoxLayout()
        add = QPushButton("＋  Add files…" if many else "＋  Choose a file…")
        add.clicked.connect(self.pick)
        rm = QPushButton("Remove selected")
        rm.clicked.connect(lambda: [self.list.takeItem(self.list.row(i)) for i in self.list.selectedItems()])
        self.hint = QLabel("Or drop files anywhere in the box above" + (" · drag to reorder" if many else ""))
        self.hint.setObjectName("sub")
        row.addWidget(add)
        if many:
            row.addWidget(rm)
        row.addWidget(self.hint)
        row.addStretch()
        root.addLayout(row)

        if opts:
            panel = QFrame()
            panel.setObjectName("panel")
            grid = QGridLayout(panel)
            grid.setContentsMargins(20, 16, 20, 16)
            for r, (key, label, choices) in enumerate(opts):
                grid.addWidget(QLabel(label), r, 0)
                if isinstance(choices, list):
                    w = QComboBox()
                    w.addItems(choices)
                else:
                    w = QLineEdit()
                    w.setPlaceholderText(label)
                    if choices == "secret":
                        w.setEchoMode(QLineEdit.EchoMode.Password)
                grid.addWidget(w, r, 1)
                self.fields[key] = w
            grid.setColumnStretch(1, 1)
            root.addWidget(panel)
            if "mode" in self.fields:
                self.fields["mode"].currentTextChanged.connect(self.sync_mode)
                self.sync_mode()

        self.go = QPushButton(f"{self.name.split()[0]} now")
        self.go.setObjectName("primary")
        self.go.clicked.connect(self.run)
        root.addWidget(self.go)
        self.status = QLabel("")
        self.status.setObjectName("status")
        self.status.setWordWrap(True)
        root.addWidget(self.status)
        self.refresh()

    def sync_mode(self):
        self.fields["ranges"].setEnabled(self.fields["mode"].currentText() == "Page ranges")

    def refresh(self, *_):
        self.go.setEnabled(self.list.count() > 0)

    def pick(self):
        fn = QFileDialog.getOpenFileNames if self.many else lambda *a: ([QFileDialog.getOpenFileName(*a)[0]], 0)
        paths, _ = fn(self, "Choose files", "", self.exts)
        self.list.add_paths([p for p in paths if p])

    def values(self):
        return {k: (w.currentText() if isinstance(w, QComboBox) else w.text()) for k, w in self.fields.items()}

    def run(self):
        files = self.list.paths()
        self.status.setStyleSheet("")
        try:
            if self.out_kind == "dir":
                out = QFileDialog.getExistingDirectory(self, "Where should the files go?")
            else:
                first = Path(files[0])
                default = str(first.with_name(f"{first.stem}_{self.suffix}.pdf"))
                out, _ = QFileDialog.getSaveFileName(self, "Save as", default, PDF)
            if not out:
                return
            if self.many and len(files) < 2 and self.name == "Merge PDF":
                raise ValueError("Add at least two PDFs to merge.")
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            self.status.setText("Working on it…")
            QApplication.processEvents()
            msg = self.fn(files, self.values(), out)
            self.status.setText(f"✓ Done! {msg}")
        except Exception as e:  # show friendly errors instead of crashing
            self.status.setStyleSheet("color:#C0392B;")
            self.status.setText(f"Something went wrong: {e}")
        finally:
            QApplication.restoreOverrideCursor()


class Home(QWidget):
    def __init__(self, open_tool):
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(40, 36, 40, 28)
        root.setSpacing(6)
        t = QLabel("PDF Buddy")
        t.setObjectName("title")
        s = QLabel("Everything you need for PDFs. It all happens on your computer, so your files stay private.")
        s.setObjectName("sub")
        root.addWidget(t)
        root.addWidget(s)
        root.addSpacing(18)
        grid = QGridLayout()
        grid.setSpacing(18)
        for i, tool in enumerate(TOOLS):
            grid.addWidget(self.card(tool, lambda _=0, k=i: open_tool(k)), i // 4, i % 4)
        root.addLayout(grid)
        root.addStretch()

    def card(self, tool, cb):
        name, blurb, icon, color = tool[:4]
        b = QPushButton()
        b.setObjectName("card")
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setMinimumHeight(170)
        b.setStyleSheet("QPushButton#card{background:white;border-radius:20px;border:1px solid #E6EBF2;text-align:left;}"
                        "QPushButton#card:hover{border:2px solid #5B7CFA;background:#FBFCFF;}")
        b.clicked.connect(cb)
        lay = QVBoxLayout(b)
        lay.setContentsMargins(18, 18, 18, 16)
        badge = QLabel(icon)
        badge.setFixedSize(52, 52)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setStyleSheet(f"background:{soft(color)};border-radius:16px;font-size:26px;border:none;")
        n, d = QLabel(name), QLabel(blurb)
        n.setObjectName("toolTitle")
        d.setObjectName("toolSub")
        d.setWordWrap(True)
        for w in (badge, n, d):
            w.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            w.setStyleSheet(w.styleSheet() + "border:none;background-clip:padding;")
        lay.addWidget(badge)
        lay.addSpacing(6)
        lay.addWidget(n)
        lay.addWidget(d)
        lay.addStretch()
        return b


class Main(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PDF Buddy")
        self.resize(1000, 720)
        self.stack = QStackedWidget()
        self.stack.setObjectName("page")
        self.stack.addWidget(Home(self.open_tool))
        for tool in TOOLS:
            self.stack.addWidget(ToolPage(tool, lambda: self.stack.setCurrentIndex(0)))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(self.stack)
        self.setCentralWidget(scroll)

    def open_tool(self, i):
        self.stack.setCurrentIndex(i + 1)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLE)
    app.setFont(QFont("Segoe UI", 10))
    win = Main()
    win.show()
    sys.exit(app.exec())
