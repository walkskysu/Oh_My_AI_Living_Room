#!/usr/bin/env python3
"""Poppy's ComfyUI client: text-to-image, image edit, image description, layer split.

Standard library only (works with any Python 3.8+ on Linux / macOS / Windows).
The server comes from --url, else the COMFYUI_URL environment variable, else
http://127.0.0.1:8188.

  python comfy.py check
  python comfy.py t2i      --prompt "..." --out outputs/cat.png [--aspect 16:9] [--mp 1.0] [--negative "..."]
  python comfy.py edit     --image inputs/a.png [--image2 inputs/b.png] --prompt "..." --out outputs/a-edit.png
  python comfy.py describe --image inputs/a.png [--mode detailed|ultra|tags|simple|cinematic|analysis] [--ask "..."]
  python comfy.py layers   --image inputs/a.png --out-dir outputs/a-layers
  python comfy.py wait     <prompt_id> --out ... | --out-dir ...   (resume a job that outlived the shell timeout)

Every command prints one JSON object on its last line ({"ok": true, ...} or {"ok": false, "error": ...}).
"""
import argparse
import json
import os
import random
import struct
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
WF = os.path.join(HERE, "workflows")
DEFAULT_URL = "http://127.0.0.1:8188"

ASPECTS = {
    "1:1": "1:1 (Square)",
    "2:3": "2:3 (Portrait Photo)",
    "3:2": "3:2 (Photo)",
    "3:4": "3:4 (Portrait Standard)",
    "4:3": "4:3 (Standard)",
    "9:16": "9:16 (Portrait Widescreen)",
    "16:9": "16:9 (Widescreen)",
    "21:9": "21:9 (Ultrawide)",
}
DESCRIBE_MODES = {
    "tags": "🖼️ Tags",
    "simple": "🖼️ Simple Description",
    "detailed": "🖼️ Detailed Description",
    "ultra": "🖼️ Ultra Detailed Description",
    "cinematic": "🎬 Cinematic Description",
    "analysis": "🖼️ Detailed Analysis",
}


class ComfyError(Exception):
    pass


def emit(obj):
    print(json.dumps(obj, ensure_ascii=False))
    sys.stdout.flush()


def log(msg):
    print(msg, file=sys.stderr)
    sys.stderr.flush()


# ---------------------------------------------------------------- HTTP helpers
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

    def upload(self, path):
        """Upload a local image to ComfyUI's input dir; returns the name to reference."""
        if not os.path.isfile(path):
            raise ComfyError(f"找不到图片：{path}")
        boundary = "----poppy" + uuid.uuid4().hex
        name = f"poppy_{uuid.uuid4().hex[:8]}_{os.path.basename(path)}"
        with open(path, "rb") as f:
            content = f.read()
        parts = []
        for k, v in (("type", "input"), ("overwrite", "true")):
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
        parts.append(
            (
                f'--{boundary}\r\nContent-Disposition: form-data; name="image"; filename="{name}"\r\n'
                f"Content-Type: application/octet-stream\r\n\r\n"
            ).encode("utf-8")
            + content
            + b"\r\n"
        )
        parts.append(f"--{boundary}--\r\n".encode())
        res = json.loads(
            self._req("POST", "/upload/image", b"".join(parts), {"Content-Type": f"multipart/form-data; boundary={boundary}"}, timeout=300)
        )
        sub = res.get("subfolder") or ""
        return f"{sub}/{res['name']}" if sub else res["name"]

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
                if status.get("status_str") == "error" or (status.get("completed") is False and status.get("messages")):
                    for kind, msg in status.get("messages", []):
                        if kind == "execution_error":
                            raise ComfyError(
                                f"ComfyUI 执行出错（节点 {msg.get('node_type')}）：{msg.get('exception_message', '').strip()}"
                            )
                    if status.get("status_str") == "error":
                        raise ComfyError("ComfyUI 执行出错：" + json.dumps(status, ensure_ascii=False)[:1500])
                if status.get("completed", True):
                    return entry
            elapsed = time.time() - start
            if elapsed > timeout:
                raise ComfyError(
                    f"等待超时（{int(elapsed)}s），任务仍在 ComfyUI 中运行。可以稍后运行："
                    f"python comfy.py wait {prompt_id} ... 继续等待并取回结果。"
                )
            if elapsed - last_note >= 30:
                last_note = elapsed
                try:
                    q = self.get_json("/queue")
                    pos = next((i for i, j in enumerate(q.get("queue_pending", [])) if j[1] == prompt_id), None)
                    state = "排队中（前面还有 %d 个）" % (pos + len(q.get("queue_running", []))) if pos is not None else "生成中"
                except ComfyError:
                    state = "生成中"
                log(f"[comfy] {state}… {int(elapsed)}s")
            time.sleep(2)

    def download(self, info, dest):
        q = urllib.parse.urlencode({"filename": info["filename"], "subfolder": info.get("subfolder", ""), "type": info.get("type", "output")})
        data = self._req("GET", f"/view?{q}", timeout=300)
        os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
        with open(dest, "wb") as f:
            f.write(data)
        return dest


