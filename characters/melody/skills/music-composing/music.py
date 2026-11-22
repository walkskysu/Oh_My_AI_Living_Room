#!/usr/bin/env python3
"""Melody's ComfyUI client: songs and instrumentals with MiniMax Music 3.

Standard library only (works with any Python 3.8+ on Linux / macOS / Windows).
The server comes from --url, else the COMFYUI_URL environment variable, else
http://127.0.0.1:8188.

  python music.py check
  python music.py compose --caption-file outputs/x.caption.txt --lyrics-file outputs/x.lyrics.txt \
                          --duration 150 --out outputs/x.mp3 [--seed N] [--format mp3|flac]
  python music.py compose --caption-file outputs/x.caption.txt --instrumental --duration 120 --out outputs/x.mp3
  python music.py wait <prompt_id> --out outputs/x.mp3   (resume a job that outlived the shell timeout)

Every command prints one JSON object on its last line ({"ok": true, ...} or {"ok": false, "error": ...}).
"""
import argparse
import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
WF = os.path.join(HERE, "workflows", "song.json")
DEFAULT_URL = "http://127.0.0.1:8188"
SAVE_NODE = "35"
MAX_SECONDS = 300
TAG_LINE = re.compile(r"^\s*\[[^\]]+\]\s*$")


def instrumental_lyrics(seconds):
    """Instrumental pieces still need section tags (the only structure the model follows), and
    with too few of them it tends to wrap up early: about one section per 15 s."""
    middle = max(2, round(seconds / 15) - 2)
    body = ["[Solo]" if i % 3 == 1 else "[Instrumental]" for i in range(middle)]
    return "\n\n".join(["[Intro]", *body, "[Outro]"])


class ComfyError(Exception):
    pass


def emit(obj):
    print(json.dumps(obj, ensure_ascii=False))
    sys.stdout.flush()


def log(msg):
    print(msg, file=sys.stderr)
    sys.stderr.flush()


class Comfy:
    def __init__(self, url):
        self.url = url.rstrip("/")
        self.client_id = uuid.uuid4().hex

    def _req(self, method, path, data=None, headers=None, timeout=60):
        req = urllib.request.Request(self.url + path, data=data, method=method, headers=headers or {})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            raise ComfyError(f"HTTP {e.code} {path}: {body[:2000]}")
        except (urllib.error.URLError, OSError) as e:
            raise ComfyError(
                f"连不上 ComfyUI（{self.url}）：{e}. 请确认 ComfyUI 已启动，或在客厅设置里修改 ComfyUI 地址。"
            )

    def get_json(self, path, timeout=60):
        return json.loads(self._req("GET", path, timeout=timeout))

    def post_json(self, path, obj):
        data = json.dumps(obj).encode("utf-8")
        return json.loads(self._req("POST", path, data, {"Content-Type": "application/json"}))

    def queue(self, prompt):
        res = self.post_json("/prompt", {"prompt": prompt, "client_id": self.client_id})
        if res.get("node_errors"):
            raise ComfyError("工作流校验失败：" + json.dumps(res["node_errors"], ensure_ascii=False)[:2000])
        return res["prompt_id"]

    def wait(self, prompt_id, timeout):
        """Poll /history until the job finishes; returns its history entry."""
        start = time.time()
        last_note = 0.0
        while True:
            h = self.get_json(f"/history/{prompt_id}")
            if prompt_id in h:
                entry = h[prompt_id]
                status = entry.get("status", {})
                if status.get("status_str") == "error":
                    for kind, msg in status.get("messages", []):
                        if kind == "execution_error":
                            raise ComfyError(
                                f"ComfyUI 执行出错（节点 {msg.get('node_type')}）：{msg.get('exception_message', '').strip()}"
                            )
                    raise ComfyError("ComfyUI 执行出错：" + json.dumps(status, ensure_ascii=False)[:1500])
                if status.get("completed", True):
                    return entry
            elapsed = time.time() - start
            if elapsed > timeout:
                raise ComfyError(
                    f"等待超时（{int(elapsed)}s），歌曲仍在 ComfyUI 中生成。请运行："
                    f"python .claude/skills/music-composing/music.py wait {prompt_id} --out <同一个路径> 继续等待并取回结果。"
                )
            if elapsed - last_note >= 30:
                last_note = elapsed
                try:
                    q = self.get_json("/queue")
                    pos = next((i for i, j in enumerate(q.get("queue_pending", [])) if j[1] == prompt_id), None)
                    state = "排队中（前面还有 %d 个）" % (pos + len(q.get("queue_running", []))) if pos is not None else "创作中"
                except ComfyError:
                    state = "创作中"
                log(f"[music] {state}… {int(elapsed)}s")
            time.sleep(2)

    def download(self, info, dest):
        q = urllib.parse.urlencode({"filename": info["filename"], "subfolder": info.get("subfolder", ""), "type": info.get("type", "output")})
        data = self._req("GET", f"/view?{q}", timeout=300)
        os.makedirs(os.path.dirname(os.path.abspath(dest)) or ".", exist_ok=True)
        with open(dest, "wb") as f:
            f.write(data)
        return dest


