#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LoudSync Suite GUI - PySide6ベースのタブ分割GUI
フェード・クロスフェード統合インターフェース
"""

from audioops.pipeline import (
    PipelineConfig, run_pipeline, create_preset_config,
    save_config, load_config
)
from audioops.core import fade_file, crossfade_sequence, duration_sec
import sys
import os
import json
import shutil
from pathlib import Path
from typing import List, Dict, Optional

import os
import sys
import json
import shutil
from pathlib import Path
from typing import List, Dict, Optional
import logging
from datetime import datetime

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QTabWidget, QVBoxLayout, QHBoxLayout,
    QListWidget, QPushButton, QFileDialog, QSpinBox, QDoubleSpinBox, QLabel,
    QAbstractItemView, QComboBox, QCheckBox, QTextEdit, QProgressBar,
    QStatusBar, QGroupBox, QFormLayout, QMessageBox, QSplitter, QRadioButton
)
from PySide6.QtCore import Qt, QThread, Signal, QMimeData
from PySide6.QtGui import QDragEnterEvent, QDropEvent

# audioops モジュールをインポート
sys.path.append(str(Path(__file__).parent.parent))


class DropListWidget(QListWidget):
    """ドラッグ&ドロップ対応のリストウィジェット"""

    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setDefaultDropAction(Qt.MoveAction)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event: QDropEvent):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                file_path = Path(url.toLocalFile())
                if file_path.is_file() and file_path.suffix.lower() in ['.wav', '.mp3', '.m4a', '.flac']:
                    self.addItem(str(file_path))
            event.acceptProposedAction()
        else:
            super().dropEvent(event)


class ProcessWorker(QThread):
    """処理用ワーカースレッド"""

    finished = Signal(bool, str)  # success, message
    progress = Signal(str)  # progress message
    error = Signal(str)  # error message

    def __init__(self, task_func, *args, **kwargs):
        super().__init__()
        self.task_func = task_func
        self.args = args
        self.kwargs = kwargs

    def run(self):
        try:
            result = self.task_func(*self.args, **self.kwargs)
            if result:
                self.finished.emit(True, "処理が正常に完了しました")
            else:
                self.finished.emit(False, "処理中にエラーが発生しました")
        except Exception as e:
            self.error.emit(f"処理エラー: {str(e)}")
            self.finished.emit(False, str(e))


class NormalizeTab(QWidget):
    """正規化タブ"""

    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        # 入力フォルダ設定
        input_group = QGroupBox("入力設定")
        input_layout = QFormLayout(input_group)

        self.input_dir_edit = QLabel("入力フォルダが選択されていません")
        btn_input_dir = QPushButton("フォルダ選択")
        btn_input_dir.clicked.connect(self.select_input_dir)

        input_dir_layout = QHBoxLayout()
        input_dir_layout.addWidget(self.input_dir_edit)
        input_dir_layout.addWidget(btn_input_dir)
        input_layout.addRow("入力フォルダ:", input_dir_layout)

        layout.addWidget(input_group)

        # モード選択
        mode_group = QGroupBox("処理モード")
        mode_layout = QVBoxLayout(mode_group)

        self.mode_normalize_radio = QRadioButton("正規化")
        self.mode_normalize_radio.setChecked(True)
        self.mode_normalize_radio.toggled.connect(self.on_mode_changed)
        mode_layout.addWidget(self.mode_normalize_radio)

        self.mode_measure_radio = QRadioButton("測定のみ")
        self.mode_measure_radio.toggled.connect(self.on_mode_changed)
        mode_layout.addWidget(self.mode_measure_radio)

        # self.mode_pipeline_radio = QRadioButton("一括パイプライン（正規化→フェード→書き出し）")
        # self.mode_pipeline_radio.toggled.connect(self.on_mode_changed)
        # mode_layout.addWidget(self.mode_pipeline_radio)

        layout.addWidget(mode_group)

        # 正規化設定
        self.settings_group = QGroupBox("正規化設定")
        settings_layout = QFormLayout(self.settings_group)

        self.preset_combo = QComboBox()
        self.preset_combo.addItems([
            "ポッドキャスト (-16 LUFS)",
            "BGM (-18 LUFS)",
            "BGM (-19 LUFS)",
            "BGM (-20 LUFS)",
            "放送 (-23 LUFS)",
            "参照ファイル"
        ])
        self.preset_combo.currentIndexChanged.connect(self.on_preset_changed)
        settings_layout.addRow("プリセット:", self.preset_combo)

        # 参照ファイル設定
        self.reference_file_edit = QLabel("参照ファイルが選択されていません")
        btn_reference_file = QPushButton("選択")
        btn_reference_file.clicked.connect(self.select_reference_file)

        self.reference_file_layout = QHBoxLayout()
        self.reference_file_layout.addWidget(self.reference_file_edit)
        self.reference_file_layout.addWidget(btn_reference_file)

        self.reference_file_widget = QWidget()
        self.reference_file_widget.setLayout(self.reference_file_layout)

        settings_layout.addRow("参照ファイル:", self.reference_file_widget)
        self.reference_file_form_row = settings_layout.rowCount() - 1

        self.format_combo = QComboBox()
        self.format_combo.addItems(["WAV", "MP3", "M4A"])
        settings_layout.addRow("出力形式:", self.format_combo)

        self.sample_rate_combo = QComboBox()
        self.sample_rate_combo.addItems(["44100", "48000", "96000"])
        self.sample_rate_combo.setCurrentText("48000")
        settings_layout.addRow("サンプルレート:", self.sample_rate_combo)

        self.two_pass_check = QCheckBox("2パス正規化（高精度）")
        self.two_pass_check.setChecked(True)
        settings_layout.addRow("オプション:", self.two_pass_check)

        layout.addWidget(self.settings_group)

        # 出力設定
        output_group = QGroupBox("出力設定")
        output_layout = QFormLayout(output_group)

        self.output_dir_edit = QLabel("出力フォルダが選択されていません")
        btn_output_dir = QPushButton("選択")
        btn_output_dir.clicked.connect(self.select_output_dir)

        output_dir_layout = QHBoxLayout()
        output_dir_layout.addWidget(self.output_dir_edit)
        output_dir_layout.addWidget(btn_output_dir)
        output_layout.addRow("出力フォルダ:", output_dir_layout)

        layout.addWidget(self.settings_group)

        # パイプライン設定（パイプラインモード時のみ有効）
        self.pipeline_group = QGroupBox("パイプライン設定")
        pipeline_layout = QFormLayout(self.pipeline_group)

        self.fade_enable_check = QCheckBox("フェード処理を含む")
        pipeline_layout.addRow("フェード:", self.fade_enable_check)

        self.crossfade_enable_check = QCheckBox("クロスフェード連結を含む")
        pipeline_layout.addRow("クロスフェード:", self.crossfade_enable_check)

        # layout.addWidget(self.pipeline_group)

        # 出力設定
        self.output_group = QGroupBox("出力設定")
        output_layout = QFormLayout(self.output_group)

        # 出力フォルダ設定
        self.output_dir_edit = QLabel("出力フォルダが選択されていません")
        btn_output_dir = QPushButton("選択")
        btn_output_dir.clicked.connect(self.select_output_dir)

        self.output_dir_layout = QHBoxLayout()
        self.output_dir_layout.addWidget(self.output_dir_edit)
        self.output_dir_layout.addWidget(btn_output_dir)

        # 出力フォルダ行を保存（ラベルも含めて制御）
        self.output_dir_widget = QWidget()
        self.output_dir_widget.setLayout(self.output_dir_layout)

        # 出力ファイル設定
        self.output_file_edit = QLabel("出力ファイルが選択されていません")
        btn_output_file = QPushButton("選択")
        btn_output_file.clicked.connect(self.select_output_file)

        self.output_file_layout = QHBoxLayout()
        self.output_file_layout.addWidget(self.output_file_edit)
        self.output_file_layout.addWidget(btn_output_file)

        # 出力ファイル行を保存（ラベルも含めて制御）
        self.output_file_widget = QWidget()
        self.output_file_widget.setLayout(self.output_file_layout)

        # 初期状態ではフォルダのみ表示（後でon_mode_changedで制御）
        output_layout.addRow("出力フォルダ:", self.output_dir_widget)
        self.output_dir_form_row = output_layout.rowCount() - 1

        output_layout.addRow("出力ファイル:", self.output_file_widget)
        self.output_file_form_row = output_layout.rowCount() - 1

        layout.addWidget(self.output_group)

        # 実行ボタン
        btn_layout = QHBoxLayout()
        self.btn_execute = QPushButton("実行")
        self.btn_execute.clicked.connect(self.run_execute)
        btn_layout.addWidget(self.btn_execute)

        # 設定保存ボタン
        self.btn_save_config = QPushButton("設定保存")
        self.btn_save_config.clicked.connect(self.save_config)
        btn_layout.addWidget(self.btn_save_config)

        # 設定読込ボタン
        self.btn_load_config = QPushButton("設定読込")
        self.btn_load_config.clicked.connect(self.load_config)
        btn_layout.addWidget(self.btn_load_config)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        layout.addStretch()

        # 初期状態設定
        self.on_mode_changed()
        self.on_preset_changed()  # 参照ファイル機能の初期表示制御

    def select_reference_file(self):
        """参照ファイルを選択"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "参照ファイルを選択", "",
            "Audio Files (*.wav *.mp3 *.m4a *.flac);;All Files (*)"
        )
        if file_path:
            self.reference_file_edit.setText(file_path)

    def on_preset_changed(self):
        """プリセット変更時の処理"""
        is_reference = self.preset_combo.currentIndex() == 5  # 参照ファイルは6番目（インデックス5）

        # 参照ファイル行の表示制御
        settings_layout = self.settings_group.layout()
        label_widget = settings_layout.itemAt(
            self.reference_file_form_row, QFormLayout.LabelRole)
        field_widget = settings_layout.itemAt(
            self.reference_file_form_row, QFormLayout.FieldRole)

        if label_widget and label_widget.widget():
            label_widget.widget().setVisible(is_reference)
        if field_widget and field_widget.widget():
            field_widget.widget().setVisible(is_reference)

    def select_input_dir(self):
        """入力フォルダを選択"""
        dir_path = QFileDialog.getExistingDirectory(self, "入力フォルダを選択")
        if dir_path:
            self.input_dir_edit.setText(dir_path)

    def select_output_dir(self):
        """出力フォルダを選択"""
        dir_path = QFileDialog.getExistingDirectory(self, "出力フォルダを選択")
        if dir_path:
            self.output_dir_edit.setText(dir_path)

    def select_output_file(self):
        """出力ファイルを選択（パイプライン用）"""
        file_path, _ = QFileDialog.getSaveFileName(
            self, "出力ファイルを指定", "",
            "Audio Files (*.wav *.mp3 *.m4a);;All Files (*)"
        )
        if file_path:
            self.output_file_edit.setText(file_path)

    def on_mode_changed(self):
        """モード変更時の処理"""
        is_normalize = self.mode_normalize_radio.isChecked()
        is_measure = self.mode_measure_radio.isChecked()
        # is_pipeline = self.mode_pipeline_radio.isChecked()

        # 測定のみモードでは正規化設定を無効化
        self.settings_group.setEnabled(not is_measure)

        # パイプライン設定の表示制御
        # self.pipeline_group.setVisible(is_pipeline)

        # 出力設定の制御
        # 測定のみ：出力設定を無効化（自動でCSV出力）
        # 正規化：出力フォルダのみ表示・有効
        # パイプライン：出力ファイルのみ表示・有効

        # 測定のみモードでは出力設定全体を無効化
        self.output_group.setEnabled(not is_measure)

        # QFormLayoutの行全体（ラベル+ウィジェット）を制御
        output_layout = self.output_group.layout()

        # 出力フォルダ行の表示制御（測定・正規化モードで表示、パイプラインは無効化済み）
        label_widget_dir = output_layout.itemAt(
            self.output_dir_form_row, QFormLayout.LabelRole)
        field_widget_dir = output_layout.itemAt(
            self.output_dir_form_row, QFormLayout.FieldRole)

        # 出力フォルダ行は常に表示（パイプライン機能は無効化済み）
        if label_widget_dir and label_widget_dir.widget():
            label_widget_dir.widget().setVisible(True)
        if field_widget_dir and field_widget_dir.widget():
            field_widget_dir.widget().setVisible(True)

        # 出力ファイル行の表示制御（パイプライン無効化により常に非表示）
        label_widget_file = output_layout.itemAt(
            self.output_file_form_row, QFormLayout.LabelRole)
        field_widget_file = output_layout.itemAt(
            self.output_file_form_row, QFormLayout.FieldRole)

        # 出力ファイル行は常に非表示（パイプライン機能は無効化済み）
        if label_widget_file and label_widget_file.widget():
            label_widget_file.widget().setVisible(False)
        if field_widget_file and field_widget_file.widget():
            field_widget_file.widget().setVisible(False)        # 実行ボタンのテキスト変更
        if is_measure:
            self.btn_execute.setText("測定実行")
            # 測定のみモードでは出力設定のタイトルを変更
            self.output_group.setTitle("出力設定（自動でCSVファイルを生成）")
        elif is_normalize:
            self.btn_execute.setText("正規化実行")
            self.output_group.setTitle("出力設定")
        # elif is_pipeline:
        #    self.btn_execute.setText("パイプライン実行")
        #    self.output_group.setTitle("出力設定")

        # 設定保存・読込ボタンの表示制御（測定のみモードでは非表示）
        self.btn_save_config.setVisible(not is_measure)
        self.btn_load_config.setVisible(not is_measure)

    def get_input_files(self) -> List[Path]:
        """入力フォルダから音声ファイルを取得"""
        input_dir = self.input_dir_edit.text()
        if input_dir == "入力フォルダが選択されていません":
            return []

        input_path = Path(input_dir)
        if not input_path.exists():
            return []

        files = []
        extensions = ['.wav', '.mp3', '.m4a', '.flac']
        for ext in extensions:
            files.extend(input_path.glob(f"**/*{ext}"))

        return sorted(files)

    def run_execute(self):
        """実行処理"""
        files = self.get_input_files()
        if not files:
            QMessageBox.warning(self, "警告", "入力フォルダに音声ファイルが見つかりません")
            return

        if self.mode_measure_radio.isChecked():
            self.run_measure(files)
        elif self.mode_normalize_radio.isChecked():
            self.run_normalize(files)
        # elif self.mode_pipeline_radio.isChecked():
        #     self.run_pipeline(files)

    def run_measure(self, files: List[Path]):
        """測定のみ実行"""
        output_dir = self.output_dir_edit.text()
        if output_dir == "出力フォルダが選択されていません":
            QMessageBox.warning(self, "警告", "出力フォルダを選択してください")
            return

        # ログファイルのパスを更新
        self.main_window.update_log_file_path(output_dir)

        self.main_window.log_message(f"測定処理開始: {len(files)}ファイル")

        def measure_task():
            try:
                from audioops.loudsync_legacy import measure_loudness, find_ffmpeg
                import csv

                ffmpeg_path = find_ffmpeg()
                results = []

                for i, file_path in enumerate(files, 1):
                    self.main_window.log_message(
                        f"[{i}/{len(files)}] 測定中: {file_path.name}")

                    result = measure_loudness(str(file_path), ffmpeg_path)
                    results.append(result)

                    if result['status'] == 'OK':
                        self.main_window.log_message(
                            f"  LUFS: {result['integrated_lufs']:.1f} | "
                            f"TP: {result['true_peak_dbtp']:.1f} | "
                            f"LRA: {result['loudness_range']:.1f}"
                        )
                    else:
                        self.main_window.log_message(
                            f"  測定失敗: {result['status']}")

                # CSV保存
                csv_path = Path(output_dir) / "loudness_measurement.csv"
                with open(csv_path, 'w', newline='', encoding='utf-8') as csvfile:
                    fieldnames = ['file', 'integrated_lufs',
                                  'loudness_range', 'true_peak_dbtp', 'status']
                    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                    writer.writeheader()
                    for result in results:
                        writer.writerow({
                            'file': Path(result['file']).name,
                            'integrated_lufs': result['integrated_lufs'],
                            'loudness_range': result['loudness_range'],
                            'true_peak_dbtp': result['true_peak_dbtp'],
                            'status': result['status']
                        })

                self.main_window.log_message(f"測定結果をCSVに保存: {csv_path}")
                return True
            except Exception as e:
                self.main_window.log_message(f"エラー: {str(e)}")
                return False

        self.worker = ProcessWorker(measure_task)
        self.worker.finished.connect(self.main_window.on_process_finished)
        self.worker.start()

    def save_config(self):
        """現在の設定をJSONファイルに保存"""
        try:
            # 現在の設定を取得
            config = {
                "input_directory": self.input_dir_edit.text(),
                "output_directory": self.output_dir_edit.text(),
                "mode": {
                    "measure_only": self.mode_measure_radio.isChecked(),
                    "normalize": self.mode_normalize_radio.isChecked(),
                    # "pipeline": self.mode_pipeline_radio.isChecked() if hasattr(self, 'mode_pipeline_radio') else False
                },
                "preset_index": self.preset_combo.currentIndex(),
                "preset_name": self.preset_combo.currentText(),
                "reference_file": self.reference_file_edit.text() if hasattr(self, 'reference_file_edit') else "",
                "output_format": self.format_combo.currentText(),
                "saved_at": str(Path().cwd())
            }

            # ファイルダイアログで保存先を選択
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "設定ファイルを保存",
                "config.json",
                "JSON files (*.json);;All files (*.*)"
            )

            if file_path:
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(config, f, ensure_ascii=False, indent=2)

                QMessageBox.information(
                    self, "設定保存", f"設定が保存されました:\n{file_path}")
                self.main_window.log_message(f"設定を保存しました: {file_path}")

        except Exception as e:
            QMessageBox.critical(self, "エラー", f"設定保存中にエラーが発生しました:\n{str(e)}")
            self.main_window.log_message(f"設定保存エラー: {str(e)}")

    def load_config(self):
        """設定をJSONファイルから読み込み"""
        try:
            # ファイルダイアログで読み込みファイルを選択
            file_path, _ = QFileDialog.getOpenFileName(
                self,
                "設定ファイルを読み込み",
                "",
                "JSON files (*.json);;All files (*.*)"
            )

            if not file_path:
                return

            with open(file_path, 'r', encoding='utf-8') as f:
                config = json.load(f)

            # 設定を復元
            if "input_directory" in config and config["input_directory"] != "入力フォルダが選択されていません":
                self.input_dir_edit.setText(config["input_directory"])

            if "output_directory" in config and config["output_directory"] != "出力フォルダが選択されていません":
                self.output_dir_edit.setText(config["output_directory"])

            if "mode" in config:
                mode = config["mode"]
                if mode.get("measure_only", False):
                    self.mode_measure_radio.setChecked(True)
                elif mode.get("normalize", False):
                    self.mode_normalize_radio.setChecked(True)
                # elif mode.get("pipeline", False) and hasattr(self, 'mode_pipeline_radio'):
                #     self.mode_pipeline_radio.setChecked(True)

            if "preset_index" in config:
                preset_idx = config["preset_index"]
                if 0 <= preset_idx < self.preset_combo.count():
                    self.preset_combo.setCurrentIndex(preset_idx)

            if "reference_file" in config and hasattr(self, 'reference_file_edit'):
                ref_file = config["reference_file"]
                if ref_file and ref_file != "参照ファイルが選択されていません":
                    self.reference_file_edit.setText(ref_file)

            if "output_format" in config:
                format_text = config["output_format"]
                format_idx = self.format_combo.findText(format_text)
                if format_idx >= 0:
                    self.format_combo.setCurrentIndex(format_idx)

            # モード変更とプリセット変更を反映
            self.on_mode_changed()
            self.on_preset_changed()

            QMessageBox.information(self, "設定読込", f"設定が読み込まれました:\n{file_path}")
            self.main_window.log_message(f"設定を読み込みました: {file_path}")

        except Exception as e:
            QMessageBox.critical(self, "エラー", f"設定読込中にエラーが発生しました:\n{str(e)}")
            self.main_window.log_message(f"設定読込エラー: {str(e)}")

    def run_normalize(self, files: List[Path]):
        """正規化実行"""
        output_dir = self.output_dir_edit.text()
        if output_dir == "出力フォルダが選択されていません":
            QMessageBox.warning(self, "警告", "出力フォルダを選択してください")
            return

        # ログファイルのパスを更新
        self.main_window.update_log_file_path(output_dir)

        # プリセット設定を取得
        preset_index = self.preset_combo.currentIndex()

        if preset_index == 5:  # 参照ファイル
            reference_file = self.reference_file_edit.text()
            if reference_file == "参照ファイルが選択されていません":
                QMessageBox.warning(self, "警告", "参照ファイルを選択してください")
                return

            # 参照ファイルのラウドネスを測定
            self.main_window.log_message(
                f"参照ファイルのラウドネスを測定中: {Path(reference_file).name}")

            try:
                from audioops.loudsync_legacy import measure_loudness, find_ffmpeg
                ffmpeg_path = find_ffmpeg()
                ref_result = measure_loudness(reference_file, ffmpeg_path)

                if ref_result['status'] != 'OK':
                    QMessageBox.critical(
                        self, "エラー", f"参照ファイルの測定に失敗しました: {ref_result['status']}")
                    return

                target_lufs = ref_result['integrated_lufs']
                self.main_window.log_message(
                    f"参照ファイルのラウドネス: {target_lufs:.1f} LUFS")

            except Exception as e:
                QMessageBox.critical(self, "エラー", f"参照ファイルの測定エラー: {str(e)}")
                return
        else:
            # 固定プリセット
            preset_map = {
                0: -16.0,  # ポッドキャスト
                1: -18.0,  # BGM -18
                2: -19.0,  # BGM -19
                3: -20.0,  # BGM -20
                4: -23.0   # 放送
            }
            target_lufs = preset_map.get(preset_index, -16.0)

        # 出力形式設定
        format_map = {"WAV": "wav", "MP3": "mp3", "M4A": "m4a"}
        output_format = format_map[self.format_combo.currentText()]

        # サンプルレート
        sample_rate = int(self.sample_rate_combo.currentText())

        # 2パス処理
        two_pass = self.two_pass_check.isChecked()

        self.main_window.log_message(f"正規化処理開始: {len(files)}ファイル")
        self.main_window.log_message(
            f"ターゲット: {target_lufs} LUFS, 形式: {output_format.upper()}, {sample_rate}Hz")

        def normalize_task():
            try:
                from audioops.loudsync_legacy import normalize_audio, find_ffmpeg

                ffmpeg_path = find_ffmpeg()
                output_path = Path(output_dir)
                output_path.mkdir(parents=True, exist_ok=True)

                success_count = 0

                for i, file_path in enumerate(files, 1):
                    self.main_window.log_message(
                        f"[{i}/{len(files)}] 正規化中: {file_path.name}")

                    # 出力ファイル名を決定
                    output_file = output_path / \
                        f"{file_path.stem}_normalized.{output_format}"

                    # 正規化実行
                    success = normalize_audio(
                        str(file_path),
                        str(output_file),
                        target_i=target_lufs,
                        target_tp=-2.0,  # True Peak を -2dB に設定
                        sample_rate=sample_rate,
                        output_format=output_format,
                        two_pass=two_pass,
                        ffmpeg_path=ffmpeg_path
                    )

                    if success:
                        self.main_window.log_message(
                            f"  ✓ 完了: {output_file.name}")
                        success_count += 1
                    else:
                        self.main_window.log_message(
                            f"  ✗ 失敗: {file_path.name}")

                self.main_window.log_message(
                    f"正規化完了: {success_count}/{len(files)} ファイル成功")
                return success_count > 0

            except Exception as e:
                self.main_window.log_message(f"エラー: {str(e)}")
                return False

        self.worker = ProcessWorker(normalize_task)
        self.worker.finished.connect(self.main_window.on_process_finished)
        self.worker.start()

    def run_pipeline(self, files: List[Path]):
        """パイプライン実行"""
        output_file = self.output_file_edit.text()
        if output_file == "出力ファイルが選択されていません":
            QMessageBox.warning(self, "警告", "出力ファイルを選択してください")
            return

        # プリセット設定を作成
        preset_map = {
            0: "podcast",
            1: "bgm",
            2: "bgm",
            3: "bgm",
            4: "broadcast"
        }
        preset_name = preset_map.get(
            self.preset_combo.currentIndex(), "podcast")

        from audioops.pipeline import create_preset_config
        config = create_preset_config(preset_name)

        # パイプライン設定を反映
        config.fade['enabled'] = self.fade_enable_check.isChecked()
        config.crossfade['enabled'] = self.crossfade_enable_check.isChecked()

        self.main_window.log_message(f"一括パイプライン開始: {len(files)}ファイル")

        def pipeline_task():
            from audioops.pipeline import run_pipeline
            return run_pipeline(files, Path(output_file), config)

        self.worker = ProcessWorker(pipeline_task)
        self.worker.finished.connect(self.main_window.on_process_finished)
        self.worker.start()

    def select_output_dir(self):
        """出力フォルダを選択"""
        dir_path = QFileDialog.getExistingDirectory(self, "出力フォルダを選択")
        if dir_path:
            self.output_dir_edit.setText(dir_path)

    def select_output_file(self):
        """出力ファイルを選択（パイプライン用）"""
        file_path, _ = QFileDialog.getSaveFileName(
            self, "出力ファイルを指定", "",
            "Audio Files (*.wav *.mp3 *.m4a);;All Files (*)"
        )
        if file_path:
            self.output_file_edit.setText(file_path)