# ---------------------------------------------------------------- utilities
def load_wf(name):
    with open(os.path.join(WF, name + ".json"), encoding="utf-8") as f:
        return json.load(f)


def unique_path(path):
    if not os.path.exists(path):
        return path
    stem, ext = os.path.splitext(path)
    i = 2
    while os.path.exists(f"{stem}-{i}{ext}"):
        i += 1
    return f"{stem}-{i}{ext}"


def image_size(path):
    """(width, height) of a PNG/JPEG/WebP, or None."""
    try:
        with open(path, "rb") as f:
            head = f.read(64)
            if head[:8] == b"\x89PNG\r\n\x1a\n":
                return struct.unpack(">II", head[16:24])
            if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
                chunk = head[12:16]
                if chunk == b"VP8X":
                    w = 1 + int.from_bytes(head[24:27], "little")
                    h = 1 + int.from_bytes(head[27:30], "little")
                    return w, h
                if chunk == b"VP8 ":
                    w, h = struct.unpack("<HH", head[26:30])
                    return w & 0x3FFF, h & 0x3FFF
                if chunk == b"VP8L":
                    b = head[21:25]
                    w = 1 + (((b[1] & 0x3F) << 8) | b[0])
                    h = 1 + (((b[3] & 0xF) << 10) | (b[2] << 2) | ((b[1] & 0xC0) >> 6))
                    return w, h
            if head[:2] == b"\xff\xd8":
                f.seek(2)
                while True:
                    marker = f.read(2)
                    if len(marker) < 2 or marker[0] != 0xFF:
                        return None
                    if marker[1] in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                        f.read(3)
                        h, w = struct.unpack(">HH", f.read(4))
                        return w, h
                    seglen = struct.unpack(">H", f.read(2))[0]
                    f.seek(seglen - 2, 1)
    except (OSError, struct.error):
        return None
    return None


def output_images(entry, node_id):
    out = entry.get("outputs", {}).get(node_id, {})
    return [i for i in out.get("images", []) if i.get("type", "output") == "output"] or out.get("images", [])


def save_outputs(comfy, entry, node_id, out):
    imgs = output_images(entry, node_id)
    if not imgs:
        raise ComfyError("ComfyUI 没有返回图片：" + json.dumps(entry.get("outputs", {}), ensure_ascii=False)[:800])
    saved = []
    stem, ext = os.path.splitext(out)
    for i, info in enumerate(imgs):
        dest = out if len(imgs) == 1 else f"{stem}-{i + 1}{ext or '.png'}"
        if not os.path.splitext(dest)[1]:
            dest += os.path.splitext(info["filename"])[1] or ".png"
        saved.append(comfy.download(info, unique_path(dest)).replace("\\", "/"))
    return saved


def seed_of(args):
    return args.seed if args.seed is not None else random.randint(1, 2**31 - 1)