# ---------------------------------------------------------------- utilities
def unique_path(path):
    if not os.path.exists(path):
        return path
    stem, ext = os.path.splitext(path)
    i = 2
    while os.path.exists(f"{stem}-{i}{ext}"):
        i += 1
    return f"{stem}-{i}{ext}"


def read_text(inline, path, what):
    if path:
        if not os.path.isfile(path):
            raise ComfyError(f"找不到{what}文件：{path}")
        with open(path, encoding="utf-8-sig") as f:
            return f.read().strip()
    return (inline or "").strip()


def has_sung_lines(lyrics):
    return any(line.strip() and not TAG_LINE.match(line) for line in lyrics.splitlines())


_BITRATES = {  # MPEG-1 / MPEG-2(.5) layer III, kbps
    1: [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320],
    2: [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160],
}
_RATES = {3: [44100, 48000, 32000], 2: [22050, 24000, 16000], 0: [11025, 12000, 8000]}


def audio_seconds(path):
    """Length of an MP3 (frame scan) or FLAC (STREAMINFO) file, or None."""
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError:
        return None
    if data[:4] == b"fLaC" and len(data) > 26:
        b = data[18:26]
        rate = (b[0] << 12) | (b[1] << 4) | (b[2] >> 4)
        total = ((b[3] & 0x0F) << 32) | int.from_bytes(b[4:8], "big")
        return round(total / rate, 1) if rate else None
    i = 0
    if data[:3] == b"ID3" and len(data) > 10:
        i = 10 + ((data[6] & 0x7F) << 21 | (data[7] & 0x7F) << 14 | (data[8] & 0x7F) << 7 | (data[9] & 0x7F))
    seconds, frames = 0.0, 0
    n = len(data)
    while i + 4 <= n:
        h = int.from_bytes(data[i:i + 4], "big")
        if (h >> 21) & 0x7FF != 0x7FF:
            i += 1
            continue
        ver, layer, br_i, sr_i, pad = (h >> 19) & 3, (h >> 17) & 3, (h >> 12) & 15, (h >> 10) & 3, (h >> 9) & 1
        if ver == 1 or layer != 1 or br_i in (0, 15) or sr_i == 3:
            i += 1
            continue
        rate = _RATES[ver][sr_i]
        br = _BITRATES[1 if ver == 3 else 2][br_i] * 1000
        samples = 1152 if ver == 3 else 576
        size = samples // 8 * br // rate + pad
        if size <= 0:
            i += 1
            continue
        seconds += samples / rate
        frames += 1
        i += size
    return round(seconds, 1) if frames else None


def save_audio(comfy, entry, out):
    items = entry.get("outputs", {}).get(SAVE_NODE, {}).get("audio", [])
    if not items:
        raise ComfyError("ComfyUI 没有返回音频：" + json.dumps(entry.get("outputs", {}), ensure_ascii=False)[:800])
    info = items[0]
    ext = os.path.splitext(info["filename"])[1] or ".mp3"
    stem, cur = os.path.splitext(out)
    if cur.lower() != ext.lower():
        out = stem + ext
    return comfy.download(info, unique_path(out)).replace("\\", "/")


