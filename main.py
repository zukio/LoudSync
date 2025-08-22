#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LoudSync Suite - Audio Loudness Normalization Tool with Fade/Crossfade Integration
フェード/クロスフェード統合版 LoudSync
"""

import os
import sys
import argparse
from pathlib import Path


def main():
    """メインエントリポイント"""
    parser = argparse.ArgumentParser(
        description='LoudSync Suite - フェード/クロスフェード統合版',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    # モード選択
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument('--gui', action='store_true',
                            help='GUIモードで起動（デフォルト）')
    mode_group.add_argument('--cli', action='store_true',
                            help='CLIモードで起動（旧LoudSync互換）')

    # サブコマンド
    subparsers = parser.add_subparsers(dest='command', help='利用可能なコマンド')

    # Pipeline コマンド
    pipeline_parser = subparsers.add_parser('pipeline', help='パイプライン実行')
    pipeline_parser.add_argument('input_dir', help='入力ディレクトリ')
    pipeline_parser.add_argument('output_file', help='出力ファイル')
    pipeline_parser.add_argument('--preset', default='podcast',
                                 choices=['podcast', 'bgm', 'broadcast'],
                                 help='プリセット設定')

    # Fade コマンド
    fade_parser = subparsers.add_parser('fade', help='フェード処理')
    fade_parser.add_argument('input_files', nargs='+', help='入力ファイル')
    fade_parser.add_argument('--output-dir', required=True, help='出力ディレクトリ')
    fade_parser.add_argument('--fade-in', type=int,
                             default=300, help='フェードイン(ms)')
    fade_parser.add_argument('--fade-out', type=int,
                             default=1500, help='フェードアウト(ms)')
    fade_parser.add_argument('--from-end', type=float,
                             default=2.0, help='アウト開始(秒)')
    fade_parser.add_argument('--codec', default='aac', help='コーデック')

    # Crossfade コマンド
    crossfade_parser = subparsers.add_parser('crossfade', help='クロスフェード連結')
    crossfade_parser.add_argument(
        'input_files', nargs='+', help='入力ファイル（順序=再生順）')
    crossfade_parser.add_argument('--output', required=True, help='出力ファイル')
    crossfade_parser.add_argument(
        '--overlap', type=float, default=2.0, help='オーバーラップ(秒)')
    crossfade_parser.add_argument('--curve', default='tri', help='カーブタイプ')
    crossfade_parser.add_argument(
        '--codec', default='libmp3lame', help='コーデック')

    args = parser.parse_args()

    # モード判定とディスパッチ
    if args.command:
        # サブコマンドが指定された場合
        return run_cli_command(args)
    elif args.gui or (not args.cli and len(sys.argv) == 1):
        # GUIモード（デフォルト）
        return run_gui_mode()
    else:
        # CLIモード
        print("CLIモードは現在開発中です。GUIモードを使用してください。")
        print("python main.py --gui")
        return 1


def run_gui_mode():
    """GUIモードで実行"""
    try:
        from gui.app_qt import main as gui_main
        return gui_main()
    except ImportError as e:
        print(f"GUI実行エラー: {e}")
        print("PySide6がインストールされていない可能性があります。")
        print("pip install PySide6 でインストールしてください。")
        return 1


def run_cli_command(args):
    """CLIコマンドを実行"""
    if args.command == 'pipeline':
        return run_pipeline_command(args)
    elif args.command == 'fade':
        return run_fade_command(args)
    elif args.command == 'crossfade':
        return run_crossfade_command(args)
    else:
        print(f"未知のコマンド: {args.command}")
        return 1


def run_pipeline_command(args):
    """パイプラインコマンドを実行"""
    try:
        from audioops.pipeline import create_preset_config, run_pipeline

        # 音声ファイルを検索
        input_dir = Path(args.input_dir)
        extensions = ['.wav', '.mp3', '.m4a', '.flac']
        input_files = []
        for ext in extensions:
            input_files.extend(input_dir.glob(f"**/*{ext}"))

        if not input_files:
            print(f"No audio files found in {args.input_dir}")
            return 1

        # 設定を作成
        config = create_preset_config(args.preset)

        # パイプライン実行
        success = run_pipeline(input_files, Path(args.output_file), config)

        return 0 if success else 1

    except Exception as e:
        print(f"Pipeline error: {e}")
        return 1


def run_fade_command(args):
    """フェードコマンドを実行"""
    try:
        from audioops.core import fade_file

        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        for i, input_file in enumerate(args.input_files, 1):
            input_path = Path(input_file)
            output_path = output_dir / \
                f"{input_path.stem}_fade{input_path.suffix}"

            print(f"[{i}/{len(args.input_files)}] Processing: {input_path.name}")

            fade_file(
                input_path, output_path,
                fade_in_ms=args.fade_in,
                fade_out_ms=args.fade_out,
                fade_out_from_end_sec=args.from_end,
                codec=args.codec
            )

            print(f"  ✓ Output: {output_path}")

        return 0

    except Exception as e:
        print(f"Fade error: {e}")
        return 1


def run_crossfade_command(args):
    """クロスフェードコマンドを実行"""
    try:
        from audioops.core import crossfade_sequence

        if len(args.input_files) < 2:
            print("Crossfade requires at least 2 input files")
            return 1

        input_paths = [Path(f) for f in args.input_files]
        output_path = Path(args.output)

        print(
            f"Crossfading {len(input_paths)} files with {args.overlap}s overlap")

        crossfade_sequence(
            input_paths, output_path,
            overlap_sec=args.overlap,
            curve1=args.curve,
            curve2=args.curve,
            codec=args.codec
        )

        print(f"✓ Output: {output_path}")
        return 0

    except Exception as e:
        print(f"Crossfade error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