# ---------------------------------------------------------------- commands
def cmd_check(comfy, args):
    s = comfy.get_json("/system_stats", timeout=10)
    dev = (s.get("devices") or [{}])[0]
    emit({
        "ok": True,
        "url": comfy.url,
        "comfyui_version": s.get("system", {}).get("comfyui_version"),
        "gpu": dev.get("name"),
        "vram_free_gb": round(dev.get("vram_free", 0) / 2**30, 1),
    })


def cmd_t2i(comfy, args):
    wf = load_wf("t2i")
    if args.aspect not in ASPECTS:
        raise ComfyError(f"--aspect 只能是 {', '.join(ASPECTS)}")
    seed = seed_of(args)
    wf["13"]["inputs"].update(aspect_ratio=ASPECTS[args.aspect], megapixels=args.mp)
    wf["459:471"]["inputs"]["prompt"] = args.prompt
    # Qwen 3.5 prompt enhancer: on_true = rewritten prompt, on_false = the prompt as given
    wf["459:474"]["inputs"].update(switch=bool(args.enhance), on_false=args.prompt)
    wf["459:452"]["inputs"]["negative_prompt"] = args.negative or ""
    wf["459:458"]["inputs"].update(seed=seed, steps=args.steps)
    wf["459:456"]["inputs"]["batch_size"] = args.count
    pid = comfy.queue(wf)
    log(f"[comfy] 已提交 t2i 任务 {pid}")
    entry = comfy.wait(pid, args.timeout)
    files = save_outputs(comfy, entry, "461", args.out)
    emit({"ok": True, "files": files, "seed": seed, "prompt_id": pid, "enhanced_prompt": enhanced_text(entry, "459:472") if args.enhance else None})


def enhanced_text(entry, node_id):
    t = entry.get("outputs", {}).get(node_id, {}).get("text")
    return t[0] if isinstance(t, list) and t else t


def cmd_edit(comfy, args):
    wf = load_wf("edit")
    seed = seed_of(args)
    wf["470"]["inputs"]["image"] = comfy.upload(args.image)
    if args.image2:
        wf["475"]["inputs"]["image"] = comfy.upload(args.image2)
    else:
        del wf["475"]
        del wf["459:474"]["inputs"]["images.image_2"]
        del wf["459:485"]["inputs"]["images.image1"]
    resolution = args.resolution
    if resolution is None:
        size = image_size(args.image)
        # keep the original size unless it is very large (VRAM)
        resolution = 0 if size and size[0] * size[1] <= 2_400_000 else 1536
    wf["459:474"]["inputs"]["resolution"] = resolution
    wf["459:500"]["inputs"]["prompt"] = args.prompt
    wf["459:484"]["inputs"].update(switch=not args.no_enhance, on_false=args.prompt)
    wf["459:474"]["inputs"]["negative_prompt"] = args.negative or ""
    wf["459:458"]["inputs"].update(seed=seed, steps=args.steps)
    pid = comfy.queue(wf)
    log(f"[comfy] 已提交 edit 任务 {pid}")
    entry = comfy.wait(pid, args.timeout)
    files = save_outputs(comfy, entry, "461", args.out)
    emit({"ok": True, "files": files, "seed": seed, "prompt_id": pid,
          "enhanced_prompt": None if args.no_enhance else enhanced_text(entry, "459:480")})


def cmd_describe(comfy, args):
    wf = load_wf("describe")
    wf["7"]["inputs"]["image"] = comfy.upload(args.image)
    n = wf["18"]["inputs"]
    if args.mode not in DESCRIBE_MODES:
        raise ComfyError(f"--mode 只能是 {', '.join(DESCRIBE_MODES)}")
    n["preset_prompt"] = DESCRIBE_MODES[args.mode]
    n["custom_prompt"] = args.ask or ""
    n["max_tokens"] = args.max_tokens
    n["seed"] = seed_of(args) % 4294967295 or 1
    pid = comfy.queue(wf)
    log(f"[comfy] 已提交 describe 任务 {pid}")
    entry = comfy.wait(pid, args.timeout)
    text = enhanced_text(entry, "13")
    if not text:
        raise ComfyError("没有拿到描述文字：" + json.dumps(entry.get("outputs", {}), ensure_ascii=False)[:800])
    emit({"ok": True, "text": text, "prompt_id": pid})


