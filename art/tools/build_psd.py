"""Seethrough layers -> cleaned, recoloured, autorig-friendly PSD.

usage: build_psd.py <seethrough prefix> <original image> <alpha|white> <out dir> <name> [fill]

fill: painted pixels whose layer coverage is below this get filled (default 0.35;
0.95 also closes half-transparent seams inside the figure). A fill above 0.5 also
recolours layers under half-transparent edges of nearer layers (otherwise only where
they are mostly uncovered), which removes colour seams.
"""
import json, sys, glob, os
import numpy as np
from PIL import Image, ImageFilter
from psd_tools import PSDImage
from psd_tools.api.layers import PixelLayer

O = '/mnt/e/Comfy-Desktop/ComfyUI-Shared/output/'
prefix, orig_path, bgmode, out, name = sys.argv[1:6]
FILL = float(sys.argv[6]) if len(sys.argv) > 6 else 0.35
COVER = 0.995 if FILL > 0.5 else 0.5
m = json.load(open(sorted(glob.glob(O + prefix + '_*_layers.json'))[-1]))
W, H = m['width'], m['height']

RENAME = {
    'back hair': 'hair_back', 'front hair': 'hair_front', 'headwear': 'ribbon', 'face': 'face', 'ears': 'ear',
    'neck': 'neck', 'topwear': 'torso', 'handwear': 'arms', 'handwear-l': 'arm_l', 'handwear-r': 'arm_r',
    'objects': 'prop', 'legwear': 'skirt', 'bottomwear': 'skirt2', 'footwear': 'feet', 'nose': 'nose', 'mouth': 'mouth',
    'eyewhite-l': 'eyewhite_l', 'eyewhite-r': 'eyewhite_r', 'irides-l': 'iris_l', 'irides-r': 'iris_r',
    'eyelash-l': 'eyelash_l', 'eyelash-r': 'eyelash_r', 'eyebrow-l': 'brow_l', 'eyebrow-r': 'brow_r',
    'eyewear': 'glasses', 'earwear': 'earring',
}

# original scaled onto the canvas (fit + centre, as seethrough does)
orig = Image.open(orig_path).convert('RGBA')
s = min(W / orig.width, H / orig.height)
ow, oh = round(orig.width * s), round(orig.height * s)
canvas = Image.new('RGBA', (W, H), (255, 255, 255, 0))
canvas.paste(orig.resize((ow, oh), Image.LANCZOS), ((W - ow) // 2, (H - oh) // 2))
O_rgba = np.array(canvas).astype(np.float32)

layers = []
for l in sorted(m['layers'], key=lambda l: -l['depth_median']):  # far -> near
    im = Image.open(O + l['filename']).convert('RGBA')
    full = Image.new('RGBA', (W, H)); full.paste(im, (l['left'], l['top']))
    a = np.array(full).astype(np.float32)
    a[H - 14:, :, 3] = 0; a[:, W - 14:, 3] = 0   # seethrough leaves specks in the far corner
    if (a[..., 3] > 32).sum() < 60:
        continue
    layers.append([RENAME.get(l['name'], l['name'].replace(' ', '_').replace('-', '_')), a])

# SPLIT="prop:stool:520" moves the part of layer `prop` below canvas y=520 into a new
# layer `stool`, placed farthest back (e.g. furniture the character sits on, which must not
# ride the torso like hand-held props do).
for spec in filter(None, os.environ.get('SPLIT', '').split(',')):
    src_nm, new_nm, y0 = spec.split(':'); y0 = int(y0)
    for i, (nm, a) in enumerate(layers):
        if nm == src_nm:
            b = np.zeros_like(a); b[y0:] = a[y0:]; a[y0:, :, 3] = 0
            layers.insert(0, [new_nm, b])
            break

comp_a = np.zeros((H, W), np.float32)
for _, a in layers:
    comp_a = a[..., 3] / 255 + comp_a * (1 - a[..., 3] / 255)

if bgmode == 'alpha':
    orig_mask = O_rgba[..., 3] > 128
else:
    nonwhite = (765 - O_rgba[..., :3].sum(-1)) > 36
    near = np.array(Image.fromarray((comp_a > 0.25).astype(np.uint8) * 255).filter(ImageFilter.MaxFilter(13))) > 0
    orig_mask = nonwhite & near
    if os.environ.get('WHITE_INSIDE'):
        # white parts *inside* the figure (paper, socks) are painting too, not background:
        # recolour them as well, or layers keep See-through's guessed colours there
        inside = np.array(Image.fromarray((comp_a > 0.5).astype(np.uint8) * 255).filter(ImageFilter.MinFilter(9))) > 0
        orig_mask |= inside
    O_rgba[..., 3] = 255

# 1) recolour visible pixels of each layer from the original painting
covered = np.zeros((H, W), np.float32)  # opacity of nearer layers
for nm, a in reversed(layers):           # near -> far
    vis = (a[..., 3] > 8) & (covered < COVER) & orig_mask
    a[vis, :3] = O_rgba[vis, :3]
    covered = covered + (1 - covered) * a[..., 3] / 255

# 2) leftover painted pixels nobody covers -> layer that dominates the neighbourhood
left = orig_mask & (comp_a < FILL)
if left.any():
    scores = []
    for nm, a in layers:
        b = Image.fromarray(a[..., 3].astype(np.uint8)).filter(ImageFilter.GaussianBlur(14))
        bias = 0.6 if nm.startswith(('iris', 'eye', 'brow', 'nose', 'mouth')) else 1.0
        scores.append(np.array(b).astype(np.float32) * bias)
    owner = np.argmax(np.stack(scores), 0)
    for i, (nm, a) in enumerate(layers):
        sel = left & (owner == i)
        if sel.any():
            a[sel, :3] = O_rgba[sel, :3]; a[sel, 3] = 255
            print(f'  leftover {sel.sum():6d}px -> {nm}')

os.makedirs(f'{out}/layers', exist_ok=True)
psd = PSDImage.new('RGBA', (W, H))
comp = Image.new('RGBA', (W, H))
seen = {}
for nm, a in layers:
    if nm in seen:
        seen[nm] += 1; nm = f'{nm}{seen[nm]}'
    else:
        seen[nm] = 0
    im = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), 'RGBA')
    im.save(f'{out}/layers/{nm}.png')
    bb = im.getbbox()
    psd.append(PixelLayer.frompil(im.crop(bb), psd, nm, top=bb[1], left=bb[0]))
    comp.alpha_composite(im)
    print(f'{nm:12s} bbox={bb}')
psd.save(f'{out}/{name}.psd')
comp.save(f'{out}/{name}_composite.png')
print('saved', f'{out}/{name}.psd')
