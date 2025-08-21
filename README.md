# LoudSync

Measure the loudness (LUFS)/peak of multiple audio files and batch normalize them to a specified preset or reference file.

---

## 使い方（例）

同じフォルダの音源を対話で正規化（出力は normalized/*.wav）

### 正規化（ターゲット選択）

ユーザーが以下から選択：

1. **指定ファイルにそろえる**（参照ファイルの Integrated LUFS を使用 / TPは安全側制限）
2. **配信/ポッドキャスト**：-16 LUFS / TP -1.5 dBTP
3. **BGM（余裕多め）**：-18 / -19 / -20 LUFS（TP -1.5 dBTP）
4. **放送（欧州基準）**：-23 LUFS / TP -1.0 dBTP

> 補足：正規化は **2パス方式（ffmpeg loudnorm）** を標準とする。1パスも選択可（高速・微誤差許容）。

### 入出力

* 入力：`.wav .mp3 .m4a`（将来拡張で他フォーマット）
* 出力：デフォルト `.wav`／引数で `.mp3` など指定可
* サンプリング周波数：既定 48 kHz（引数で指定可）
* 出力先：`normalized` フォルダ（既定）／引数で変更可
* 同名ファイルがある場合：上書き／別名付与（設定）

### 基本コマンド

* **同じフォルダの音源を正規化**

  ``` bash
  .\\LoudSync.ps1
  ```

* **引数で入力・出力指定（例）**

  ``` bash
  .\\LoudSync.ps1 -InputDir "D:\audio\in" -OutputDir "D:\audio\out" -OutExt "mp3" -SampleRate 48000
  ```

#### 主な引数

* `-InputDir`（既定 `"."`）
* `-OutputDir`（既定 `"normalized"`）
* `-OutExt`：`wav|mp3|m4a`（既定 `"wav"`）
* `-SampleRate`：`44100|48000|…`（既定 `48000`）
* `-Mode`：`Measure|Normalize`（既定は Normalize）
* `-Preset`：`RefFile|-16|-18|-19|-20|-23`
* `-RefPath`：参照ファイルのパス（`-Preset RefFile` 時に必須）
* `-OnePass`：スイッチ指定で 1 パス運用
* `-Csv`：計測結果を CSV に保存
* `-Overwrite`：上書き許可

---

## 依存関係

[ffmpeg](https://www.ffmpeg.org/) をインストールしてください。

### ffmpeg 解決順

1. **環境変数 PATH の ffmpeg** を優先
2. 見つからなければ **同梱 `bin\ffmpeg.exe`** を使用
3. どちらも無ければエラー終了（メッセージ表示）

### ライセンス配慮

* FFmpeg（LGPL/GPL 構成）を**別プロセス実行**で利用
* 同梱再配布時は **ライセンス文面と入手元**の明記、`licenses/ffmpeg-LICENSE.txt` を同梱