def write_sidecar(audio_path, meta):
    """outputs/<song>.json next to the audio: caption, lyrics, seed, so a take can be reproduced."""
    side = os.path.splitext(audio_path)[0] + ".json"
    with open(side, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    return side.replace("\\", "/")


# ---------------------------------------------------------------- commands
def cmd_check(comfy, args):
    s = comfy.get_json("/system_stats", timeout=10)
    dev = (s.get("devices") or [{}])[0]
    info = {}
    try:
        info = comfy.get_json("/object_info/MiniMaxMusic3TextEncode", timeout=20)
    except ComfyError:
        pass
    emit({
        "ok": True,
        "url": comfy.url,
        "comfyui_version": s.get("system", {}).get("comfyui_version"),
        "gpu": dev.get("name"),
        "vram_free_gb": round(dev.get("vram_free", 0) / 2**30, 1),
        "minimax_music3_nodes": bool(info),
    })


def cmd_compose(comfy, args):
    caption = read_text(args.caption, args.caption_file, "风格描述（caption）")
    lyrics = read_text(args.lyrics, args.lyrics_file, "歌词")
    if not caption:
        raise ComfyError("缺少风格描述：用 --caption-file（推荐）或 --caption 提供")
    if args.instrumental:
        if lyrics and has_sung_lines(lyrics):
            raise ComfyError("--instrumental（纯音乐）时歌词里只能有 [Intro] [Instrumental] 这类段落标签，不能有要唱的句子")
        lyrics = lyrics or instrumental_lyrics(args.duration)
    elif not lyrics:
        raise ComfyError("缺少歌词：用 --lyrics-file 提供；要做纯音乐请加 --instrumental")
    if not 10 <= args.duration <= MAX_SECONDS:
        raise ComfyError(f"--duration 要在 10–{MAX_SECONDS} 秒之间")
    seed = args.seed if args.seed is not None else random.randint(1, 2**31 - 1)

    with open(WF, encoding="utf-8") as f:
        wf = json.load(f)
    enc = wf["37:13"]["inputs"]
    enc.update(caption=caption, lyrics=lyrics, max_duration=float(args.duration))
    wf["37:38"]["inputs"]["seed"] = seed
    wf["37:9"]["inputs"]["steps"] = args.steps
    save = wf[SAVE_NODE]["inputs"]
    if args.format == "flac":
        save["format"] = "flac"
        save.pop("format.quality", None)
    pid = comfy.queue(wf)
    log(f"[music] 已提交作曲任务 {pid}（目标时长 {args.duration}s，通常需要 1.5–3 倍时长的时间）")
    meta = {"caption": caption, "lyrics": lyrics, "instrumental": bool(args.instrumental), "seed": seed,
            "max_duration": args.duration, "steps": args.steps, "prompt_id": pid}
    # remember the request so `wait` can still write the sidecar after a shell timeout
    pending = os.path.splitext(args.out)[0] + ".pending.json"
    os.makedirs(os.path.dirname(os.path.abspath(pending)) or ".", exist_ok=True)
    with open(pending, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    entry = comfy.wait(pid, args.timeout)
    finish(comfy, entry, args.out, meta, pending)


def finish(comfy, entry, out, meta, pending=None):
    path = save_audio(comfy, entry, out)
    meta = dict(meta, file=path, seconds=audio_seconds(path))
    side = write_sidecar(path, meta)
    if pending and os.path.exists(pending):
        os.remove(pending)
    emit({"ok": True, "file": path, "seconds": meta["seconds"], "seed": meta.get("seed"),
          "instrumental": meta.get("instrumental"), "info": side, "prompt_id": meta.get("prompt_id")})


def cmd_wait(comfy, args):
    entry = comfy.wait(args.prompt_id, args.timeout)
    pending = os.path.splitext(args.out)[0] + ".pending.json"
    meta = {"prompt_id": args.prompt_id}
    if os.path.exists(pending):
        with open(pending, encoding="utf-8") as f:
            meta = json.load(f)
    finish(comfy, entry, args.out, meta, pending)


def main():
    if hasattr(sys.stdout, "reconfigure"):
        # Windows consoles default to a legacy code page; we print Chinese.
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default=os.environ.get("COMFYUI_URL") or DEFAULT_URL)
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("check")

    p = sub.add_parser("compose", help="作曲（MiniMax Music 3）：歌曲或纯音乐")
    p.add_argument("--caption-file", help="风格描述文件（英文，Global Metadata / Vocal Details / Arrangement 三段）")
    p.add_argument("--caption", help="风格描述（短的时候可以直接写在命令行）")
    p.add_argument("--lyrics-file", help="歌词文件（带 [Verse] [Chorus] 等段落标签）")
    p.add_argument("--lyrics")
    p.add_argument("--instrumental", action="store_true", help="纯音乐：没有人声；歌词可省略或只写段落标签")
    p.add_argument("--duration", type=float, default=120, help=f"最长时长（秒，10–{MAX_SECONDS}），模型可能提前结束")
    p.add_argument("--out", required=True, help="保存路径，如 outputs/晴天的猫.mp3")
    p.add_argument("--format", choices=("mp3", "flac"), default="mp3")
    p.add_argument("--steps", type=int, default=30)
    p.add_argument("--seed", type=int)
    p.add_argument("--timeout", type=int, default=560, help="最长等待秒数（超时后用 wait 继续取）")

    p = sub.add_parser("wait", help="继续等待之前提交的作曲任务并取回结果")
    p.add_argument("prompt_id")
    p.add_argument("--out", required=True)
    p.add_argument("--timeout", type=int, default=560)

    args = ap.parse_args()
    comfy = Comfy(args.url)
    try:
        {"check": cmd_check, "compose": cmd_compose, "wait": cmd_wait}[args.cmd](comfy, args)
    except ComfyError as e:
        emit({"ok": False, "error": str(e)})
        sys.exit(1)
    except KeyboardInterrupt:
        emit({"ok": False, "error": "已中断"})
        sys.exit(130)


if __name__ == "__main__":
    main()
