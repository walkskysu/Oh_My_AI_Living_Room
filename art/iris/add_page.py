"""Add a `page` layer to Iris's reading PSD: a thin curled sheet lying along the top edge of the
right-hand page block, hinged at the top of the spine (PIVOT). Rotated about PIVOT in
anims2.py it rises above the book and sweeps over to the left block (a page turn seen
from behind the cover). Drawn 4x supersampled; inserted just above the `prop` (book) layer.

usage: add_page.py <reading psd>
"""
import os, sys, math
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from psd_tools import PSDImage
from psd_tools.api.layers import PixelLayer

PIVOT = (582, 374)          # top of the spine, canvas px
TIP = (655, 327)              # outer top corner of the right page block
THICK = 16                  # sheet depth below its top edge (the part seen past the edge)
K = 4

def page_image(W, H):
    im = Image.new('RGBA', (W * K, H * K)); d = ImageDraw.Draw(im)
    (px, py), (tx, ty) = PIVOT, TIP
    L = math.hypot(tx - px, ty - py); ux, uy = (tx - px) / L, (ty - py) / L; nx, ny = -uy, ux   # n points down
    top, bot = [], []
    for i in range(41):
        s = i / 40
        curl = 7 * math.sin(math.pi * s) * (1 - 0.3 * s)       # page bows upward in the middle
        x, y = px + ux * L * s - nx * curl, py + uy * L * s - ny * curl
        top.append((x, y)); bot.append((x + nx * THICK * (1 - 0.55 * s), y + ny * THICK * (1 - 0.55 * s)))
    poly = [(x * K, y * K) for x, y in top + bot[::-1]]
    d.polygon(poly, fill=(246, 236, 216, 255))
    # soft shade toward the spine, then the outline
    sh = Image.new('L', im.size); ds = ImageDraw.Draw(sh)
    ds.polygon([(x * K, y * K) for x, y in top[:14] + bot[:14][::-1]], fill=70)
    sh = sh.filter(ImageFilter.GaussianBlur(8 * K))
    shade = Image.new('RGBA', im.size, (200, 170, 140, 255)); shade.putalpha(Image.fromarray(np.minimum(np.array(sh), np.array(im)[..., 3])))
    im.alpha_composite(shade)
    d = ImageDraw.Draw(im); d.line(poly + [poly[0]], fill=(150, 108, 92, 255), width=round(1.6 * K), joint='curve')
    return im.resize((W, H), Image.LANCZOS)

if __name__ == '__main__':
    path = sys.argv[1]
    psd = PSDImage.open(path); W, H = psd.width, psd.height
    layers = []
    for l in psd:
        if l.name == 'page': continue
        im = Image.new('RGBA', (W, H)); im.paste(l.topil().convert('RGBA'), (l.left, l.top)); layers.append((l.name, im))
    page = page_image(W, H)
    i = [n for n, _ in layers].index('prop'); layers.insert(i + 1, ('page', page))
    out = PSDImage.new('RGBA', (W, H))
    for nm, im in layers:
        bb = im.getbbox(); out.append(PixelLayer.frompil(im.crop(bb), out, nm, top=bb[1], left=bb[0]))
    out.save(path); page.save(os.path.join(os.path.dirname(path), 'layers', 'page.png'))
    print('page', page.getbbox(), [n for n, _ in layers])
