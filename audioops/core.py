import subprocess
import json
import shlex
from pathlib import Path


def run(cmd: list[str]):
    print("RUN:", " ".join(shlex.quote(x) for x in cmd))
    subprocess.check_call(cmd)


def duration_sec(path: Path) -> float:
    out = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(
            path)
    ]).decode()
    return float(json.loads(out)["format"]["duration"])


def fade_file(infile: Path, outfile: Path,
              fade_in_ms=0, fade_out_ms=0,
              fade_out_from_end_sec: float | None = None,
              fade_out_start_sec: float | None = None,
              codec="aac"):
    dur = duration_sec(infile)
    fin = max(fade_in_ms/1000, 0.0)
    fout = max(fade_out_ms/1000, 0.0)
    if fade_out_from_end_sec is not None:
        st_out = max(dur - fade_out_from_end_sec, 0.0)
    elif fade_out_start_sec is not None:
        st_out = max(fade_out_start_sec, 0.0)
    else:
        st_out = max(dur - fout, 0.0)

    filters = []
    if fin > 0:
        filters.append(f"afade=t=in:st=0:d={fin}")
    if fout > 0:
        filters.append(f"afade=t=out:st={st_out}:d={fout}")

    # フィルターが何もない場合はanullを使用
    af = ",".join(filters) if filters else "anull"

    # 出力ファイルの拡張子に応じてコーデックを自動選択
    outfile_ext = outfile.suffix.lower()
    if outfile_ext == '.wav':
        codec = 'pcm_s16le'  # WAVファイルにはPCMを使用
    elif outfile_ext == '.mp3':
        codec = 'libmp3lame'
    elif outfile_ext in ['.m4a', '.aac']:
        codec = 'aac'

    run(["ffmpeg", "-y", "-i", str(infile), "-vn",
        "-af", af, "-c:a", codec, str(outfile)])


def crossfade_sequence(inputs: list[Path], outfile: Path, overlap_sec=2.0,
                       curve1="tri", curve2="tri", codec="libmp3lame"):
    assert len(inputs) >= 2
    args = ["ffmpeg", "-y"]
    for p in inputs:
        args += ["-i", str(p)]
    chains = []
    prev = "[0:a]"
    for i in range(1, len(inputs)):
        out = f"[a{i}]"
        chains.append(
            f"{prev}[{i}:a]acrossfade=d={overlap_sec}:c1={curve1}:c2={curve2}{out}")
        prev = out
    filter_complex = ";".join(chains)
    args += ["-filter_complex", filter_complex,
             "-map", prev, "-c:a", codec, str(outfile)]
    run(args)