class FadeTab(QWidget):
    """フェードタブ"""

    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        # ファイルリスト
        file_group = QGroupBox("入力ファイル")
        file_layout = QVBoxLayout(file_group)

        self.file_list = DropListWidget()
        file_layout.addWidget(QLabel("音声ファイルをドラッグ&ドロップしてください"))
        file_layout.addWidget(self.file_list)

        # ボタン
        btn_layout = QHBoxLayout()
        btn_add = QPushButton("ファイル追加")
        btn_add.clicked.connect(self.add_files)
        btn_clear = QPushButton("クリア")
        btn_clear.clicked.connect(self.file_list.clear)
        btn_layout.addWidget(btn_add)
        btn_layout.addWidget(btn_clear)
        btn_layout.addStretch()
        file_layout.addLayout(btn_layout)

        layout.addWidget(file_group)

        # フェード設定
        fade_group = QGroupBox("フェード設定")
        fade_layout = QFormLayout(fade_group)

        self.fade_in_spin = QSpinBox()
        self.fade_in_spin.setRange(0, 60000)
        self.fade_in_spin.setValue(300)
        self.fade_in_spin.setSuffix(" ms")
        fade_layout.addRow("フェードイン:", self.fade_in_spin)

        # フェードアウト設定は「末尾から」の設定で自動決定されるため、GUIからは削除

        self.from_end_spin = QDoubleSpinBox()
        self.from_end_spin.setRange(0.0, 60.0)
        self.from_end_spin.setValue(2.0)
        self.from_end_spin.setSuffix(" 秒")
        fade_layout.addRow("フェードアウト(末尾から):", self.from_end_spin)

        self.codec_combo = QComboBox()
        self.codec_combo.addItems(["aac", "libmp3lame", "pcm_s16le"])
        fade_layout.addRow("コーデック:", self.codec_combo)

        layout.addWidget(fade_group)

        # 出力設定
        output_group = QGroupBox("出力設定")
        output_layout = QFormLayout(output_group)

        self.output_dir_edit = QLabel("出力フォルダが選択されていません")
        btn_output_dir = QPushButton("選択")
        btn_output_dir.clicked.connect(self.select_output_dir)

        output_dir_layout = QHBoxLayout()
        output_dir_layout.addWidget(self.output_dir_edit)
        output_dir_layout.addWidget(btn_output_dir)
        output_layout.addRow("出力フォルダ:", output_dir_layout)

        layout.addWidget(output_group)

        # 実行ボタン
        btn_process = QPushButton("フェード処理実行")
        btn_process.clicked.connect(self.run_fade)
        layout.addWidget(btn_process)

        layout.addStretch()

    def add_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "音声ファイルを選択", "",
            "Audio Files (*.wav *.mp3 *.m4a *.flac);;All Files (*)"
        )
        for file_path in files:
            self.file_list.addItem(file_path)

    def select_output_dir(self):
        dir_path = QFileDialog.getExistingDirectory(self, "出力フォルダを選択")
        if dir_path:
            self.output_dir_edit.setText(dir_path)

    def get_files(self) -> List[Path]:
        files = []
        for i in range(self.file_list.count()):
            files.append(Path(self.file_list.item(i).text()))
        return files

    def run_fade(self):
        files = self.get_files()
        if not files:
            QMessageBox.warning(self, "警告", "処理するファイルがありません")
            return

        output_dir = self.output_dir_edit.text()
        if output_dir == "出力フォルダが選択されていません":
            QMessageBox.warning(self, "警告", "出力フォルダを選択してください")
            return

        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        # ログファイルのパスを更新
        self.main_window.update_log_file_path(output_dir)

        self.main_window.log_message(f"フェード処理開始: {len(files)}ファイル")

        def fade_task():
            try:
                for i, file_path in enumerate(files, 1):
                    self.main_window.log_message(
                        f"[{i}/{len(files)}] Processing: {file_path.name}")

                    # 出力ファイル名
                    output_file = output_path / \
                        f"{file_path.stem}_fade{file_path.suffix}"

                    # フェード処理（コーデックは拡張子から自動選択）
                    # フェードアウト時間は「末尾から」の設定値と同じ秒数に自動設定
                    fade_out_duration_sec = self.from_end_spin.value()
                    fade_out_ms = int(fade_out_duration_sec * 1000)  # 秒をミリ秒に変換

                    fade_file(
                        file_path, output_file,
                        fade_in_ms=self.fade_in_spin.value(),
                        fade_out_ms=fade_out_ms,
                        fade_out_from_end_sec=self.from_end_spin.value()
                    )

                    self.main_window.log_message(
                        f"  ✓ Completed: {output_file.name}")

                return True
            except Exception as e:
                self.main_window.log_message(f"エラー: {str(e)}")
                return False

        self.worker = ProcessWorker(fade_task)
        self.worker.finished.connect(self.main_window.on_process_finished)
        self.worker.start()


