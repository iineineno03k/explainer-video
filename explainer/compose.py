"""画 (PNG) と台詞の wav を、字幕 (SRT) つきの mp4 に組み立てる。"""
from __future__ import annotations

import subprocess
import wave
from pathlib import Path

import imageio_ffmpeg

RATE = 24000  # VOICEVOX の既定の出力


def build_audio(segments: list[tuple[Path | None, float]], out: Path) -> list[float]:
    """segments: (wav か None, 後ろに足す無音の秒)。全体を 1 つの wav にし、各区間の長さ (秒) を返す。"""
    params = None
    lengths = []
    with wave.open(str(out), "wb") as dst:
        for wav, pause in segments:
            n = 0
            if wav is not None:
                with wave.open(str(wav), "rb") as src:
                    p = (src.getnchannels(), src.getsampwidth(), src.getframerate())
                    if params is None:
                        params = p
                        dst.setnchannels(p[0]); dst.setsampwidth(p[1]); dst.setframerate(p[2])
                    elif p != params:
                        raise RuntimeError(f"wav の形式がそろっていない: {wav}")
                    data = src.readframes(src.getnframes())
                    dst.writeframes(data)
                    n = src.getnframes()
            if params is None:
                params = (1, 2, RATE)
                dst.setnchannels(1); dst.setsampwidth(2); dst.setframerate(RATE)
            silent = int(round(pause * params[2]))
            dst.writeframes(b"\x00" * silent * params[0] * params[1])
            lengths.append((n + silent) / params[2])
    return lengths


def _ts(sec: float) -> str:
    ms = int(round(sec * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def write_srt(cues: list[tuple[float, float, str]], out: Path) -> None:
    lines = []
    for i, (a, b, text) in enumerate(cues, 1):
        lines += [str(i), f"{_ts(a)} --> {_ts(b)}", text, ""]
    out.write_text("\n".join(lines), encoding="utf-8")


def build_video(frames: list[Path], durations: list[float], audio: Path, out: Path) -> None:
    lst = frames[0].parent / "frames.txt"
    rows = []
    for f, d in zip(frames, durations):
        rows += [f"file '{f.name}'", f"duration {d:.3f}"]
    rows.append(f"file '{frames[-1].name}'")  # concat の決まり: 最後の画をもう一度書く
    lst.write_text("\n".join(rows) + "\n", encoding="utf-8")
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [ffmpeg, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-i", str(audio),
           "-vf", "fps=30,format=yuv420p", "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-tune", "stillimage",
           "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart", str(out)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg が失敗した:\n{r.stderr[-3000:]}")
