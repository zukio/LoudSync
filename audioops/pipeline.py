#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LoudSync Pipeline - 正規化→フェード→書き出しの統合処理
"""

import os
import sys
import json
import subprocess
import shutil
from pathlib import Path
from typing import List, Dict, Optional, Tuple

# LoudSync関数をインポート
from .loudsync_legacy import (
    find_ffmpeg, normalize_audio, measure_loudness,
    find_audio_files, LoudSyncError
)
from .core import fade_file, crossfade_sequence


class PipelineConfig:
    """パイプライン設定クラス"""

    def __init__(self):
        self.normalize = {
            'enabled': True,
            'preset': '-16',  # -16, -18, -19, -20, -23, reffile
            'lufs': -16.0,
            'tp': -1.5,
            'two_pass': True
        }
        self.fade = {
            'enabled': False,
            'in_ms': 300,
            'out_ms': 1500,
            'from_end_sec': 2.0
        }
        self.crossfade = {
            'enabled': False,
            'overlap_sec': 2.0,
            'curve': 'tri'
        }
        self.output = {
            'codec': 'aac',
            'sample_rate': 48000,
            'format': 'wav'
        }
        self.paths = {
            'ffmpeg': None,  # 自動検出
            'cache_dir': './_cache'
        }


def setup_cache_dirs(cache_dir: str) -> Dict[str, Path]:
    """キャッシュディレクトリを設定"""
    cache_path = Path(cache_dir)
    dirs = {
        'normalized': cache_path / 'normalized',
        'faded': cache_path / 'faded'
    }

    for dir_path in dirs.values():
        dir_path.mkdir(parents=True, exist_ok=True)

    return dirs


def cleanup_cache(cache_dirs: Dict[str, Path], keep_files: bool = False):
    """キャッシュディレクトリをクリーンアップ"""
    if keep_files:
        return

    for dir_path in cache_dirs.values():
        if dir_path.exists():
            shutil.rmtree(dir_path)
            print(f"Cleaned cache: {dir_path}")


def run_normalize_step(files: List[Path], config: PipelineConfig,
                       cache_dirs: Dict[str, Path]) -> List[Path]:
    """正規化ステップを実行"""
    if not config.normalize['enabled']:
        return files

    print(f"=== Normalization Step ===")
    print(
        f"Target: {config.normalize['lufs']} LUFS / TP {config.normalize['tp']} dBTP")

    normalized_files = []
    ffmpeg_path = config.paths['ffmpeg'] or find_ffmpeg()

    for i, file_path in enumerate(files, 1):
        print(f"[{i}/{len(files)}] Normalizing: {file_path.name}")

        # 出力ファイル名
        output_name = f"{file_path.stem}__norm{file_path.suffix}"
        output_path = cache_dirs['normalized'] / output_name

        # 正規化実行
        success = normalize_audio(
            str(file_path), str(output_path),
            config.normalize['lufs'], config.normalize['tp'],
            config.output['sample_rate'],
            file_path.suffix[1:],  # 拡張子から.を除去
            config.normalize['two_pass'],
            ffmpeg_path
        )

        if success:
            normalized_files.append(output_path)
            print(f"  ✓ Normalized to: {output_path.name}")
        else:
            print(f"  ✗ Normalization failed, skipping")

    return normalized_files


def run_fade_step(files: List[Path], config: PipelineConfig,
                  cache_dirs: Dict[str, Path]) -> List[Path]:
    """フェードステップを実行"""
    if not config.fade['enabled'] or not files:
        return files

    print(f"=== Fade Step ===")
    print(f"FadeIn: {config.fade['in_ms']}ms, FadeOut: {config.fade['out_ms']}ms "
          f"(from end: {config.fade['from_end_sec']}s)")

    faded_files = []

    for i, file_path in enumerate(files, 1):
        print(f"[{i}/{len(files)}] Adding fade: {file_path.name}")

        # 出力ファイル名
        output_name = f"{file_path.stem}__fade{file_path.suffix}"
        output_path = cache_dirs['faded'] / output_name

        try:
            fade_file(
                file_path, output_path,
                fade_in_ms=config.fade['in_ms'],
                fade_out_ms=config.fade['out_ms'],
                fade_out_from_end_sec=config.fade['from_end_sec'],
                codec=config.output['codec']
            )
            faded_files.append(output_path)
            print(f"  ✓ Faded to: {output_path.name}")
        except Exception as e:
            print(f"  ✗ Fade failed: {e}")

    return faded_files


def run_crossfade_step(files: List[Path], config: PipelineConfig,
                       output_path: Path) -> bool:
    """クロスフェードステップを実行"""
    if not config.crossfade['enabled'] or len(files) < 2:
        if len(files) == 1:
            # 単一ファイルの場合はコピー
            shutil.copy2(files[0], output_path)
            print(f"Single file copied to: {output_path}")
            return True
        return False

    print(f"=== Crossfade Step ===")
    print(
        f"Crossfading {len(files)} files with {config.crossfade['overlap_sec']}s overlap")

    try:
        crossfade_sequence(
            files, output_path,
            overlap_sec=config.crossfade['overlap_sec'],
            curve1=config.crossfade['curve'],
            curve2=config.crossfade['curve'],
            codec=config.output['codec']
        )
        print(f"✓ Crossfaded to: {output_path}")
        return True
    except Exception as e:
        print(f"✗ Crossfade failed: {e}")
        return False


def run_pipeline(input_files: List[Path], output_path: Path,
                 config: PipelineConfig) -> bool:
    """パイプライン全体を実行"""
    try:
        print(f"=== LoudSync Pipeline Started ===")
        print(f"Input files: {len(input_files)}")
        print(f"Output: {output_path}")

        # キャッシュディレクトリ設定
        cache_dirs = setup_cache_dirs(config.paths['cache_dir'])

        # ステップ1: 正規化
        normalized_files = run_normalize_step(input_files, config, cache_dirs)
        if not normalized_files:
            print("No files to process after normalization")
            return False

        # ステップ2: フェード
        faded_files = run_fade_step(normalized_files, config, cache_dirs)
        if not faded_files:
            faded_files = normalized_files  # フェードなしの場合は正規化済みファイルを使用

        # ステップ3: クロスフェード（または単一ファイルコピー）
        final_success = run_crossfade_step(faded_files, config, output_path)

        # クリーンアップ
        cleanup_cache(cache_dirs, keep_files=False)

        if final_success:
            print(f"=== Pipeline Completed Successfully ===")
            print(f"Output: {output_path}")
            return True
        else:
            print(f"=== Pipeline Failed ===")
            return False

    except Exception as e:
        print(f"Pipeline error: {e}")
        return False


def create_preset_config(preset_name: str) -> PipelineConfig:
    """プリセット設定を作成"""
    config = PipelineConfig()

    if preset_name == "podcast":
        config.normalize.update({
            'preset': '-16',
            'lufs': -16.0,
            'tp': -1.5
        })
        config.fade.update({
            'enabled': True,
            'in_ms': 500,
            'out_ms': 2000,
            'from_end_sec': 3.0
        })
        config.output.update({
            'codec': 'libmp3lame',
            'format': 'mp3'
        })

    elif preset_name == "bgm":
        config.normalize.update({
            'preset': '-18',
            'lufs': -18.0,
            'tp': -1.5
        })
        config.fade.update({
            'enabled': True,
            'in_ms': 1000,
            'out_ms': 3000,
            'from_end_sec': 4.0
        })
        config.crossfade.update({
            'enabled': True,
            'overlap_sec': 3.0
        })
        config.output.update({
            'codec': 'aac',
            'format': 'wav'
        })

    elif preset_name == "broadcast":
        config.normalize.update({
            'preset': '-23',
            'lufs': -23.0,
            'tp': -1.0
        })
        config.fade.update({
            'enabled': True,
            'in_ms': 300,
            'out_ms': 1000,
            'from_end_sec': 2.0
        })
        config.output.update({
            'codec': 'pcm_s16le',
            'format': 'wav'
        })

    return config


def save_config(config: PipelineConfig, config_path: str):
    """設定をJSONファイルに保存"""
    config_dict = {
        'normalize': config.normalize,
        'fade': config.fade,
        'crossfade': config.crossfade,
        'output': config.output,
        'paths': config.paths
    }

    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(config_dict, f, indent=2, ensure_ascii=False)

    print(f"Configuration saved to: {config_path}")


def load_config(config_path: str) -> PipelineConfig:
    """JSONファイルから設定を読み込み"""
    config = PipelineConfig()

    if not os.path.exists(config_path):
        return config

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config_dict = json.load(f)

        config.normalize.update(config_dict.get('normalize', {}))
        config.fade.update(config_dict.get('fade', {}))
        config.crossfade.update(config_dict.get('crossfade', {}))
        config.output.update(config_dict.get('output', {}))
        config.paths.update(config_dict.get('paths', {}))

        print(f"Configuration loaded from: {config_path}")

    except Exception as e:
        print(f"Warning: Could not load config file: {e}")

    return config


if __name__ == "__main__":
    # テスト実行例
    import argparse

    parser = argparse.ArgumentParser(description='LoudSync Pipeline Test')
    parser.add_argument('input_dir', help='Input directory')
    parser.add_argument('output_file', help='Output file')
    parser.add_argument('--preset', default='podcast',
                        choices=['podcast', 'bgm', 'broadcast'],
                        help='Preset configuration')

    args = parser.parse_args()

    # 音声ファイルを検索
    extensions = ['.wav', '.mp3', '.m4a']
    input_files = find_audio_files(args.input_dir, extensions)

    if not input_files:
        print(f"No audio files found in {args.input_dir}")
        sys.exit(1)

    # 設定を作成
    config = create_preset_config(args.preset)

    # パイプライン実行
    success = run_pipeline(input_files, Path(args.output_file), config)

    sys.exit(0 if success else 1)