class CrossfadeTab(QWidget):
    """クロスフェードタブ"""

    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        # ファイルリスト
        file_group = QGroupBox("入力ファイル（順序 = 再生順）")
        file_layout = QVBoxLayout(file_group)

        self.file_list = DropListWidget()
        file_layout.addWidget(QLabel("音声ファイルをドラッグ&ドロップしてください（2ファイル以上必要）"))
        file_layout.addWidget(self.file_list)

        # ボタン
        btn_layout = QHBoxLayout()
        btn_add = QPushButton("ファイル追加")
        btn_add.clicked.connect(self.add_files)
        btn_clear = QPushButton("クリア")
        btn_clear.clicked.connect(self.file_list.clear)
        btn_up = QPushButton("↑")
        btn_up.clicked.connect(self.move_up)
        btn_down = QPushButton("↓")
        btn_down.clicked.connect(self.move_down)
        btn_layout.addWidget(btn_add)
        btn_layout.addWidget(btn_clear)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_up)
        btn_layout.addWidget(btn_down)
        file_layout.addLayout(btn_layout)

        layout.addWidget(file_group)

        # クロスフェード設定
        crossfade_group = QGroupBox("クロスフェード設定")
        crossfade_layout = QFormLayout(crossfade_group)

        self.overlap_spin = QDoubleSpinBox()
        self.overlap_spin.setRange(0.1, 60.0)
        self.overlap_spin.setValue(2.0)
        self.overlap_spin.setSuffix(" 秒")
        crossfade_layout.addRow("オーバーラップ:", self.overlap_spin)

        self.curve_combo = QComboBox()
        self.curve_combo.addItems(
            ["tri", "qsin", "esin", "hsin", "log", "ipar", "qua", "cub", "squ", "cbr"])
        crossfade_layout.addRow("カーブ:", self.curve_combo)

        self.codec_combo = QComboBox()
        self.codec_combo.addItems(["libmp3lame", "aac", "pcm_s16le"])
        crossfade_layout.addRow("コーデック:", self.codec_combo)

        layout.addWidget(crossfade_group)

        # 出力設定
        output_group = QGroupBox("出力設定")
        output_layout = QFormLayout(output_group)

        self.output_file_edit = QLabel("出力ファイルが選択されていません")
        btn_output_file = QPushButton("選択")
        btn_output_file.clicked.connect(self.select_output_file)

        output_file_layout = QHBoxLayout()
        output_file_layout.addWidget(self.output_file_edit)
        output_file_layout.addWidget(btn_output_file)
        output_layout.addRow("出力ファイル:", output_file_layout)

        layout.addWidget(output_group)

        # 実行ボタン
        btn_process = QPushButton("クロスフェード連結実行")
        btn_process.clicked.connect(self.run_crossfade)
        layout.addWidget(btn_process)

        layout.addStretch()

    def add_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "音声ファイルを選択", "",
            "Audio Files (*.wav *.mp3 *.m4a *.flac);;All Files (*)"
        )
        for file_path in files:
            self.file_list.addItem(file_path)

    def move_up(self):
        current_row = self.file_list.currentRow()
        if current_row > 0:
            item = self.file_list.takeItem(current_row)
            self.file_list.insertItem(current_row - 1, item)
            self.file_list.setCurrentRow(current_row - 1)

    def move_down(self):
        current_row = self.file_list.currentRow()
        if current_row < self.file_list.count() - 1:
            item = self.file_list.takeItem(current_row)
            self.file_list.insertItem(current_row + 1, item)
            self.file_list.setCurrentRow(current_row + 1)

    def select_output_file(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self, "出力ファイルを指定", "mix.mp3",
            "Audio Files (*.wav *.mp3 *.m4a);;All Files (*)"
        )
        if file_path:
            self.output_file_edit.setText(file_path)

    def get_files(self) -> List[Path]:
        files = []
        for i in range(self.file_list.count()):
            files.append(Path(self.file_list.item(i).text()))
        return files

    def run_crossfade(self):
        files = self.get_files()
        if len(files) < 2:
            QMessageBox.warning(self, "警告", "クロスフェードには2ファイル以上が必要です")
            return

        output_file = self.output_file_edit.text()
        if output_file == "出力ファイルが選択されていません":
            QMessageBox.warning(self, "警告", "出力ファイルを選択してください")
            return

        self.main_window.log_message(f"クロスフェード処理開始: {len(files)}ファイル")

        def crossfade_task():
            try:
                crossfade_sequence(
                    files, Path(output_file),
                    overlap_sec=self.overlap_spin.value(),
                    curve1=self.curve_combo.currentText(),
                    curve2=self.curve_combo.currentText(),
                    codec=self.codec_combo.currentText()
                )
                return True
            except Exception as e:
                self.main_window.log_message(f"エラー: {str(e)}")
                return False

        self.worker = ProcessWorker(crossfade_task)
        self.worker.finished.connect(self.main_window.on_process_finished)
        self.worker.start()


