from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMainWindow, QPlainTextEdit, QSplitter, QTextEdit

from nexa.compiler import Compiler


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Nexa Studio")
        self.resize(1280, 840)

        self.editor = QPlainTextEdit()
        self.viewer = QTextEdit()
        self.viewer.setReadOnly(True)
        self.console = QTextEdit()
        self.console.setReadOnly(True)

        horiz = QSplitter(Qt.Horizontal)
        horiz.addWidget(self.editor)
        horiz.addWidget(self.viewer)

        root = QSplitter(Qt.Vertical)
        root.addWidget(horiz)
        root.addWidget(self.console)
        root.setSizes([650, 190])
        self.setCentralWidget(root)

    def compile_now(self) -> None:
        result = Compiler().compile(self.editor.toPlainText())
        self.console.clear()
        for d in result.diagnostics:
            self.console.append(f"{d.level}: {d.message}")
        if result.value:
            self.viewer.setPlainText("\n".join(result.value.hir))


def run() -> None:
    app = QApplication([])
    win = MainWindow()
    win.show()
    app.exec()

