"""explainer: 台本 (YAML) から解説動画を作るコマンド。

  explainer check                     エンジンにつながるか、話し手の一覧を見る
  explainer preview <台本.yaml>       音声なしで、台詞ごとの画だけを描く (見た目の確認)
  explainer build <台本.yaml>         音声を作り、mp4 と字幕 (SRT) まで作る
  explainer lines <台本.yaml>         台詞を場面をまたいで通しで並べる (読み直し・レビュー用)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

from . import compose, render, voicevox

DEFAULT_SPEAKERS = {
    "zundamon": {"name": "ずんだもん", "style_id": 3, "color": "#2f9e5a", "mark": "ず", "speed": 1.12},
    "metan": {"name": "四国めたん", "style_id": 2, "color": "#d8408c", "mark": "め", "speed": 1.08},
}
PAUSE_LINE = 0.35   # 台詞のあとの間 (秒)
PAUSE_SCENE = 0.8   # 場面の終わりの間 (秒)
TITLE_SEC = 2.5
CREDIT_SEC = 3.5


def load_script(path: Path) -> dict:
    s = yaml.safe_load(path.read_text(encoding="utf-8"))
    base = path.parent
    speakers = {k: dict(v) for k, v in DEFAULT_SPEAKERS.items()}
    for k, v in (s.get("speakers") or {}).items():
        speakers[k] = {**speakers.get(k, {}), **(v or {})}
    for sp in speakers.values():
        if sp.get("icon"):
            sp["icon"] = str((base / sp["icon"]).resolve())
    readings = s.get("readings") or {}
    if isinstance(readings, str):
        readings = yaml.safe_load((base / readings).read_text(encoding="utf-8")) or {}
    scenes = []
    for i, sc in enumerate(s.get("scenes") or [], 1):
        sc = dict(sc)
        if sc.get("image"):
            sc["image"] = str((base / sc["image"]).resolve())
            if not Path(sc["image"]).exists():
                raise SystemExit(f"場面 {i} の画像がない: {sc['image']}")
        lines = []
        for ln in sc.get("lines") or []:
            if isinstance(ln, dict) and "speaker" in ln:
                lines.append(dict(ln))
                continue
            keys = [k for k in ln if k in speakers]
            if len(keys) != 1:
                raise SystemExit(f"場面 {i} の台詞の話し手が分からない: {ln}")
            d = {k: v for k, v in ln.items() if k != keys[0]}
            d.update(speaker=keys[0], text=str(ln[keys[0]]))
            lines.append(d)
        if not lines:
            raise SystemExit(f"場面 {i} に台詞がない")
        sc["lines"] = lines
        scenes.append(sc)
    name = s.get("name") or path.stem
    out = Path(s["output"]) if s.get("output") else Path("out") / f"{name}.mp4"
    if not out.is_absolute():
        out = base / out
    return {"title": s.get("title", name), "subtitle": s.get("subtitle", ""), "speakers": speakers,
            "readings": {str(k): str(v) for k, v in readings.items()}, "scenes": scenes, "out": out,
            "order": list(dict.fromkeys(l["speaker"] for sc in scenes for l in sc["lines"])) or list(speakers)}


def fill_from_engine(script: dict, engine: str) -> None:
    """話し手の名前・顔が台本にないとき、エンジンから埋める (顔は公式のアイコン。icon: false で頭文字の丸)。"""
    names = {}
    try:
        names = {st["id"]: sp["name"] for sp in json.loads(voicevox._request(f"{engine}/speakers", timeout=10))
                 for st in sp["styles"]}
    except voicevox.EngineError:
        pass
    for k in script["order"]:
        sp = script["speakers"][k]
        sp.setdefault("color", "#4b5563")
        if not sp.get("name"):
            if int(sp["style_id"]) not in names:
                raise SystemExit(f"話し手 {k} の name がない。台本の speakers に name を書くか、エンジンを起動する。")
            sp["name"] = names[int(sp["style_id"])]
        if "icon" not in sp:
            icon = voicevox.style_icon(engine, int(sp["style_id"]), script["out"].parent / "cache")
            if icon:
                sp["icon"] = str(icon)


def plan_frames(sc: dict) -> list[dict]:
    """台詞ごとの画の中身を決める。"""
    frames = []
    title = sc.get("title", "")
    counter = f"{sc['_no']} / {len(sc['_all'])}"
    for k, ln in enumerate(sc["lines"]):
        fr = {"title": title, "counter": counter, "speaker": ln["speaker"], "text": ln.get("subtitle", ln["text"]),
              "point": ln.get("point", sc.get("point"))}
        if sc.get("image"):
            fr.update(image=sc["image"], zoom=ln.get("zoom", sc.get("zoom")), boxes=ln.get("boxes", sc.get("boxes")),
                      dim=ln.get("dim", sc.get("dim", True)))
        else:
            card = sc.get("card") or {"title": title}
            fr["card"] = card
            if card.get("reveal"):
                fr["card_upto"] = ln.get("upto", min(k + 1, len(card.get("points") or [])))
        frames.append(fr)
    return frames


def collect(script: dict) -> tuple[list[dict], list[dict]]:
    """全部の画と、それぞれに対応する台詞 (なければ None) の並び。"""
    frames, lines = [], []
    frames.append({"card": {"title": script["title"], "sub": script["subtitle"]}, "title": "", "counter": ""})
    lines.append({"pause": TITLE_SEC})
    for no, sc in enumerate(script["scenes"], 1):
        sc["_no"], sc["_all"] = no, script["scenes"]
        fs = plan_frames(sc)
        for k, (fr, ln) in enumerate(zip(fs, sc["lines"])):
            frames.append(fr)
            last = k == len(fs) - 1
            lines.append({**ln, "pause": ln.get("pause", PAUSE_SCENE if last else PAUSE_LINE)})
    names = [f"VOICEVOX:{script['speakers'][k]['name']}" for k in script["order"]]
    frames.append({"credit": names, "credit_title": "音声", "title": ""})
    lines.append({"pause": CREDIT_SEC})
    return frames, lines


def cmd_check(a) -> None:
    print("VOICEVOX エンジン", voicevox.check(a.engine))
    data = json.loads(voicevox._request(f"{a.engine}/speakers"))
    for sp in data:
        print(sp["name"], ", ".join(f"{x['name']}={x['id']}" for x in sp["styles"]))


def cmd_preview(a) -> None:
    script = load_script(Path(a.script))
    fill_from_engine(script, a.engine)
    frames, _ = collect(script)
    out = script["out"].parent / (script["out"].stem + "-preview")
    render.render_frames(frames, script["speakers"], script["order"], out, a.jobs)
    print(out)


def cmd_build(a) -> None:
    script = load_script(Path(a.script))
    out = Path(a.out) if a.out else script["out"]
    work = out.parent / (out.stem + "-work")
    voicevox.check(a.engine)
    fill_from_engine(script, a.engine)
    frames, lines = collect(script)
    segs, cues, t = [], [], 0.0
    for ln in lines:
        if "speaker" not in ln:
            segs.append((None, ln["pause"]))
            continue
        sp = script["speakers"][ln["speaker"]]
        text = voicevox.speak_text(voicevox.apply_readings(ln["text"], script["readings"]))
        wav = voicevox.synthesize(a.engine, text, int(ln.get("style_id", sp["style_id"])), out.parent / "cache",
                                  speed=float(ln.get("speed", sp.get("speed", 1.0))),
                                  pitch=float(sp.get("pitch", 0.0)), intonation=float(sp.get("intonation", 1.0)))
        segs.append((wav, ln["pause"]))
    work.mkdir(parents=True, exist_ok=True)
    durations = compose.build_audio(segs, work / "audio.wav")
    for (wav, pause), ln, d in zip(segs, lines, durations):
        if wav is not None:
            cues.append((t, t + d - pause, f"{script['speakers'][ln['speaker']]['name']}「{ln.get('subtitle', ln['text'])}」"))
        t += d
    pngs = render.render_frames(frames, script["speakers"], script["order"], work / "frames", a.jobs)
    compose.build_video(pngs, durations, work / "audio.wav", out)
    compose.write_srt(cues, out.with_suffix(".srt"))
    print(f"できた: {out} ({t:.1f} 秒, 台詞 {len(cues)} 本)")


def cmd_lines(a) -> None:
    """台詞を通しで並べる。画面に出す一言 (point) と赤枠の名前 (label) も添える。"""
    s = load_script(Path(a.script))
    names = {k: v.get("name", k) for k, v in s["speakers"].items()}
    for i, sc in enumerate(s["scenes"], 1):
        print(f"\n## {i}. {sc.get('title', '')}")
        for j, ln in enumerate(sc["lines"], 1):
            print(f"{i}-{j:02d} {names.get(ln['speaker'], ln['speaker'])}: {ln['text']}")
            extra = []
            point = ln.get("point", sc.get("point"))  # 描くときと同じく、台詞になければ場面のもの
            if point:
                extra.append(f"画面: {point}")
            boxes = ln.get("boxes", sc.get("boxes")) if sc.get("image") else None
            labels = [b.get("label") for b in (boxes or []) if b.get("label")]
            if labels:
                extra.append("赤枠: " + "・".join(labels))
            if extra:
                print("      (" + " / ".join(extra) + ")")


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="explainer", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--engine", default=voicevox.DEFAULT_URL, help="VOICEVOX エンジンの URL")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check")
    for name in ("preview", "build"):
        s = sub.add_parser(name)
        s.add_argument("script")
        s.add_argument("--jobs", type=int, default=4, help="同時に描く画の数")
        if name == "build":
            s.add_argument("--out", help="mp4 の出力先 (既定は台本の output)")
    sub.add_parser("lines").add_argument("script")
    a = p.parse_args(argv)
    try:
        {"check": cmd_check, "preview": cmd_preview, "build": cmd_build, "lines": cmd_lines}[a.cmd](a)
    except voicevox.EngineError as err:
        print(err, file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
