"""Cut a polygon out of one PSD layer into a new layer (for parts that must move on their own bone).

usage: split_layer.py <psd> <src layer>[,<src layer>...] <new layer> <below|above> x,y x,y x,y ...

Pixels of the source layer(s) inside the polygon (canvas px) move to <new layer> (several
sources are stacked in draw order, e.g. a hand and the pen it holds), which is inserted
just below (or above) the first source layer in draw order: e.g. a forearm goes below its sleeve layer
so the cuff hides the joint. If <new layer> exists, the pixels are added to it.
Options (env): KEEP=skin only moves skin-toned / dark pixels (a hand and the pen it holds,
not the clothes around it); FILL=<layer> inpaints that layer under the cut (diffusion from
its own neighbouring pixels) so nothing shows through when the part moves; REST=<layer>
moves the sources' other (not kept) pixels inside the polygon onto that layer (e.g. the top
around a hand, so the sleeve layer above the hand holds nothing but the sleeve); PAD=<px>
grows the new layer by that many px where the first source still covers it (a wrist that
reaches on under the cuff, so no gap opens when the hand moves).
Rewrites the PSD and the layers/<name>.png next to it.
"""
import os, sys
import numpy as np
from PIL import Image, ImageDraw
from psd_tools import PSDImage
from psd_tools.api.layers import PixelLayer

path, src, new, where = sys.argv[1:5]
poly = [tuple(map(float, p.split(','))) for p in sys.argv[5:]]
psd = PSDImage.open(path)
W, H = psd.width, psd.height
layers = []
for l in psd:
    im = Image.new('RGBA', (W, H)); im.paste(l.topil().convert('RGBA'), (l.left, l.top))
    layers.append([l.name, im])

mask = Image.new('L', (W, H)); ImageDraw.Draw(mask).polygon(poly, fill=255)
m = np.array(mask) > 0
KEEP, FILL, REST = os.environ.get('KEEP'), os.environ.get('FILL'), os.environ.get('REST')

def keep_mask(a):
    if KEEP != 'skin':
        return m
    r, g, bl = (a[..., k].astype(int) for k in range(3))
    mx = np.maximum(np.maximum(r, g), bl); mn = np.minimum(np.minimum(r, g), bl)
    skin = (r - bl > 30) & (g - bl >= 5)
    dark = mx < 90
    grey = (mx - mn < 18) & (mx < 170)          # highlights on a dark pen / tool
    return m & (skin | dark | grey)

def inpaint(img, hole, iters=400):
    """Fill `hole` pixels from the layer's own opaque neighbours (repeated 4-neighbour averaging)."""
    a = np.array(img).astype(float)
    known = (a[..., 3] > 200) & ~hole
    col = np.where(known[..., None], a, 0.0); w = known.astype(float)
    for _ in range(iters):
        sc = sum(np.roll(col, sh, ax) for sh in (1, -1) for ax in (0, 1))
        sw = sum(np.roll(w, sh, ax) for sh in (1, -1) for ax in (0, 1))
        upd = hole & (sw > 0)
        col[upd] = sc[upd] / sw[upd, None]; w[upd] = 1
    out = np.array(img).copy(); f = hole & (w > 0)
    out[f] = np.clip(col[f], 0, 255).astype(np.uint8); out[f, 3] = 255
    return Image.fromarray(out)
srcs = src.split(',')
cut = np.zeros((H, W), bool)
names = [n for n, _ in layers]
b = Image.new('RGBA', (W, H))
for j in sorted(names.index(s_) for s_ in srcs):
    a = np.array(layers[j][1]); part = np.zeros_like(a); km = keep_mask(a)
    part[km] = a[km]; a[km] = 0
    if REST and srcs[0] != REST and layers[j][0] != REST:
        rest = np.zeros_like(a); rm = m & (a[..., 3] > 0); rest[rm] = a[rm]; a[rm] = 0
        k = names.index(REST); t = Image.fromarray(rest); t.alpha_composite(layers[k][1]); layers[k][1] = t
    layers[j][1] = Image.fromarray(a); b.alpha_composite(Image.fromarray(part)); cut |= part[..., 3] > 0
b = np.array(b)
PAD = int(os.environ.get('PAD', 0))
if PAD:
    cover = np.array(layers[names.index(srcs[0])][1])[..., 3] > 200
    nb = b.copy()
    for _ in range(PAD):
        grown = nb.copy(); empty = nb[..., 3] == 0
        for ax, sh in ((0, 1), (0, -1), (1, 1), (1, -1)):
            r = np.roll(nb, sh, ax); take = empty & (r[..., 3] > 200) & cover & (grown[..., 3] == 0)
            grown[take] = r[take]
        nb = grown
    b = nb
if FILL:
    k = [n for n, _ in layers].index(FILL)
    hole = cut.copy()
    for _ in range(3):                       # grow a little past the cut edge
        hole |= np.roll(hole, 1, 0) | np.roll(hole, -1, 0) | np.roll(hole, 1, 1) | np.roll(hole, -1, 1)
    hole &= np.array(layers[k][1])[..., 3] < 250
    bb = np.argwhere(cut); (y0, x0), (y1, x1) = bb.min(0), bb.max(0)
    near = np.zeros_like(hole); near[max(0, y0 - 40):y1 + 40, max(0, x0 - 40):x1 + 40] = True
    layers[k][1] = inpaint(layers[k][1], (hole | cut) & near)
if new in names:          # already split: add these pixels to it (where is ignored)
    k = names.index(new); merged = layers[k][1].copy(); merged.alpha_composite(Image.fromarray(b))
    layers[k][1] = merged; b = np.array(merged)
else:
    i = names.index(srcs[0])
    layers.insert(i if where == 'below' else i + 1, [new, Image.fromarray(b)])

out = PSDImage.new('RGBA', (W, H))
d = os.path.join(os.path.dirname(path), 'layers')
for nm, im in layers:
    bb = im.getbbox()
    if not bb:
        continue
    out.append(PixelLayer.frompil(im.crop(bb), out, nm, top=bb[1], left=bb[0]))
    if nm in srcs + [new, FILL, REST]:
        im.save(f'{d}/{nm}.png')
out.save(path)
print(new, Image.fromarray(b).getbbox(), 'order:', [n for n, _ in layers])
