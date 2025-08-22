#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LoudSync - Audio Loudness Normalization Tool (Python version)
Audio loudness measurement and normalization using EBU R128 standards.
"""

import os
import sys
import signal
import argparse
import asyncio
import threading
import json
import csv
import subprocess
import shutil
import re
import logging
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Tuple
try:
    from aioconsole import ainput
except ImportError:
    print("Warning: aioconsole not available. Interactive mode disabled.")
    ainput = None

from modules.communication.ipc_client import check_existing_instance
from modules.utils.path_utils import is_subpath

# Global variables
ffmpeg_path = None
logger = None


class LoudSyncError(Exception):
    """Custom exception for LoudSync errors."""
    pass


class LoudSyncGUI:
    """GUI window for LoudSync configuration and execution."""

    def __init__(self, args):
        self.args = args
        self.root = tk.Tk()
        self.root.title("LoudSync - Audio Loudness Normalization Tool")
        self.root.geometry("800x600")

        # Set application icon
        try:
            icon_path = Path(__file__).parent / "assets" / "icon.ico"
            if icon_path.exists():
                self.root.iconbitmap(str(icon_path))
        except Exception as e:
            print(f"Warning: Could not set application icon: {e}")

        # Variables for GUI controls
        self.input_dir_var = tk.StringVar(value=args.input_dir)
        self.output_dir_var = tk.StringVar(value=args.output_dir)
        self.mode_var = tk.StringVar(value=args.mode)
        self.preset_var = tk.StringVar(value=args.preset)
        self.out_ext_var = tk.StringVar(value=args.out_ext)
        self.sample_rate_var = tk.StringVar(value=str(args.sample_rate))
        self.two_pass_var = tk.BooleanVar(value=args.two_pass)
        self.overwrite_var = tk.BooleanVar(value=args.overwrite)

        # GUI widgets references for state control
        self.preset_label = None
        self.preset_combo = None
        self.format_label = None
        self.format_frame = None
        self.format_wav_radio = None
        self.format_mp3_radio = None
        self.format_m4a_radio = None
        self.sample_label = None
        self.sample_combo = None
        self.options_frame = None
        self.two_pass_check = None
        self.overwrite_check = None

        self.setup_gui()

    def setup_gui(self):
        """Setup the GUI components."""
        # Main frame
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)

        row = 0

        # Title
        title_label = ttk.Label(main_frame, text="フォルダ内の音声ファイルのレベルをそろえる",
                                font=('Arial', 14, 'bold'))
        title_label.grid(row=row, column=0, columnspan=3, pady=(30, 50))
        row += 1

        # Input Directory
        ttk.Label(main_frame, text="入力フォルダ:").grid(
            row=row, column=0, sticky=tk.W, pady=5)
        ttk.Entry(main_frame, textvariable=self.input_dir_var, width=50).grid(
            row=row, column=1, sticky=(tk.W, tk.E), padx=5)
        ttk.Button(main_frame, text="参照", command=self.browse_input_dir).grid(
            row=row, column=2, padx=5)
        row += 1

        # Output Directory
        ttk.Label(main_frame, text="出力フォルダ:").grid(
            row=row, column=0, sticky=tk.W, pady=5)
        ttk.Entry(main_frame, textvariable=self.output_dir_var, width=50).grid(
            row=row, column=1, sticky=(tk.W, tk.E), padx=5)
        ttk.Button(main_frame, text="参照", command=self.browse_output_dir).grid(
            row=row, column=2, padx=5)
        row += 1

        # Mode selection
        ttk.Label(main_frame, text="モード:").grid(
            row=row, column=0, sticky=tk.W, pady=5)
        mode_frame = ttk.Frame(main_frame)
        mode_frame.grid(row=row, column=1, sticky=(tk.W, tk.E), padx=5)
        ttk.Radiobutton(mode_frame, text="測定のみ", variable=self.mode_var,
                        value="measure", command=self.on_mode_change).pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(mode_frame, text="レベルをそろえる", variable=self.mode_var,
                        value="normalize", command=self.on_mode_change).pack(side=tk.LEFT, padx=5)
        row += 1

        # Preset selection
        self.preset_label = ttk.Label(main_frame, text="基準のレベル:")
        self.preset_label.grid(row=row, column=0, sticky=tk.W, pady=5)
        preset_values = ["-16", "-18", "-19", "-20", "-23", "reffile"]
        preset_labels = ["-16 (ポッドキャスト)", "-18 (BGM)", "-19 (BGM)",
                         "-20 (BGM)", "-23 (放送)", "参照ファイルに合わせる"]
        self.preset_combo = ttk.Combobox(main_frame, textvariable=self.preset_var,
                                         values=preset_labels,
                                         state="readonly", width=47)
        self.preset_combo.grid(row=row, column=1, sticky=(tk.W, tk.E), padx=5)

        # Set initial value
        try:
            initial_idx = preset_values.index(args.preset)
            self.preset_combo.set(preset_labels[initial_idx])
        except ValueError:
            self.preset_combo.set(preset_labels[0])  # Default to -16
        row += 1

        # Output format
        self.format_label = ttk.Label(main_frame, text="出力形式:")
        self.format_label.grid(row=row, column=0, sticky=tk.W, pady=5)
        self.format_frame = ttk.Frame(main_frame)
        self.format_frame.grid(row=row, column=1, sticky=(tk.W, tk.E), padx=5)
        self.format_wav_radio = ttk.Radiobutton(self.format_frame, text="WAV", variable=self.out_ext_var,
                                                value="wav")
        self.format_wav_radio.pack(side=tk.LEFT, padx=5)
        self.format_mp3_radio = ttk.Radiobutton(self.format_frame, text="MP3", variable=self.out_ext_var,
                                                value="mp3")
        self.format_mp3_radio.pack(side=tk.LEFT, padx=5)
        self.format_m4a_radio = ttk.Radiobutton(self.format_frame, text="M4A", variable=self.out_ext_var,
                                                value="m4a")
        self.format_m4a_radio.pack(side=tk.LEFT, padx=5)
        row += 1

        # Sample rate
        self.sample_label = ttk.Label(main_frame, text="サンプリング周波数:")
        self.sample_label.grid(row=row, column=0, sticky=tk.W, pady=5)
        self.sample_combo = ttk.Combobox(main_frame, textvariable=self.sample_rate_var,
                                         values=["44100", "48000", "96000"], state="readonly", width=47)
        self.sample_combo.grid(row=row, column=1, sticky=(tk.W, tk.E), padx=5)
        row += 1

        # Options
        self.options_frame = ttk.LabelFrame(
            main_frame, text="オプション", padding="10")
        self.options_frame.grid(row=row, column=0, columnspan=3,
                                sticky=(tk.W, tk.E), pady=10)
        self.two_pass_check = ttk.Checkbutton(self.options_frame, text="2パス正規化（高精度）",
                                              variable=self.two_pass_var)
        self.two_pass_check.pack(anchor=tk.W)
        self.overwrite_check = ttk.Checkbutton(self.options_frame, text="既存ファイルを上書き",
                                               variable=self.overwrite_var)
        self.overwrite_check.pack(anchor=tk.W)
        row += 1

        # Buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=row, column=0, columnspan=3, pady=20)
        ttk.Button(button_frame, text="実行", command=self.run_processing,
                   style="Accent.TButton").pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="設定保存", command=self.save_config).pack(
            side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="終了", command=self.close_app).pack(
            side=tk.LEFT, padx=5)
        row += 1

        # Progress and log
        ttk.Label(main_frame, text="進捗・ログ:").grid(
            row=row, column=0, sticky=tk.W, pady=(10, 5))
        row += 1

        # Progress bar
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(
            main_frame, variable=self.progress_var, maximum=100)
        self.progress_bar.grid(
            row=row, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=5)
        row += 1

        # Log text area
        self.log_text = scrolledtext.ScrolledText(
            main_frame, height=15, width=80)
        self.log_text.grid(row=row, column=0, columnspan=3,
                           sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)
        main_frame.rowconfigure(row, weight=1)

        # Status bar
        self.status_var = tk.StringVar(value="準備完了")
        status_bar = ttk.Label(
            main_frame, textvariable=self.status_var, relief=tk.SUNKEN)
        status_bar.grid(row=row+1, column=0, columnspan=3,
                        sticky=(tk.W, tk.E), pady=(5, 0))

        # Set initial state based on mode
        self.on_mode_change()

    def on_mode_change(self):
        """Handle mode change to enable/disable relevant controls."""
        is_measure_mode = self.mode_var.get() == "measure"

        # State for normalization-only controls
        state = "disabled" if is_measure_mode else "normal"

        # Disable/enable preset controls
        self.preset_label.config(state=state)
        self.preset_combo.config(
            state="disabled" if is_measure_mode else "readonly")

        # Disable/enable output format controls
        self.format_label.config(state=state)
        self.format_wav_radio.config(state=state)
        self.format_mp3_radio.config(state=state)
        self.format_m4a_radio.config(state=state)

        # Disable/enable sample rate controls
        self.sample_label.config(state=state)
        self.sample_combo.config(
            state="disabled" if is_measure_mode else "readonly")

        # Disable/enable option controls (only two-pass, keep overwrite for measure mode)
        self.two_pass_check.config(state=state)
        # Keep overwrite option available for measure mode (for CSV output)

    def browse_input_dir(self):
        """Browse for input directory."""
        directory = filedialog.askdirectory(
            initialdir=self.input_dir_var.get())
        if directory:
            self.input_dir_var.set(directory)

    def browse_output_dir(self):
        """Browse for output directory."""
        directory = filedialog.askdirectory(
            initialdir=self.output_dir_var.get())
        if directory:
            self.output_dir_var.set(directory)

    def log_message(self, message):
        """Add message to log text area."""
        self.log_text.insert(
            tk.END, f"[{datetime.now().strftime('%H:%M:%S')}] {message}\n")
        self.log_text.see(tk.END)
        self.root.update_idletasks()

    def update_status(self, status):
        """Update status bar."""
        self.status_var.set(status)

    def update_progress(self, value):
        """Update progress bar."""
        self.progress_var.set(value)

    def save_config(self):
        """Save current settings to config.json."""
        try:
            config = {
                "input-dir": self.input_dir_var.get(),
                "output-dir": self.output_dir_var.get(),
                "out-ext": self.out_ext_var.get(),
                "sample-rate": int(self.sample_rate_var.get()),
                "mode": self.mode_var.get(),
                "preset": self.preset_var.get().split()[0] if self.preset_var.get() else "-16",
                "two-pass": self.two_pass_var.get(),
                "overwrite": self.overwrite_var.get(),
                "no-console": True,
                "single-instance-only": True
            }

            with open("config.json", "w", encoding="utf-8") as f:
                json.dump(config, f, indent="\t", ensure_ascii=False)

            self.log_message("設定を保存しました")
            messagebox.showinfo("保存完了", "設定がconfig.jsonに保存されました")

        except Exception as e:
            self.log_message(f"設定保存エラー: {e}")
            messagebox.showerror("保存エラー", f"設定の保存に失敗しました: {e}")

    def run_processing(self):
        """Run the audio processing in a separate thread."""
        # Update args from GUI
        self.args.input_dir = self.input_dir_var.get()
        self.args.output_dir = self.output_dir_var.get()
        self.args.mode = self.mode_var.get()
        self.args.preset = self.preset_var.get().split(
        )[0] if self.preset_var.get() else "-16"
        self.args.out_ext = self.out_ext_var.get()
        self.args.sample_rate = int(self.sample_rate_var.get())
        self.args.two_pass = self.two_pass_var.get()
        self.args.overwrite = self.overwrite_var.get()

        # Validation
        if not os.path.exists(self.args.input_dir):
            messagebox.showerror("エラー", "入力フォルダが存在しません")
            return

        # Start processing in separate thread
        self.log_message("処理を開始します...")
        self.update_status("処理中...")
        self.update_progress(0)

        thread = threading.Thread(target=self.run_processing_thread)
        thread.daemon = True
        thread.start()

    def run_processing_thread(self):
        """Run processing in separate thread."""
        try:
            # Run the main processing function
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            result = loop.run_until_complete(self.run_main_processing())

            if result == 0:
                self.log_message("処理が正常に完了しました")
                self.update_status("完了")
                self.update_progress(100)
                self.root.after(
                    0, lambda: messagebox.showinfo("完了", "処理が正常に完了しました"))
            else:
                self.log_message("処理中にエラーが発生しました")
                self.update_status("エラー")
                self.root.after(0, lambda: messagebox.showerror(
                    "エラー", "処理中にエラーが発生しました"))

        except Exception as e:
            self.log_message(f"処理エラー: {e}")
            self.update_status("エラー")
            self.root.after(
                0, lambda: messagebox.showerror("エラー", f"処理エラー: {e}"))

    async def run_main_processing(self):
        """Run the main processing logic."""
        # This will call the main() function with GUI logging
        global logger

        try:
            # Find ffmpeg
            ffmpeg_path = find_ffmpeg()
            self.root.after(0, lambda: self.log_message(
                f"Using ffmpeg: {ffmpeg_path}"))

            # Setup logging
            logger = setup_logging(self.args.output_dir)

            # Find audio files
            extensions = ['.wav', '.mp3', '.m4a']
            files = find_audio_files(self.args.input_dir, extensions)

            if not files:
                self.root.after(0, lambda: self.log_message(
                    f"No audio files found in {self.args.input_dir}"))
                return 1

            self.root.after(0, lambda: self.log_message(
                f"Found {len(files)} audio files"))

            # Determine target values
            target_i, target_tp = -16.0, -1.5  # Default values

            preset = self.args.preset
            if preset == '-16':
                target_i = -16.0
            elif preset == '-18':
                target_i = -18.0
            elif preset == '-19':
                target_i = -19.0
            elif preset == '-20':
                target_i = -20.0
            elif preset == '-23':
                target_i, target_tp = -23.0, -1.0
            elif preset == 'reffile':
                # TODO: Add reference file selection
                self.root.after(0, lambda: self.log_message(
                    "Reference file not implemented yet, using -16 LUFS"))
                target_i = -16.0

            self.root.after(0, lambda: self.log_message(
                f"Target: {target_i} LUFS / TP {target_tp} dBTP"))

            # Process files with progress updates
            success_count, failure_count = await self.process_files_with_progress(files, target_i, target_tp, ffmpeg_path)

            self.root.after(0, lambda: self.log_message(
                f"Complete: Success={success_count} / Fail={failure_count}"))

            return 0 if failure_count == 0 else 1

        except Exception as e:
            error_msg = str(e)
            self.root.after(
                0, lambda msg=error_msg: self.log_message(f"Error: {msg}"))
            return 1

    async def process_files_with_progress(self, files: List[Path], target_i: float, target_tp: float, ffmpeg_path: str) -> Tuple[int, int]:
        """Process files with GUI progress updates."""
        success_count = 0
        failure_count = 0
        measure_results = []

        # Create output directory
        os.makedirs(self.args.output_dir, exist_ok=True)

        total_files = len(files)

        for i, file_path in enumerate(files, 1):
            # Update progress
            progress = (i - 1) / total_files * 100
            self.root.after(0, lambda p=progress: self.update_progress(p))
            self.root.after(0, lambda f=file_path.name: self.log_message(
                f"[{i}/{total_files}] Processing: {f}"))

            if self.args.mode.lower() == 'measure':
                # Measurement mode
                result = measure_loudness(
                    str(file_path), ffmpeg_path, target_i, target_tp)
                measure_results.append(result)

                if result['status'] == 'OK':
                    self.root.after(0, lambda r=result: self.log_message(
                        f"  LUFS: {r['integrated_lufs']:.1f} | TP: {r['true_peak_dbtp']:.1f} | LRA: {r['loudness_range']:.1f}"))
                    success_count += 1
                else:
                    self.root.after(0, lambda r=result: self.log_message(
                        f"  Measurement failed: {r['status']}"))
                    failure_count += 1
            else:
                # Normalization mode
                base_name = file_path.stem
                output_name = f"{base_name}.{self.args.out_ext}"
                output_path = Path(self.args.output_dir) / output_name

                # Handle existing files
                if output_path.exists() and not self.args.overwrite:
                    output_path = Path(self.args.output_dir) / \
                        f"{base_name}_norm.{self.args.out_ext}"

                success = normalize_audio(
                    str(file_path), str(output_path), target_i, target_tp,
                    self.args.sample_rate, self.args.out_ext, self.args.two_pass,
                    ffmpeg_path
                )

                if success:
                    self.root.after(0, lambda n=output_path.name: self.log_message(
                        f"  ✓ Normalized to: {n}"))
                    success_count += 1
                else:
                    self.root.after(0, lambda: self.log_message(
                        "  ✗ Normalization failed"))
                    failure_count += 1

            # Allow interruption
            await asyncio.sleep(0.1)

        # Final progress
        self.root.after(0, lambda: self.update_progress(100))

        # Save measurement results to CSV if in measure mode
        if self.args.mode.lower() == 'measure' and measure_results:
            csv_path = Path(self.args.output_dir) / "loudness_measurement.csv"
            with open(csv_path, 'w', newline='', encoding='utf-8') as csvfile:
                fieldnames = ['file', 'integrated_lufs',
                              'loudness_range', 'true_peak_dbtp', 'status']
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

                writer.writeheader()
                for result in measure_results:
                    writer.writerow({
                        'file': Path(result['file']).name,
                        'integrated_lufs': result['integrated_lufs'],
                        'loudness_range': result['loudness_range'],
                        'true_peak_dbtp': result['true_peak_dbtp'],
                        'status': result['status']
                    })

            self.root.after(0, lambda: self.log_message(
                f"Measurement results saved to: {csv_path}"))

        return success_count, failure_count

    def close_app(self):
        """Close the application."""
        if messagebox.askquestion("終了", "アプリケーションを終了しますか？") == "yes":
            self.root.quit()

    def run(self):
        """Run the GUI."""
        self.root.mainloop()


def setup_logging(output_dir: str) -> logging.Logger:
    """Setup logging configuration."""
    log_file = os.path.join(output_dir, "LoudSync.log")

    # Create logger
    logger = logging.getLogger('LoudSync')
    logger.setLevel(logging.INFO)

    # Create handlers
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    console_handler = logging.StreamHandler(sys.stdout)

    # Create formatter
    formatter = logging.Formatter('[%(asctime)s] %(levelname)s: %(message)s',
                                  datefmt='%Y-%m-%d %H:%M:%S')

    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    # Add handlers to logger
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger


def find_ffmpeg() -> str:
    """Find ffmpeg executable path."""
    # Try system PATH first
    ffmpeg = shutil.which('ffmpeg')
    if ffmpeg:
        return ffmpeg

    # Try bundled ffmpeg
    bundled_ffmpeg = Path(__file__).parent / "bin" / "ffmpeg.exe"
    if bundled_ffmpeg.exists():
        return str(bundled_ffmpeg)

    # Check if running from PyInstaller bundle
    if hasattr(sys, '_MEIPASS'):
        bundle_ffmpeg = Path(sys._MEIPASS) / "bin" / "ffmpeg.exe"
        if bundle_ffmpeg.exists():
            return str(bundle_ffmpeg)

    raise LoudSyncError(
        "ffmpeg not found. Please install ffmpeg or place it in bin/ directory.")


def find_audio_files(input_dir: str, extensions: List[str]) -> List[Path]:
    """Find audio files in directory."""
    input_path = Path(input_dir)
    if not input_path.exists():
        raise LoudSyncError(f"Input directory not found: {input_dir}")

    files = []
    for ext in extensions:
        pattern = f"**/*{ext}" if ext.startswith('.') else f"**/*.{ext}"
        files.extend(input_path.glob(pattern))

    return sorted(files)


def measure_loudness(file_path: str, ffmpeg_path: str, target_i: float = -16.0, target_tp: float = -1.5) -> Dict:
    """Measure loudness of audio file using ffmpeg."""
    try:
        cmd = [
            ffmpeg_path, '-hide_banner', '-nostats',
            '-i', file_path,
            '-af', f'loudnorm=I={target_i}:TP={target_tp}:LRA=11:print_format=json',
            '-f', 'null', '-'
        ]

        result = subprocess.run(cmd, capture_output=True,
                                text=True, encoding='utf-8', errors='replace',
                                creationflags=subprocess.CREATE_NO_WINDOW)

        # Extract JSON from stderr
        stderr_lines = result.stderr.split('\n')
        json_started = False
        json_lines = []

        for line in stderr_lines:
            if '{' in line and not json_started:
                json_started = True
            if json_started:
                json_lines.append(line)
                if '}' in line:
                    break

        json_text = '\n'.join(json_lines)

        # Parse JSON
        try:
            json_data = json.loads(json_text)
            return {
                'file': file_path,
                'integrated_lufs': float(json_data.get('input_i', 0)),
                'loudness_range': float(json_data.get('input_lra', 0)),
                'true_peak_dbtp': float(json_data.get('input_tp', 0)),
                'status': 'OK',
                'raw_json': json_data
            }
        except (json.JSONDecodeError, ValueError, KeyError) as e:
            return {
                'file': file_path,
                'integrated_lufs': None,
                'loudness_range': None,
                'true_peak_dbtp': None,
                'status': f'JSON_ERROR: {str(e)}',
                'raw_json': None
            }

    except subprocess.SubprocessError as e:
        return {
            'file': file_path,
            'integrated_lufs': None,
            'loudness_range': None,
            'true_peak_dbtp': None,
            'status': f'FFMPEG_ERROR: {str(e)}',
            'raw_json': None
        }


def get_reference_lufs(ref_path: str, ffmpeg_path: str) -> float:
    """Get LUFS value from reference file."""
    if not os.path.exists(ref_path):
        raise LoudSyncError(f"Reference file not found: {ref_path}")

    result = measure_loudness(ref_path, ffmpeg_path)
    if result['status'] == 'OK' and result['integrated_lufs'] is not None:
        return round(result['integrated_lufs'], 1)
    else:
        raise LoudSyncError(
            f"Failed to analyze reference file: {result['status']}")


def normalize_audio(input_path: str, output_path: str, target_i: float, target_tp: float,
                    sample_rate: int = 48000, output_format: str = 'wav',
                    two_pass: bool = True, ffmpeg_path: str = None) -> bool:
    """Normalize audio file using ffmpeg loudnorm."""
    try:
        if two_pass:
            # First pass: measure
            measure_result = measure_loudness(
                input_path, ffmpeg_path, target_i, target_tp)
            if measure_result['status'] != 'OK' or not measure_result['raw_json']:
                logger.warning(
                    f"Measurement failed for {input_path}, falling back to 1-pass")
                return normalize_audio(input_path, output_path, target_i, target_tp,
                                       sample_rate, output_format, two_pass=False, ffmpeg_path=ffmpeg_path)

            # Second pass: apply normalization
            json_data = measure_result['raw_json']
            cmd = [
                ffmpeg_path, '-hide_banner', '-y',
                '-i', input_path,
                '-af', (f'loudnorm=I={target_i}:TP={target_tp}:LRA=11:'
                        f'measured_I={json_data["input_i"]}:'
                        f'measured_TP={json_data["input_tp"]}:'
                        f'measured_LRA={json_data["input_lra"]}:'
                        f'measured_thresh={json_data["input_thresh"]}:'
                        f'offset={json_data["target_offset"]}:'
                        f'linear=true:print_format=summary'),
                '-ar', str(sample_rate)
            ]
        else:
            # One pass normalization
            cmd = [
                ffmpeg_path, '-hide_banner', '-y',
                '-i', input_path,
                '-af', f'loudnorm=I={target_i}:TP={target_tp}:LRA=11',
                '-ar', str(sample_rate)
            ]

        # Add codec and output path
        if output_format.lower() == 'wav':
            cmd.extend(['-c:a', 'pcm_s16le'])
        elif output_format.lower() == 'mp3':
            cmd.extend(['-c:a', 'libmp3lame', '-q:a', '2'])
        elif output_format.lower() == 'm4a':
            cmd.extend(['-c:a', 'aac', '-b:a', '128k'])

        cmd.append(output_path)

        result = subprocess.run(cmd, capture_output=True,
                                text=True, encoding='utf-8', errors='replace',
                                creationflags=subprocess.CREATE_NO_WINDOW)

        if result.returncode == 0:
            return True
        else:
            logger.error(f"FFmpeg error for {input_path}: {result.stderr}")
            return False

    except Exception as e:
        logger.error(f"Normalization error for {input_path}: {str(e)}")
        return False


def select_preset_interactive() -> Tuple[float, float]:
    """Interactive preset selection."""
    print("\n=== Select Target ===")
    print("1) Reference file")
    print("2) Podcast: -16 LUFS")
    print("3) BGM: -18 LUFS")
    print("4) BGM: -19 LUFS")
    print("5) BGM: -20 LUFS")
    print("6) Broadcast: -23 LUFS")

    while True:
        try:
            selection = input("Enter number (1-6): ").strip()

            if selection == "1":
                ref_path = input("Reference file path: ").strip()
                try:
                    target_i = get_reference_lufs(ref_path, ffmpeg_path)
                    print(f"Reference file LUFS: {target_i}")
                    return target_i, -1.5
                except LoudSyncError as e:
                    print(f"Error: {e}")
                    print("Using default -16 LUFS")
                    return -16.0, -1.5
            elif selection == "2":
                return -16.0, -1.5
            elif selection == "3":
                return -18.0, -1.5
            elif selection == "4":
                return -19.0, -1.5
            elif selection == "5":
                return -20.0, -1.5
            elif selection == "6":
                return -23.0, -1.0
            else:
                print("Invalid selection. Please enter 1-6.")
        except KeyboardInterrupt:
            print("\nOperation cancelled.")
            sys.exit(0)


async def process_files(files: List[Path], args, target_i: float, target_tp: float) -> Tuple[int, int]:
    """Process audio files for measurement or normalization."""
    success_count = 0
    failure_count = 0
    measure_results = []

    # Create output directory
    os.makedirs(args.output_dir, exist_ok=True)

    for i, file_path in enumerate(files, 1):
        print(f"\n[{i}/{len(files)}] Processing: {file_path.name}")
        logger.info(f"Processing file {i}/{len(files)}: {file_path}")

        if args.mode.lower() == 'measure':
            # Measurement mode
            result = measure_loudness(
                str(file_path), ffmpeg_path, target_i, target_tp)
            measure_results.append(result)

            if result['status'] == 'OK':
                print(f"  LUFS: {result['integrated_lufs']:.1f} | "
                      f"TP: {result['true_peak_dbtp']:.1f} | "
                      f"LRA: {result['loudness_range']:.1f}")
                success_count += 1
            else:
                print(f"  Measurement failed: {result['status']}")
                failure_count += 1
        else:
            # Normalization mode
            base_name = file_path.stem
            output_name = f"{base_name}.{args.out_ext}"
            output_path = Path(args.output_dir) / output_name

            # Handle existing files
            if output_path.exists() and not args.overwrite:
                output_path = Path(args.output_dir) / \
                    f"{base_name}_norm.{args.out_ext}"

            success = normalize_audio(
                str(file_path), str(output_path), target_i, target_tp,
                args.sample_rate, args.out_ext, args.two_pass, ffmpeg_path
            )

            if success:
                print(f"  ✓ Normalized to: {output_path.name}")
                success_count += 1
            else:
                print(f"  ✗ Normalization failed")
                failure_count += 1

        # Allow interruption
        await asyncio.sleep(0.1)

    # Save measurement results to CSV if in measure mode
    if args.mode.lower() == 'measure' and measure_results:
        csv_path = Path(args.output_dir) / "loudness_measurement.csv"
        with open(csv_path, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['file', 'integrated_lufs',
                          'loudness_range', 'true_peak_dbtp', 'status']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

            writer.writeheader()
            for result in measure_results:
                writer.writerow({
                    'file': Path(result['file']).name,
                    'integrated_lufs': result['integrated_lufs'],
                    'loudness_range': result['loudness_range'],
                    'true_peak_dbtp': result['true_peak_dbtp'],
                    'status': result['status']
                })

        print(f"\nMeasurement results saved to: {csv_path}")
        logger.info(f"CSV results saved to: {csv_path}")

    return success_count, failure_count


async def main(args):
    """Main application logic."""
    global ffmpeg_path, logger

    try:
        # Find ffmpeg
        ffmpeg_path = find_ffmpeg()
        print(f"Using ffmpeg: {ffmpeg_path}")

        # Setup logging
        logger = setup_logging(args.output_dir)
        logger.info("LoudSync started")
        logger.info(f"FFmpeg path: {ffmpeg_path}")

        # Find audio files
        extensions = ['.wav', '.mp3', '.m4a']
        files = find_audio_files(args.input_dir, extensions)

        if not files:
            print(f"No audio files found in {args.input_dir}")
            return 1

        print(f"Found {len(files)} audio files")
        logger.info(f"Found {len(files)} audio files")

        # Determine target values
        target_i, target_tp = -16.0, -1.5  # Default values

        if args.preset.lower() == 'interactive':
            if sys.stdin.isatty() and not args.no_console:  # Only if we have a console AND not in no-console mode
                target_i, target_tp = select_preset_interactive()
            else:
                print("No console available, using default preset: -16 LUFS")
                target_i, target_tp = -16.0, -1.5
        elif args.preset.lower() == 'reffile':
            if args.ref_path and os.path.exists(args.ref_path):
                target_i = get_reference_lufs(args.ref_path, ffmpeg_path)
                print(f"Reference file LUFS: {target_i}")
            else:
                raise LoudSyncError(
                    "Reference file not specified or not found")
        elif args.preset == '-16':
            target_i = -16.0
        elif args.preset == '-18':
            target_i = -18.0
        elif args.preset == '-19':
            target_i = -19.0
        elif args.preset == '-20':
            target_i = -20.0
        elif args.preset == '-23':
            target_i, target_tp = -23.0, -1.0

        print(f"Target: {target_i} LUFS / TP {target_tp} dBTP")
        logger.info(f"Target: {target_i} LUFS / TP {target_tp} dBTP")

        # Process files
        success_count, failure_count = await process_files(files, args, target_i, target_tp)

        # Summary
        print(f"\nComplete: Success={success_count} / Fail={failure_count}")
        logger.info(
            f"Processing complete: Success={success_count} / Fail={failure_count}")

        # Console mode: Exit after processing
        if not args.no_console and sys.stdin.isatty():
            print("Press Enter to exit...")
            input()

        return 0 if failure_count == 0 else 1

    except LoudSyncError as e:
        print(f"Error: {e}")
        if logger:
            logger.error(str(e))
        return 1
    except KeyboardInterrupt:
        print("\nOperation cancelled by user")
        if logger:
            logger.info("Operation cancelled by user")
        return 1
    except Exception as e:
        print(f"Unexpected error: {e}")
        if logger:
            logger.error(f"Unexpected error: {e}")
        return 1


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='LoudSync - Audio Loudness Normalization Tool',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument('--input-dir', default='.',
                        help='Input directory containing audio files (default: current directory)')
    parser.add_argument('--output-dir', default='normalized',
                        help='Output directory for processed files (default: normalized)')
    parser.add_argument('--out-ext', choices=['wav', 'mp3', 'm4a'], default='wav',
                        help='Output file format (default: wav)')
    parser.add_argument('--sample-rate', type=int, choices=[44100, 48000, 96000], default=48000,
                        help='Output sample rate (default: 48000)')
    parser.add_argument('--mode', choices=['measure', 'normalize'], default='normalize',
                        help='Processing mode (default: normalize)')
    parser.add_argument('--preset', default='interactive',
                        choices=['interactive', 'reffile',
                                 '-16', '-18', '-19', '-20', '-23'],
                        help='Loudness preset (default: interactive)')
    parser.add_argument('--ref-path',
                        help='Reference file path (required when preset=reffile)')
    parser.add_argument('--two-pass', action='store_true', default=True,
                        help='Use 2-pass normalization (default: enabled)')
    parser.add_argument('--one-pass', action='store_true',
                        help='Force 1-pass normalization')
    parser.add_argument('--overwrite', action='store_true',
                        help='Overwrite existing output files')
    parser.add_argument('--config', default='config.json',
                        help='Configuration file path (default: config.json)')
    parser.add_argument('--no-console', action='store_true',
                        help='Disable console interaction (background mode)')
    parser.add_argument('--single-instance-only', action='store_true',
                        help='Prevent multiple instances')

    return parser.parse_args()


if __name__ == "__main__":
    # Parse arguments
    args = parse_arguments()

    # Handle one-pass override
    if args.one_pass:
        args.two_pass = False

    # Load config file if exists
    if os.path.isfile(args.config):
        try:
            with open(args.config, 'r', encoding='utf-8') as f:
                config = json.load(f)

            # Apply config values (simple approach) but respect CLI overrides
            for key, value in config.items():
                attr_name = key.replace('-', '_')
                if hasattr(args, attr_name):
                    # Don't override if explicitly set via command line
                    if attr_name == 'no_console':
                        # Only set from config if not explicitly overridden
                        if not getattr(args, attr_name, False):
                            setattr(args, attr_name, value)
                    else:
                        setattr(args, attr_name, value)
                    # Debug
                    print(f"Config: {attr_name} = {getattr(args, attr_name)}")
        except Exception as e:
            print(f"Warning: Could not load config file: {e}")

    # Convert to absolute paths
    args.input_dir = os.path.abspath(args.input_dir)
    args.output_dir = os.path.abspath(args.output_dir)

    # Check for output directory inside input directory
    if is_subpath(args.output_dir, args.input_dir):
        print('Warning: Output directory is inside input directory.')
        print('Changing output directory to parent directory.')
        args.output_dir = os.path.join(
            os.path.dirname(args.input_dir), 'normalized')
        print(f"New output directory: {args.output_dir}")

    # Create output directory
    os.makedirs(args.output_dir, exist_ok=True)

    # Check for existing instance
    if args.single_instance_only:
        instance_key = f"LoudSync_{args.input_dir}"
        if check_existing_instance(12321, instance_key):
            print("Another instance is already running.")
            sys.exit(0)

    # Exit handler for console mode
    def exit_handler(reason):
        print(f"Exiting: {reason}")
        sys.exit(0)

    # Signal handlers
    signal.signal(signal.SIGINT, lambda sig,
                  frame: exit_handler("[Exit] Signal Interrupt"))
    if hasattr(signal, 'SIGTERM'):
        signal.signal(signal.SIGTERM, lambda sig,
                      frame: exit_handler("[Exit] Signal Terminate"))

    # Detect console availability
    if not sys.stdin or not sys.stdin.isatty():
        if not args.no_console:
            print("Console not attached. Disabling console input.")
        args.no_console = True

    # Run main application based on no-console mode
    if args.no_console:
        # GUI mode: Show GUI window
        print("Starting GUI mode...")
        try:
            app = LoudSyncGUI(args)
            app.run()
        except Exception as e:
            print(f"GUI error: {e}")
            sys.exit(1)
    else:
        # Console mode: Run directly
        async def run_console_app():
            try:
                if ainput is None:
                    args.no_console = True

                exit_code = await main(args)
                sys.exit(exit_code)

            except KeyboardInterrupt:
                exit_handler("[Exit] Keyboard Interrupt")

        try:
            asyncio.run(run_console_app())
        except KeyboardInterrupt:
            exit_handler("[Exit] Keyboard Interrupt")
