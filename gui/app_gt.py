from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QTabWidget, QVBoxLayout,
    QListWidget, QPushButton, QFileDialog, QHBoxLayout, QSpinBox, QLabel,
    QAbstractItemView
)
from PySide6.QtCore import Qt, QThread, Signal
from pathlib import Path
import sys
from audioops.core import fade_file, crossfade_sequence


class DropList(QListWidget):
    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.InternalMove)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dragMoveEvent(self, e):
        e.acceptProposedAction()

    def dropEvent(self, e):
        for url in e.mimeData().urls():
            p = Path(url.toLocalFile())
            if p.is_file():
                self.addItem(str(p))
        e.acceptProposedAction()


class Worker(QThread):
    finished = Signal(str)
    errored = Signal(str)

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.fn, self.args, self.kwargs = fn, args, kwargs

    def run(self):
        try:
            self.fn(*self.args, **self.kwargs)
            self.finished.emit("done")
        except Exception as ex:
            self.errored.emit(str(ex))


class FadeTab(QWidget):
    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        self.list = DropList()
        lay.addWidget(self.list)
        ctrl = QHBoxLayout()
        ctrl.addWidget(QLabel("FadeIn(ms)"))
        self.in_ms = QSpinBox()
        self.in_ms.setRange(0, 600000)
        self.in_ms.setValue(300)
        ctrl.addWidget(self.in_ms)
        ctrl.addWidget(QLabel("FadeOut(ms)"))
        self.out_ms = QSpinBox()
        self.out_ms.setRange(0, 600000)
        self.out_ms.setValue(1500)
        ctrl.addWidget(self.out_ms)
        ctrl.addWidget(QLabel("Out開始(末尾からsec)"))
        self.from_end = QSpinBox()
        self.from_end.setRange(0, 6000)
        self.from_end.setValue(2)
        ctrl.addWidget(self.from_end)
        lay.addLayout(ctrl)
        btns = QHBoxLayout()
        b_add = QPushButton("追加")
        b_add.clicked.connect(self.add_files)
        btns.addWidget(b_add)
        b_run = QPushButton("処理")
        b_run.clicked.connect(self.run)
        btns.addWidget(b_run)
        lay.addLayout(btns)

    def add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "音声を選択")
        for p in paths:
            self.list.addItem(p)

    def run(self):
        out_dir = QFileDialog.getExistingDirectory(self, "出力フォルダ")
        if not out_dir:
            return
        in_ms, out_ms, from_end = self.in_ms.value(
        ), self.out_ms.value(), self.from_end.value()

        def task():
            for i in range(self.list.count()):
                src = Path(self.list.item(i).text())
                dst = Path(out_dir) / src.with_suffix(src.suffix).name
                fade_file(src, dst, fade_in_ms=in_ms, fade_out_ms=out_ms,
                          fade_out_from_end_sec=from_end, codec="libmp3lame")
        self.worker = Worker(task)
        self.worker.start()


class CrossfadeTab(QWidget):
    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        self.list = DropList()
        lay.addWidget(self.list)
        ctrl = QHBoxLayout()
        ctrl.addWidget(QLabel("オーバーラップ(sec)"))
        self.overlap = QSpinBox()
        self.overlap.setRange(0, 60)
        self.overlap.setValue(2)
        ctrl.addWidget(self.overlap)
        lay.addLayout(ctrl)
        btns = QHBoxLayout()
        b_add = QPushButton("追加")
        b_add.clicked.connect(self.add_files)
        btns.addWidget(b_add)
        b_run = QPushButton("連結")
        b_run.clicked.connect(self.run)
        btns.addWidget(b_run)
        lay.addLayout(btns)

    def add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "音声を選択（順番＝再生順）")
        for p in paths:
            self.list.addItem(p)

    def run(self):
        if self.list.count() < 2:
            return
        out_path, _ = QFileDialog.getSaveFileName(self, "書き出し先", "mix.mp3")
        if not out_path:
            return
        files = [Path(self.list.item(i).text())
                 for i in range(self.list.count())]
        ov = self.overlap.value()
        self.worker = Worker(crossfade_sequence, files, Path(
            out_path), ov, "tri", "tri", "libmp3lame")
        self.worker.start()


class NormalizeTab(QWidget):
    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("ここにLoudSyncのプリセット選択や一括処理UIを配置"))
        # 既存LoudSync関数/CLI呼び出しをここに実装


class Main(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("LoudSync Suite")
        tabs = QTabWidget()
        tabs.addTab(NormalizeTab(), "Normalize")
        tabs.addTab(FadeTab(),      "Fade")
        tabs.addTab(CrossfadeTab(), "Crossfade")
        self.setCentralWidget(tabs)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = Main()
    w.resize(900, 600)
    w.show()
    sys.exit(app.exec())
