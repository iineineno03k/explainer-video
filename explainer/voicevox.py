"""VOICEVOX エンジン (HTTP API) で、台詞ごとの wav を作る。"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import urllib.parse
import urllib.request
import wave
from pathlib import Path

DEFAULT_URL = "http://127.0.0.1:50021"


class EngineError(RuntimeError):
    pass


def _request(url: str, data: bytes | None = None, headers: dict | None = None, timeout: float = 120) -> bytes:
    req = urllib.request.Request(url, data=data, headers=headers or {}, method="POST" if data is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except OSError as e:  # URLError も含む
        raise EngineError(
            f"VOICEVOX エンジンにつながらない ({url}): {e}\n"
            "README の「VOICEVOX を動かす」の手順でエンジンを起動してから、もう一度実行する。"
        ) from e


def check(base: str) -> str:
    return json.loads(_request(f"{base}/version", timeout=5))


def apply_readings(text: str, readings: dict[str, str]) -> str:
    """読みの辞書: 表記を読みに置き換えてから合成する (字幕は元の表記のまま)。長い表記から置き換える。"""
    for surface in sorted(readings, key=len, reverse=True):
        text = text.replace(surface, readings[surface])
    return text


def speak_text(text: str) -> str:
    """字幕用の記号を読み上げ用に整える。"""
    text = re.sub(r"[「」『』【】]", "", text)
    text = text.replace("→", "、").replace("…", "、")
    # 日本語と英数字の間の半角空白は、読むと変な間になるので消す
    return re.sub(r"(?<=[^\x00-\x7f]) +| +(?=[^\x00-\x7f])", "", text)


def synthesize(base: str, text: str, style_id: int, cache_dir: Path, *, speed: float = 1.0, pitch: float = 0.0,
               intonation: float = 1.0) -> Path:
    """台詞 1 つを wav にする。同じ内容は cache_dir から使い回す。"""
    key = hashlib.sha256(json.dumps([base.rstrip("/"), text, style_id, speed, pitch, intonation],
                                    ensure_ascii=False).encode()).hexdigest()[:20]
    out = cache_dir / f"{key}.wav"
    if out.exists():
        return out
    cache_dir.mkdir(parents=True, exist_ok=True)
    q = urllib.parse.urlencode({"text": text, "speaker": style_id})
    query = json.loads(_request(f"{base}/audio_query?{q}", data=b""))
    query.update({"speedScale": speed, "pitchScale": pitch, "intonationScale": intonation,
                  "prePhonemeLength": 0.05, "postPhonemeLength": 0.1})
    wav = _request(f"{base}/synthesis?speaker={style_id}", data=json.dumps(query).encode(),
                   headers={"Content-Type": "application/json"})
    tmp = out.with_suffix(".tmp")
    tmp.write_bytes(wav)
    tmp.replace(out)
    return out


def style_icon(base: str, style_id: int, cache_dir: Path) -> Path | None:
    """スタイルの公式アイコン (エンジンに入っている PNG) を cache_dir に書き出して返す。取れなければ None。"""
    try:
        speakers = json.loads(_request(f"{base}/speakers", timeout=10))
        uuid = next(sp["speaker_uuid"] for sp in speakers if any(st["id"] == style_id for st in sp["styles"]))
    except (EngineError, StopIteration, KeyError, ValueError):
        return None
    out = cache_dir / f"icon-{uuid}-{style_id}.png"
    if out.exists():
        return out
    try:
        info = json.loads(_request(f"{base}/speaker_info?{urllib.parse.urlencode({'speaker_uuid': uuid})}", timeout=30))
        icon = next(st.get("icon") for st in info["style_infos"] if st["id"] == style_id)
    except (EngineError, StopIteration, KeyError, ValueError):
        return None
    if not icon:
        return None
    cache_dir.mkdir(parents=True, exist_ok=True)
    out.write_bytes(base64.b64decode(icon))
    return out


def wav_seconds(path: Path) -> float:
    with wave.open(str(path), "rb") as w:
        return w.getnframes() / w.getframerate()
