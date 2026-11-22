"""Align an edited pose onto the original Melody frame by matching the legs (the part that never moves).
usage: align.py <edited png> <out png>   (searches scale + offset that maximise leg-mask IoU, white bg)"""
import sys, numpy as np
from PIL import Image
ref = Image.open('src/omalr_melody_white.png').convert('RGB')
W, H = ref.size
def mask(im):
    a = np.asarray(im.convert('RGB')).astype(np.int32)
    return (765 - a.sum(-1)) > 60
LEG_Y = int(H * 0.62)                       # below the lap: legs and shoes
rm = mask(ref)[LEG_Y:]
src = Image.open(sys.argv[1]).convert('RGB')
def place(s, dx, dy, im=src, size=None):
    w, h = round(im.width * s), round(im.height * s)
    c = Image.new('RGB', (W, H), 'white'); c.paste(im.resize((w, h), Image.LANCZOS if size else Image.BILINEAR), (dx, dy))
    return c
small = 4
ss = src.resize((src.width // small, src.height // small))
r = mask(ref.resize((W // small, H // small)))[LEG_Y // small:]
def score(s, dx, dy):
    w, h = round(ss.width * s), round(ss.height * s)
    c = Image.new('RGB', (W // small, H // small), 'white'); c.paste(ss.resize((w, h)), (dx // small, dy // small))
    m = mask(c)[LEG_Y // small:]
    return (m & r).sum() / max(1, (m | r).sum())
best = (0, 1, 0, 0)
for s in np.arange(0.90, 1.35, 0.02):
    for dx in range(-240, 241, 16):
        for dy in range(-300, 301, 16):
            v = score(s, dx, dy)
            if v > best[0]: best = (v, s, dx, dy)
_, s0, x0, y0 = best
for s in np.arange(s0 - 0.02, s0 + 0.021, 0.005):
    for dx in range(x0 - 16, x0 + 17, 4):
        for dy in range(y0 - 16, y0 + 17, 4):
            v = score(s, dx, dy)
            if v > best[0]: best = (v, s, dx, dy)
print(sys.argv[1], 'iou %.3f scale %.3f dx %d dy %d' % best)
place(best[1], best[2], best[3], size=True).save(sys.argv[2])