class LoudSyncSuiteMainWindow(QMainWindow):
    """LoudSync Suite メインウィンドウ"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("LoudSync Suite - フェード/クロスフェード統合")
        self.setGeometry(100, 100, 1000, 700)

        # 設定
        self.config_path = "config.json"

        # ログ設定の初期化
        self.log_file_path = None
        self.setup_logging()

        self.setup_ui()
        self.load_settings()

    def setup_logging(self):
        """ログ設定を初期化"""
        # デフォルトの出力ディレクトリは normalized フォルダ
        default_output_dir = Path("normalized")
        default_output_dir.mkdir(parents=True, exist_ok=True)

        self.log_file_path = default_output_dir / "LoudSync.log"

        # ログファイルのハンドラを設定
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        # ファイルハンドラを追加
        self.file_handler = logging.FileHandler(
            self.log_file_path, encoding='utf-8')
        self.file_handler.setLevel(logging.INFO)
        formatter = logging.Formatter(
            '%(asctime)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
        self.file_handler.setFormatter(formatter)

        # ルートロガーにハンドラを追加
        logging.getLogger().addHandler(self.file_handler)

    def update_log_file_path(self, output_dir: str):
        """ログファイルのパスを更新"""
        if output_dir and output_dir != "出力フォルダが選択されていません":
            new_log_path = Path(output_dir) / "LoudSync.log"
            if new_log_path != self.log_file_path:
                # 古いハンドラを削除
                if hasattr(self, 'file_handler'):
                    logging.getLogger().removeHandler(self.file_handler)
                    self.file_handler.close()

                # 新しいハンドラを設定
                self.log_file_path = new_log_path
                self.file_handler = logging.FileHandler(
                    self.log_file_path, encoding='utf-8')
                self.file_handler.setLevel(logging.INFO)
                formatter = logging.Formatter(
                    '%(asctime)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
                self.file_handler.setFormatter(formatter)
                logging.getLogger().addHandler(self.file_handler)

    def setup_ui(self):
        # 中央ウィジェット
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # メインレイアウト
        main_layout = QVBoxLayout(central_widget)

        # 上下分割
        splitter = QSplitter(Qt.Vertical)
        main_layout.addWidget(splitter)

        # タブウィジェット
        self.tab_widget = QTabWidget()
        splitter.addWidget(self.tab_widget)

        # タブ作成
        self.normalize_tab = NormalizeTab(self)
        self.fade_tab = FadeTab(self)
        self.crossfade_tab = CrossfadeTab(self)

        self.tab_widget.addTab(self.normalize_tab, "Normalize")
        self.tab_widget.addTab(self.fade_tab, "Fade")
        self.tab_widget.addTab(self.crossfade_tab, "Crossfade")

        # Crossfadeタブを無効化（未来の機能として実装は保持）
        self.tab_widget.setTabEnabled(2, False)  # インデックス2のタブ（Crossfade）を無効化
        self.tab_widget.setTabToolTip(2, "Crossfade機能は将来のバージョンで利用可能になります")

        # ログエリア
        log_group = QGroupBox("ログ")
        log_layout = QVBoxLayout(log_group)

        self.log_text = QTextEdit()
        self.log_text.setMaximumHeight(200)
        self.log_text.setReadOnly(True)
        log_layout.addWidget(self.log_text)

        splitter.addWidget(log_group)
        splitter.setSizes([500, 200])

        # プログレスバー
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        main_layout.addWidget(self.progress_bar)

        # ステータスバー
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("準備完了")

        # 初期ログ
        self.log_message("LoudSync Suite を開始しました")

    def log_message(self, message: str):
        """ログメッセージを追加（GUI表示とファイル出力）"""
        from datetime import datetime
        timestamp = datetime.now().strftime("%H:%M:%S")
        gui_message = f"[{timestamp}] {message}"

        # GUIのログエリアに表示
        self.log_text.append(gui_message)

        # ファイルにも出力
        logging.info(message)

    def on_process_finished(self, success: bool, message: str):
        """処理完了時のハンドラ"""
        self.progress_bar.setVisible(False)

        if success:
            self.log_message(f"✓ {message}")
            self.status_bar.showMessage("処理完了")
            QMessageBox.information(self, "完了", message)
        else:
            self.log_message(f"✗ {message}")
            self.status_bar.showMessage("処理失敗")
            QMessageBox.critical(self, "エラー", message)

    def load_settings(self):
        """設定を読み込み"""
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    settings = json.load(f)

                self.log_message(f"設定ファイルを読み込み中: {self.config_path}")

                # Normalizeタブの設定を復元
                if hasattr(self, 'normalize_tab'):
                    if "input_directory" in settings and settings["input_directory"] != "入力フォルダが選択されていません":
                        self.normalize_tab.input_dir_edit.setText(
                            settings["input_directory"])
                        self.log_message(
                            f"入力フォルダを復元: {settings['input_directory']}")

                    if "output_directory" in settings and settings["output_directory"] != "出力フォルダが選択されていません":
                        self.normalize_tab.output_dir_edit.setText(
                            settings["output_directory"])
                        self.log_message(
                            f"出力フォルダを復元: {settings['output_directory']}")

                    if "mode" in settings:
                        mode = settings["mode"]
                        if mode.get("measure_only", False):
                            self.normalize_tab.mode_measure_radio.setChecked(
                                True)
                            self.log_message("モード: 測定のみ")
                        elif mode.get("normalize", False):
                            self.normalize_tab.mode_normalize_radio.setChecked(
                                True)
                            self.log_message("モード: 正規化")

                    if "preset_index" in settings:
                        preset_idx = settings["preset_index"]
                        if 0 <= preset_idx < self.normalize_tab.preset_combo.count():
                            self.normalize_tab.preset_combo.setCurrentIndex(
                                preset_idx)
                            self.log_message(f"プリセットを復元: {preset_idx}")

                    if "reference_file" in settings and hasattr(self.normalize_tab, 'reference_file_edit'):
                        ref_file = settings["reference_file"]
                        if ref_file and ref_file != "参照ファイルが選択されていません":
                            self.normalize_tab.reference_file_edit.setText(
                                ref_file)
                            self.log_message(f"参照ファイルを復元: {ref_file}")

                    if "output_format" in settings:
                        format_text = settings["output_format"]
                        format_idx = self.normalize_tab.format_combo.findText(
                            format_text)
                        if format_idx >= 0:
                            self.normalize_tab.format_combo.setCurrentIndex(
                                format_idx)
                            self.log_message(f"出力形式を復元: {format_text}")

                    # ウィンドウ位置とサイズの復元
                    if "window_geometry" in settings:
                        geo = settings["window_geometry"]
                        self.setGeometry(geo.get("x", 100), geo.get("y", 100),
                                         geo.get("width", 1000), geo.get("height", 700))

                    # モード変更とプリセット変更を反映
                    self.normalize_tab.on_mode_changed()
                    if hasattr(self.normalize_tab, 'on_preset_changed'):
                        self.normalize_tab.on_preset_changed()

                self.log_message("設定を正常に読み込みました")
            except Exception as e:
                self.log_message(f"設定読み込みエラー: {e}")
        else:
            self.log_message(f"設定ファイルが見つかりません: {self.config_path}")

    def save_settings(self):
        """設定を保存"""
        try:
            settings = {}

            # Normalizeタブの設定を保存
            if hasattr(self, 'normalize_tab'):
                settings.update({
                    "input_directory": self.normalize_tab.input_dir_edit.text(),
                    "output_directory": self.normalize_tab.output_dir_edit.text(),
                    "mode": {
                        "measure_only": self.normalize_tab.mode_measure_radio.isChecked(),
                        "normalize": self.normalize_tab.mode_normalize_radio.isChecked(),
                    },
                    "preset_index": self.normalize_tab.preset_combo.currentIndex(),
                    "preset_name": self.normalize_tab.preset_combo.currentText(),
                    "reference_file": getattr(self.normalize_tab, 'reference_file_edit', QLabel()).text(),
                    "output_format": self.normalize_tab.format_combo.currentText(),
                    "saved_at": str(Path().cwd()),
                    "window_geometry": {
                        "x": self.x(),
                        "y": self.y(),
                        "width": self.width(),
                        "height": self.height()
                    }
                })

            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(settings, f, indent=2, ensure_ascii=False)
            self.log_message("設定を保存しました")
        except Exception as e:
            self.log_message(f"設定保存エラー: {e}")

    def closeEvent(self, event):
        """終了時の処理"""
        self.save_settings()

        # ログハンドラをクリーンアップ
        if hasattr(self, 'file_handler'):
            logging.getLogger().removeHandler(self.file_handler)
            self.file_handler.close()

        event.accept()


def main():
    """メイン関数"""
    app = QApplication(sys.argv)

    # アプリケーション情報
    app.setApplicationName("LoudSync Suite")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("LoudSync")

    # メインウィンドウ作成
    window = LoudSyncSuiteMainWindow()
    window.show()

    # アイコン設定（あれば）
    try:
        icon_path = Path(__file__).parent.parent / "assets" / "icon.ico"
        if icon_path.exists():
            from PySide6.QtGui import QIcon
            app.setWindowIcon(QIcon(str(icon_path)))
    except Exception:
        pass

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
