# LoudSync Suite (フェード/クロスフェード統合版)

**Audio Loudness Normalization Tool with Fade/Crossfade Integration**

PowerShellスクリプトから変換されたPython版のLoudSyncに、フェードイン/アウトおよびクロスフェード連結機能を統合したツールです。複数の音声ファイルのラウドネス（LUFS）/ピークを計測し、指定プリセットまたは参照ファイルに合わせて正規化→フェード→クロスフェードの一括パイプラインを実行できます。

## 新機能（v2.0）

- **フェードイン/アウト**: 音声ファイルにフェードイン・フェードアウトを追加
- **クロスフェード連結**: 複数ファイルを順にクロスフェードで連結
- **一括パイプライン**: 正規化→フェード→書き出しを一括実行
- **タブ分割GUI**: PySide6ベースの直感的なタブ式インターフェース
- **ドラッグ&ドロップ**: ファイルを簡単に追加・並べ替え
- **プリセット設定**: ポッドキャスト/BGM/放送用の事前設定

## 機能

### 正規化 (Normalize)
- **ラウドネス測定**: LUFS/TP/LRA値の測定とCSV出力
- **音声正規化**: EBU R128準拠の1パス/2パス正規化
- **プリセット選択**: ポッドキャスト、BGM、放送用など
- **参照ファイル**: 指定ファイルと同じラウドネスに調整

### フェード (Fade)
- **フェードイン**: 指定ミリ秒でのフェードイン効果
- **フェードアウト**: 指定ミリ秒でのフェードアウト効果
- **開始位置制御**: 末尾からの秒数指定または絶対位置指定
- **一括処理**: 複数ファイルの同時フェード処理

### クロスフェード (Crossfade)
- **多段連結**: 2ファイル以上の順次クロスフェード連結
- **オーバーラップ制御**: 重複時間の細かい調整
- **カーブ選択**: tri/qsin/esin/hsin/log/ipar等の多彩なカーブ
- **順序変更**: ドラッグで再生順序を調整

### システム機能
- **タスクトレイ**: システムトレイでのバックグラウンド実行
- **多重起動防止**: 同一ディレクトリでの重複実行防止
- **設定保存**: GUI設定の自動保存・復元

## Installation

### バイナリ版
Release版のバイナリは [Releases](https://github.com/zukio/LoudSync/releases/) からダウンロードできます。

### ソースコード版
```bash
# 必要な依存関係をインストール
pip install -r requirements.txt

# GUIモードで実行
python main.py

# または
python main.py --gui
```

## 使用方法

### GUIモード（推奨）

1. `LoudSyncSuite.exe` をダブルクリックして実行
2. タブ式インターフェースで機能を選択：
   - **Normalize**: 正規化設定とプリセット選択
   - **Fade**: フェードイン/アウト設定
   - **Crossfade**: クロスフェード連結設定
3. 音声ファイルをドラッグ&ドロップで追加
4. パラメータを調整して実行

### コマンドラインモード

#### パイプライン実行
```bash
# 一括パイプライン（正規化→フェード→書き出し）
python main.py pipeline input_dir output.mp3 --preset podcast

# BGMプリセットで実行
python main.py pipeline bgm_files final_mix.wav --preset bgm
```

#### フェード処理
```bash
# 複数ファイルにフェード適用
python main.py fade file1.wav file2.wav --output-dir faded_output --fade-in 500 --fade-out 2000

# コーデック指定
python main.py fade *.mp3 --output-dir output --codec libmp3lame
```

#### クロスフェード連結
```bash
# 複数ファイルをクロスフェードで連結
python main.py crossfade song1.wav song2.wav song3.wav --output mix.mp3 --overlap 3.0

# カーブとコーデック指定
python main.py crossfade *.wav --output final.wav --overlap 2.5 --curve qsin --codec pcm_s16le
```

#### 旧LoudSync互換
```bash
# インタラクティブモード（プリセット選択）
python main.py --cli

# 測定のみ
python main.py --mode measure

# プリセット指定での正規化
python main.py --preset -16
```
- `--out-ext`: 出力形式（wav, mp3, m4a）
- `--sample-rate`: サンプリング周波数（44100, 48000, 96000）
- `--two-pass`: 2パス正規化（デフォルト有効）
- `--one-pass`: 1パス正規化を強制
- `--overwrite`: 既存ファイルの上書き許可

### プリセット一覧

| プリセット | 目標LUFS | True Peak | 用途 |
|-----------|----------|-----------|------|
| -16 | -16 LUFS | -1.5 dBTP | ポッドキャスト/配信 |
| -18 | -18 LUFS | -1.5 dBTP | BGM（余裕多め） |
| -19 | -19 LUFS | -1.5 dBTP | BGM（標準） |
| -20 | -20 LUFS | -1.5 dBTP | BGM（控えめ） |
| -23 | -23 LUFS | -1.0 dBTP | 放送（欧州基準） |
| reffile | 参照ファイル準拠 | -1.5 dBTP | 指定ファイルに合わせる |

### 設定ファイル

`config.json`でデフォルト設定を変更できます：

```json
{
    "input-dir": ".",
    "output-dir": "normalized",
    "out-ext": "wav",
    "sample-rate": 48000,
    "mode": "normalize",
    "preset": "interactive",
    "two-pass": true,
    "overwrite": false,
    "no-console": false,
    "single-instance-only": true
}
```

## ログとCSV出力

- **ログファイル**: `{output_dir}/LoudSync.log`
- **測定結果CSV**: `{output_dir}/loudness_measurement.csv`（測定モード時）

### CSV出力例

```csv
file,integrated_lufs,loudness_range,true_peak_dbtp,status
audio1.wav,-12.84,11.0,1.28,OK
audio2.wav,-58.28,8.1,-42.76,OK
```

## 開発

### 必要環境

- Python 3.8以降
- FFmpeg（システムPATHまたは`bin/ffmpeg.exe`）
- Windows 10以降

### 開発環境のセットアップ

1. 依存パッケージのインストール:

```bash
pip install aioconsole Pillow pystray
```

2. FFmpegの設置:
   - システムPATHにffmpegを追加、または
   - `bin/ffmpeg.exe`として同梱

## エラー処理

- **FFmpeg未検出**: PATH確認または`bin/ffmpeg.exe`設置の案内
- **対応外形式**: 対応形式（wav/mp3/m4a）のみ処理、それ以外はスキップ
- **破損ファイル**: エラー情報をログに記録し、次ファイルに続行
- **権限エラー**: 出力先の書き込み権限確認を案内

## トラブルシューティング

### FFmpeg not found

```bash
# システムにFFmpegをインストール
winget install FFmpeg

# または、bin/ffmpeg.exe として配置
```

### Unicode decode error

FFmpegの出力で文字化けが発生する場合、エラーは自動的に置換されます。

### Permission denied

出力ディレクトリの書き込み権限を確認してください。

---

## ライセンス

本ツールはFFmpegを外部プロセスとして使用します。FFmpegのライセンス（LGPL/GPL）に準拠し、必要なライセンス文書を`licenses/`ディレクトリに同梱してください。
