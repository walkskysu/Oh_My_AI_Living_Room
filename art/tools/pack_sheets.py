"""Repack Rigby2D sprite-sheet exports into one WebP grid per pose, aligned to the
canonical pose frame (seethrough canvas crop CROP) via each frame's pivot (= skeleton origin).

Output JSON is TexturePacker-hash compatible: spriteSourceSize gives each cell's offset
inside sourceSize (the canonical frame), so all poses line up exactly.
"""
import json, os, sys
from PIL import Image

CHAR = os.environ.get('CHAR', 'iris')    # CHAR=poppy python pack_sheets.py reading bored ...
SRC = f'/mnt/e/rig_projects/{CHAR}/sheets'
DST = f'/home/walksky/workspace/Oh_My_AI_Living_Room/public/characters/{CHAR}/anim'
S = 0.6                      # export scale (pixels per canvas px)
# canonical frame in seethrough canvas px (per character: covers every pose)
CROP = {'iris': (96, 8, 904, 1016), 'poppy': (150, 4, 874, 1020), 'claire': (170, 0, 854, 1024),
        'melody': (186, 0, 838, 1024)}[CHAR]
ORIGIN = (512, 1024)         # skeleton origin in canvas px (autorig: bottom centre)
CW, CH = round((CROP[2] - CROP[0]) * S), round((CROP[3] - CROP[1]) * S)
R = 0.75                     # final downscale of every cell (keeps decoded sheets small)
import math

def load_frames(name):
    top = json.load(open(f'{SRC}/{name}.json'))
    pages = []
    if 'textures' in top:
        for t in top['textures']:
            pages.append((t['image'], {f['filename']: f for f in t['frames']}))
    else:
        pages.append((top['meta']['image'], top['frames']))
    frames = []
    for image, fr in pages:
        img = Image.open(f'{SRC}/{image}').convert('RGBA')
        for key, f in fr.items():
            r = f['frame']
            crop = img.crop((r['x'], r['y'], r['x'] + r['w'], r['y'] + r['h']))
            src_w, src_h = f['sourceSize']['w'], f['sourceSize']['h']
            # top-left of the untrimmed source frame, in canonical-frame pixels
            ox = ORIGIN[0] * S - f['pivot']['x'] * src_w - CROP[0] * S
            oy = ORIGIN[1] * S - f['pivot']['y'] * src_h - CROP[1] * S
            x = round(ox + f['spriteSourceSize']['x']); y = round(oy + f['spriteSourceSize']['y'])
            frames.append((key, crop, x, y, f.get('duration', 83)))
    frames.sort(key=lambda t: t[0])
    return frames

def pack(name, quality=88):
    frames = load_frames(name)
    # union box of all frames in canonical coords (clamped to the canonical frame)
    x0 = max(0, min(f[2] for f in frames)); y0 = max(0, min(f[3] for f in frames))
    x1 = min(CW, max(f[2] + f[1].width for f in frames)); y1 = min(CH, max(f[3] + f[1].height for f in frames))
    cw, ch = x1 - x0, y1 - y0
    rw, rh = round(cw * R), round(ch * R)
    cols = max(1, math.ceil(math.sqrt(len(frames) * rh / rw)))
    rows = (len(frames) + cols - 1) // cols
    sheet = Image.new('RGBA', (cols * rw, rows * rh))
    out = []
    for i, (key, im, x, y, dur) in enumerate(frames):
        cx, cy = (i % cols) * rw, (i // cols) * rh
        cell = Image.new('RGBA', (cw, ch)); cell.paste(im, (x - x0, y - y0), im)
        sheet.paste(cell.resize((rw, rh), Image.LANCZOS), (cx, cy))
        out.append({'filename': key, 'frame': {'x': cx, 'y': cy, 'w': rw, 'h': rh},
                    'spriteSourceSize': {'x': round(x0 * R), 'y': round(y0 * R), 'w': rw, 'h': rh},
                    'sourceSize': {'w': round(CW * R), 'h': round(CH * R)}, 'duration': dur})
    os.makedirs(DST, exist_ok=True)
    sheet.save(f'{DST}/{name}.webp', 'WEBP', quality=quality, method=6, alpha_quality=90)
    json.dump({'frames': out, 'meta': {'image': f'{name}.webp', 'size': {'w': sheet.width, 'h': sheet.height},
                                       'source': 'rigby2d', 'scale': S}}, open(f'{DST}/{name}.json', 'w'))
    # first frame as a still for previews / hit-testing
    still = Image.new('RGBA', (round(CW * R), round(CH * R))); still.alpha_composite(sheet.crop((0, 0, rw, rh)), (round(x0 * R), round(y0 * R)))
    print(f'{name}: {len(frames)} frames, cell {cw}x{ch}, sheet {sheet.size}, '
          f'{os.path.getsize(f"{DST}/{name}.webp") // 1024} KB')
    return still

if __name__ == '__main__':
    for n in sys.argv[1:]:
        pack(n).save(f'{DST}/../poses/{n}.png', optimize=True)