def cmd_layers(comfy, args):
    wf = load_wf("layers")
    wf["27"]["inputs"]["image"] = comfy.upload(args.image)
    seed = seed_of(args)
    wf["24"]["inputs"]["seed"] = seed
    wf["23"]["inputs"]["seed"] = seed
    pid = comfy.queue(wf)
    log(f"[comfy] 已提交 layers 任务 {pid}（拆图层比较慢，通常 1–4 分钟）")
    entry = comfy.wait(pid, args.timeout)
    finish_layers(comfy, entry, args.out_dir, pid)


def finish_layers(comfy, entry, out_dir, pid):
    """See-through writes <prefix>_<stamp>_layers.json + one cropped PNG per part on the
    server and reports only that json's path (via the PreviewAny node 30)."""
    info = enhanced_text(entry, "30")
    if not info:
        raise ComfyError("ComfyUI 没有返回图层信息：" + json.dumps(entry.get("outputs", {}), ensure_ascii=False)[:800])
    name = os.path.basename(info.strip().replace("\\", "/"))
    os.makedirs(out_dir, exist_ok=True)
    meta_path = comfy.download({"filename": name, "type": "output"}, os.path.join(out_dir, "layers.json"))
    with open(meta_path, encoding="utf-8") as f:
        meta = json.load(f)
    W, H = meta["width"], meta["height"]
    layers = sorted(meta["layers"], key=lambda l: -l.get("depth_median", 0))  # back -> front
    parts = []
    for i, l in enumerate(layers):
        fname = f"{i + 1:02d}_{l['name'].replace(' ', '_')}.png"
        comfy.download({"filename": l["filename"], "type": "output"}, os.path.join(out_dir, fname))
        parts.append({"file": fname, "name": l["name"], "left": l["left"], "top": l["top"]})
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump({"width": W, "height": H, "order": "back_to_front", "layers": parts}, f, ensure_ascii=False, indent=1)
    result = {"ok": True, "out_dir": out_dir.replace("\\", "/"), "canvas": [W, H], "layers": [p["file"] for p in parts],
              "note": "图层 PNG 是裁剪过的，left/top 偏移和前后顺序见 layers.json", "prompt_id": pid}
    result.update(assemble_layers(out_dir, W, H, parts))
    emit(result)


def assemble_layers(out_dir, W, H, parts):
    """Optional extras when Pillow (and psd-tools) are installed: full-canvas layers,
    a composite preview and a PSD. Without them the cropped PNGs + layers.json remain."""
    try:
        from PIL import Image
    except ImportError:
        return {"extras": "未安装 Pillow，只输出裁剪图层 + layers.json"}
    full_dir = os.path.join(out_dir, "full")
    os.makedirs(full_dir, exist_ok=True)
    comp = Image.new("RGBA", (W, H))
    imgs = []
    for p in parts:
        im = Image.open(os.path.join(out_dir, p["file"])).convert("RGBA")
        canvas = Image.new("RGBA", (W, H))
        canvas.paste(im, (p["left"], p["top"]))
        canvas.save(os.path.join(full_dir, p["file"]))
        comp.alpha_composite(canvas)
        imgs.append((p, im))
    comp_path = os.path.join(out_dir, "composite.png")
    comp.save(comp_path)
    extra = {"composite": comp_path.replace("\\", "/"), "full_canvas_dir": full_dir.replace("\\", "/")}
    try:
        from psd_tools import PSDImage
        from psd_tools.api.layers import PixelLayer
        psd = PSDImage.new("RGBA", (W, H))
        for p, im in imgs:
            psd.append(PixelLayer.frompil(im, psd, p["name"], top=p["top"], left=p["left"]))
        psd_path = os.path.join(out_dir, "layers.psd")
        psd.save(psd_path)
        extra["psd"] = psd_path.replace("\\", "/")
    except Exception:  # psd-tools missing or failed: PNGs are enough
        pass
    return extra


