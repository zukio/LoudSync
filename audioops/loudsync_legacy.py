#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LoudSync Legacy Functions
旧LoudSyncから抽出した必要な関数群
"""

import os
import sys
import json
import subprocess
import shutil
import logging
from pathlib import Path
from typing import List, Dict, Optional


class LoudSyncError(Exception):
    """Custom exception for LoudSync errors."""
    pass


def find_ffmpeg() -> str:
    """Find ffmpeg executable path."""
    # Try system PATH first
    ffmpeg = shutil.which('ffmpeg')
    if ffmpeg:
        return ffmpeg

    # Try bundled ffmpeg
    bundled_ffmpeg = Path(__file__).parent.parent / "bin" / "ffmpeg.exe"
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
                                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)

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


def normalize_audio(input_path: str, output_path: str, target_i: float, target_tp: float,
                    sample_rate: int = 48000, output_format: str = 'wav',
                    two_pass: bool = True, ffmpeg_path: str = None) -> bool:
    """Normalize audio file using ffmpeg loudnorm."""
    try:
        if ffmpeg_path is None:
            ffmpeg_path = find_ffmpeg()

        if two_pass:
            # First pass: measure
            measure_result = measure_loudness(
                input_path, ffmpeg_path, target_i, target_tp)
            if measure_result['status'] != 'OK' or not measure_result['raw_json']:
                print(
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
                                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)

        if result.returncode == 0:
            return True
        else:
            print(f"FFmpeg error for {input_path}: {result.stderr}")
            return False

    except Exception as e:
        print(f"Normalization error for {input_path}: {str(e)}")
        return False
