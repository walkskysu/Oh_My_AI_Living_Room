"""Cut a polygon out of one PSD layer into a new layer (for parts that must move on their own bone).

usage: split_layer.py <psd> <src layer> <new layer> <below|above> x,y x,y x,y ...

Pixels of <src layer> inside the polygon (canvas px) move to <new layer>, which is inserted
just below (or above) <src layer> in draw order: e.g. a forearm goes below its sleeve layer
so the cuff hides the joint. Rewrites the PSD and the layers/<name>.png next to it.
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
i = [n for n, _ in layers].index(src)
a = np.array(layers[i][1]); b = np.zeros_like(a)
b[m] = a[m]; a[m] = 0
layers[i][1] = Image.fromarray(a)
layers.insert(i if where == 'below' else i + 1, [new, Image.fromarray(b)])

out = PSDImage.new('RGBA', (W, H))
d = os.path.join(os.path.dirname(path), 'layers')
for nm, im in layers:
    bb = im.getbbox()
    if not bb:
        continue
    out.append(PixelLayer.frompil(im.crop(bb), out, nm, top=bb[1], left=bb[0]))
    if nm in (src, new):
        im.save(f'{d}/{nm}.png')
out.save(path)
print(new, Image.fromarray(b).getbbox(), 'order:', [n for n, _ in layers])
