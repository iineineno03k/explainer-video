"""1 枚の画 (場面の画像・強調の枠・字幕) を HTML で組み、headless Chrome で PNG にする。"""
from __future__ import annotations

import html
import os
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image

W, H = 1920, 1080
STAGE = (40, 96, 1840, 640)  # x, y, w, h : 画像やカードを置く場所
e = html.escape

CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]


def find_chrome() -> str:
    env = os.environ.get("CHROME_PATH")
    if env and Path(env).exists():
        return env
    for c in CHROME_CANDIDATES:
        if Path(c).exists():
            return c
    for name in ("google-chrome", "chromium", "chromium-browser", "chrome", "msedge"):
        p = shutil.which(name)
        if p:
            return p
    raise RuntimeError("Chrome か Edge が見つからない。環境変数 CHROME_PATH に実行ファイルのパスを入れる。")


CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
html, body { width: 1920px; height: 1080px; overflow: hidden; }
body { background: #f3f2ec; color: #1d2430;
  font-family: "Hiragino Sans", "Hiragino Kaku Gothic ProN", "Yu Gothic UI", "Yu Gothic", "Meiryo", "Noto Sans JP", sans-serif; }
.top { position: absolute; left: 40px; right: 40px; top: 22px; height: 56px; display: flex; align-items: center; gap: 18px; }
.top .t { font-size: 34px; font-weight: 800; letter-spacing: .02em; }
.top .n { margin-left: auto; font-size: 24px; color: #6b7280; font-weight: 700; }
.stage { position: absolute; left: 40px; top: 96px; width: 1840px; height: 640px; display: grid; place-items: center; }
.view { position: relative; overflow: hidden; background: #fff; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,.12); }
.view img { position: absolute; max-width: none; }
.shade { position: absolute; left: 0; top: 0; }
.box { position: absolute; border: 6px solid #e0281b; border-radius: 6px; box-shadow: 0 0 0 3px rgba(255,255,255,.9); }
.box .lb { position: absolute; left: -6px; top: calc(100% + 4px); background: #e0281b; color: #fff; font-size: 28px; font-weight: 800;
  padding: 2px 12px; border-radius: 4px; white-space: nowrap; }
.box .lb.up { top: auto; bottom: calc(100% + 4px); }
.card { width: 1700px; background: #fff; border-radius: 14px; padding: 48px 64px; box-shadow: 0 2px 10px rgba(0,0,0,.12); }
.card h1 { font-size: 64px; font-weight: 900; line-height: 1.25; }
.card .sub { font-size: 32px; color: #4b5563; margin-top: 14px; }
.card ul { list-style: none; margin-top: 30px; display: grid; gap: 18px; }
.card li { font-size: 42px; font-weight: 700; line-height: 1.35; padding-left: 52px; position: relative; }
.card li::before { content: ""; position: absolute; left: 6px; top: .42em; width: 24px; height: 24px; border-radius: 50%; background: #e0281b; }
.card li.dim { color: #9ca3af; }
.card li.dim::before { background: #d1d5db; }
.point { position: absolute; left: 40px; right: 40px; top: 748px; height: 72px; display: flex; justify-content: center; }
.point span { background: #1d2430; color: #fff; font-size: 36px; font-weight: 800; padding: 10px 28px; border-radius: 8px; max-width: 1840px;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.sub-area { position: absolute; left: 0; right: 0; top: 836px; bottom: 0; }
.av { position: absolute; bottom: 26px; width: 150px; height: 150px; border-radius: 50%; display: grid; place-items: center;
  font-size: 76px; font-weight: 900; color: #fff; opacity: .28; transform: scale(.82); transition: none; overflow: hidden; }
.av img { width: 100%; height: 100%; object-fit: cover; }
.av.on { opacity: 1; transform: scale(1); box-shadow: 0 0 0 6px #fff, 0 4px 14px rgba(0,0,0,.25); }
.av.left { left: 36px; } .av.right { right: 36px; }
.say { position: absolute; left: 210px; right: 210px; top: 8px; bottom: 22px; background: #fff; border: 6px solid #999; border-radius: 16px;
  padding: 26px 34px 18px; display: flex; flex-direction: column; justify-content: center; }
.say .who { position: absolute; top: -26px; left: 26px; color: #fff; font-size: 28px; font-weight: 800; padding: 2px 16px; border-radius: 6px; }
.say .txt { font-size: 50px; font-weight: 800; line-height: 1.38; }
.credit { text-align: center; }
.credit h1 { font-size: 56px; }
.credit p { font-size: 40px; margin-top: 18px; color: #374151; }
"""


def _image_view(img_path: Path, zoom: dict | None, boxes: list[dict], dim: bool = True) -> str:
    with Image.open(img_path) as im:
        iw, ih = im.size
    x0, y0, cw, ch = 0, 0, iw, ih
    if zoom:
        x0, y0 = zoom.get("x", 0), zoom.get("y", 0)
        cw, ch = zoom.get("w", iw - x0), zoom.get("h", ih - y0)
    sw, sh = STAGE[2], STAGE[3]
    s = min(sw / cw, sh / ch)
    vw, vh = cw * s, ch * s
    out = [f'<div class="view" style="width:{vw:.1f}px;height:{vh:.1f}px">'
           f'<img src="{img_path.resolve().as_uri()}" style="width:{iw * s:.1f}px;left:{-x0 * s:.1f}px;top:{-y0 * s:.1f}px">']
    pad = 4
    rects = [((b["x"] - x0) * s - pad, (b["y"] - y0) * s - pad, b["w"] * s + pad * 2, b["h"] * s + pad * 2) for b in boxes or []]
    if rects and dim:  # 枠の外を暗くして、見る所を 1 か所に絞る
        holes = "".join(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="6" fill="#000"/>' for x, y, w, h in rects)
        out.append(f'<svg class="shade" width="{vw:.1f}" height="{vh:.1f}"><mask id="m"><rect width="100%" height="100%" fill="#fff"/>'
                   f'{holes}</mask><rect width="100%" height="100%" fill="rgba(15,23,42,.45)" mask="url(#m)"/></svg>')
    for b, (bx, by, bw, bh) in zip(boxes or [], rects):
        label = b.get("label")
        up = by + bh > vh - 60
        lb = f'<span class="lb{" up" if up else ""}">{e(label)}</span>' if label else ""
        out.append(f'<div class="box" style="left:{bx:.1f}px;top:{by:.1f}px;width:{bw:.1f}px;height:{bh:.1f}px">{lb}</div>')
    out.append("</div>")
    return "".join(out)


def _card(card: dict, upto: int | None) -> str:
    pts = card.get("points") or []
    lis = []
    for i, p in enumerate(pts):
        dim = upto is not None and i >= upto
        lis.append(f'<li class="{"dim" if dim else ""}">{e(str(p))}</li>')
    sub = f'<p class="sub">{e(card["sub"])}</p>' if card.get("sub") else ""
    ul = f"<ul>{''.join(lis)}</ul>" if lis else ""
    return f'<div class="card"><h1>{e(card.get("title", ""))}</h1>{sub}{ul}</div>'


def _avatar(sp: dict, side: str, on: bool) -> str:
    inner = f'<img src="{Path(sp["icon"]).resolve().as_uri()}">' if sp.get("icon") else e(sp.get("mark", sp["name"][:1]))
    return f'<div class="av {side}{" on" if on else ""}" style="background:{sp["color"]}">{inner}</div>'


def frame_html(frame: dict, speakers: dict, order: list[str]) -> str:
    """frame: {title, counter, image?, zoom?, boxes?, dim?, card?, card_upto?, point?, speaker?, text?, credit?}"""
    if frame.get("credit"):
        stage = '<div class="card credit">' + f"<h1>{e(frame.get('credit_title', ''))}</h1>" + "".join(
            f"<p>{e(x)}</p>" for x in frame["credit"]) + "</div>"
    elif frame.get("image"):
        stage = _image_view(Path(frame["image"]), frame.get("zoom"), frame.get("boxes") or [], frame.get("dim", True))
    else:
        stage = _card(frame.get("card") or {"title": frame.get("title", "")}, frame.get("card_upto"))
    point = f'<div class="point"><span>{e(frame["point"])}</span></div>' if frame.get("point") else ""
    sub = ""
    if frame.get("speaker"):
        sp = speakers[frame["speaker"]]
        avs = []
        # 顔は 2 つ。左は最初に話す人、右は 2 人目 (3 人目以降が話すときは、右をその人に替える)
        pair = order[:2]
        if frame["speaker"] not in pair:
            pair = [order[0], frame["speaker"]]
        for i, sid in enumerate(pair):
            avs.append(_avatar(speakers[sid], "left" if i == 0 else "right", sid == frame["speaker"]))
        txt = e(frame.get("text", "")).replace("\n", "<br>")
        sub = (f'<div class="sub-area">{"".join(avs)}<div class="say" style="border-color:{sp["color"]}">'
               f'<span class="who" style="background:{sp["color"]}">{e(sp["name"])}</span>'
               f'<div class="txt">{txt}</div></div></div>')
    top = f'<div class="top"><span class="t">{e(frame.get("title", ""))}</span><span class="n">{e(frame.get("counter", ""))}</span></div>'
    return (f'<!doctype html><html lang="ja"><head><meta charset="utf-8"><style>{CSS}</style></head>'
            f'<body>{top}<div class="stage">{stage}</div>{point}{sub}</body></html>')


def _shot(chrome: str, html_path: Path, png_path: Path, tries: int = 3) -> None:
    """Chrome はまれに固まるので、時間を切って描き直す。"""
    err = ""
    for _ in range(tries):
        with tempfile.TemporaryDirectory() as prof:
            cmd = [chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
                   "--no-default-browser-check", f"--user-data-dir={prof}", "--force-device-scale-factor=1",
                   f"--window-size={W},{H}", "--virtual-time-budget=4000", "--allow-file-access-from-files",
                   f"--screenshot={png_path.resolve()}", html_path.resolve().as_uri()]
            try:
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
                err = r.stderr[-2000:]
            except subprocess.TimeoutExpired:
                err = "60 秒で終わらなかった"
        if png_path.exists():
            return
    raise RuntimeError(f"画の描画に失敗した: {html_path}\n{err}")


def render_frames(frames: list[dict], speakers: dict, order: list[str], out_dir: Path, jobs: int = 4) -> list[Path]:
    chrome = find_chrome()
    out_dir.mkdir(parents=True, exist_ok=True)
    tasks = []
    for i, fr in enumerate(frames, 1):
        h = out_dir / f"f{i:04d}.html"
        p = out_dir / f"f{i:04d}.png"
        h.write_text(frame_html(fr, speakers, order), encoding="utf-8")
        if p.exists():
            p.unlink()
        tasks.append((h, p))
    with ThreadPoolExecutor(max_workers=max(1, jobs)) as ex:
        list(ex.map(lambda t: _shot(chrome, *t), tasks))
    for _, p in tasks:  # 窓の大きさの差で 1px ずれることがあるので、そろえる
        with Image.open(p) as im:
            if im.size != (W, H):
                im.convert("RGB").resize((W, H)).save(p)
    print(f"画 {len(tasks)} 枚を描いた ({out_dir})", file=sys.stderr)
    return [p for _, p in tasks]
