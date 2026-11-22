"""Melody's source art: cut her off the dark glow background and add headroom.

1. ComfyUI `workflows/rmbg.json` (BiRefNet) on images/Melody.png (uploaded as
   omalr_melody_src.png); save its mask preview as src/_mask.png.
2. python make_alpha.py  ->  src/omalr_melody_alpha.png (transparent) and
   src/omalr_melody_white.png (white background), 1024x1632.

The mask is hardened so the glow halo does not survive as a grey fringe, and 96px are added on
top: the yawning pose stretches an arm above her head, and every pose must share one frame
(edited poses are matched to it with align.py, by the legs).
"""
import numpy as np
from PIL import Image

PAD = 96
src = Image.open('../../images/Melody.png').convert('RGB')
m = Image.open('src/_mask.png').convert('L').resize(src.size)
a = np.clip((np.asarray(m).astype(float) / 255 - 0.35) / 0.4, 0, 1)
alpha = Image.fromarray((a * 255).astype(np.uint8))


def pad(im, bg):
    c = Image.new(im.mode, (src.width, src.height + PAD), bg)
    c.paste(im, (0, PAD))
    return c


rgba = src.copy(); rgba.putalpha(alpha)
pad(rgba, (255, 255, 255, 0)).save('src/omalr_melody_alpha.png')
white = Image.new('RGB', src.size, 'white'); white.paste(src, mask=alpha)
pad(white, 'white').save('src/omalr_melody_white.png')
print('saved', 'src/omalr_melody_alpha.png', 'src/omalr_melody_white.png')