def cmd_wait(comfy, args):
    entry = comfy.wait(args.prompt_id, args.timeout)
    outputs = entry.get("outputs", {})
    if "30" in outputs or args.out_dir:
        if not args.out_dir:
            raise ComfyError("这是拆图层任务，请用 --out-dir 指定保存目录")
        return finish_layers(comfy, entry, args.out_dir, args.prompt_id)
    if "461" in outputs:
        if not args.out:
            raise ComfyError("请用 --out 指定保存路径")
        return emit({"ok": True, "files": save_outputs(comfy, entry, "461", args.out), "prompt_id": args.prompt_id})
    if "13" in outputs:
        return emit({"ok": True, "text": enhanced_text(entry, "13"), "prompt_id": args.prompt_id})
    raise ComfyError("无法识别这个任务的输出：" + json.dumps(outputs, ensure_ascii=False)[:800])


def main():
    if hasattr(sys.stdout, "reconfigure"):
        # Windows consoles default to a legacy code page; we print Chinese + emoji.
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default=os.environ.get("COMFYUI_URL") or DEFAULT_URL)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p, timeout=1500):
        p.add_argument("--seed", type=int)
        p.add_argument("--timeout", type=int, default=timeout, help="最长等待秒数")

    sub.add_parser("check")

    p = sub.add_parser("t2i", help="文生图（Qwen-Image 2.1）")
    p.add_argument("--prompt", required=True)
    p.add_argument("--negative")
    p.add_argument("--out", required=True, help="保存路径，如 outputs/cat.png")
    p.add_argument("--aspect", default="1:1", help="|".join(ASPECTS))
    p.add_argument("--mp", type=float, default=1.0, help="总像素（百万），1.0≈1024², 最高 4")
    p.add_argument("--steps", type=int, default=25)
    p.add_argument("--count", type=int, default=1, help="一次生成几张（1-4）")
    p.add_argument("--enhance", action="store_true", help="用 Qwen 提示词增强器改写提示词（提示词很短时有用）")
    common(p)

    p = sub.add_parser("edit", help="改图（Qwen-Image 2.1 Edit）")
    p.add_argument("--image", required=True)
    p.add_argument("--image2", help="第二张参考图（例如要换上的衣服/物件）")
    p.add_argument("--prompt", required=True, help="只描述要改什么，简短明确")
    p.add_argument("--negative")
    p.add_argument("--out", required=True)
    p.add_argument("--resolution", type=int, help="输出总像素预算（边长基准，如 1024/1536）；0=保持原图尺寸")
    p.add_argument("--steps", type=int, default=25)
    p.add_argument("--no-enhance", action="store_true", help="关闭编辑提示词增强器（默认开启）")
    common(p)

    p = sub.add_parser("describe", help="用 Qwen3-VL 描述图片")
    p.add_argument("--image", required=True)
    p.add_argument("--mode", default="ultra", help="|".join(DESCRIBE_MODES))
    p.add_argument("--ask", help="自定义提问（会替换预设指令）")
    p.add_argument("--max-tokens", type=int, default=1024)
    common(p, 600)

    p = sub.add_parser("layers", help="拆图层（See-through），输出分层 PNG（+ 有 Pillow/psd-tools 时的整图层和 PSD）")
    p.add_argument("--image", required=True)
    p.add_argument("--out-dir", required=True)
    common(p)

    p = sub.add_parser("wait", help="继续等待之前提交的任务并取回结果")
    p.add_argument("prompt_id")
    p.add_argument("--out")
    p.add_argument("--out-dir")
    p.add_argument("--timeout", type=int, default=1500)

    args = ap.parse_args()
    comfy = Comfy(args.url)
    try:
        {"check": cmd_check, "t2i": cmd_t2i, "edit": cmd_edit, "describe": cmd_describe,
         "layers": cmd_layers, "wait": cmd_wait}[args.cmd](comfy, args)
    except ComfyError as e:
        emit({"ok": False, "error": str(e)})
        sys.exit(1)
    except KeyboardInterrupt:
        emit({"ok": False, "error": "已中断"})
        sys.exit(130)


if __name__ == "__main__":
    main()
