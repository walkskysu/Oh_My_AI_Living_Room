"""Find scale/offset mapping an original pose image onto the seethrough 1024 canvas (max alpha IoU)."""
import sys, numpy as np
from PIL import Image
def mask_of(im, white_bg):
    a = np.array(im.convert('RGBA')).astype(float)
    if not white_bg: return a[..., 3] > 128
    return (255 * 3 - a[..., :3].sum(-1)) > 40
def register(orig, comp, white_bg):
    cm = np.array(comp)[..., 3] > 128
    best = None
    for s in np.arange(0.70, 0.86, 0.005):
        w, h = round(orig.width * s), round(orig.height * s)
        om = mask_of(orig.resize((w, h)), white_bg)
        for dx in range(-60, 200, 4):
            for dy in range(-60, 60, 4):
                canvas = np.zeros_like(cm)
                x0, y0 = max(dx, 0), max(dy, 0); x1, y1 = min(dx + w, 1024), min(dy + h, 1024)
                if x1 <= x0 or y1 <= y0: continue
                canvas[y0:y1, x0:x1] = om[y0 - dy:y1 - dy, x0 - dx:x1 - dx]
                iou = (canvas & cm).sum() / (canvas | cm).sum()
                if best is None or iou > best[0]: best = (iou, s, dx, dy)
    # refine
    iou, s0, dx0, dy0 = best
    for s in np.arange(s0 - 0.006, s0 + 0.006, 0.001):
        w, h = round(orig.width * s), round(orig.height * s)
        om = mask_of(orig.resize((w, h)), white_bg)
        for dx in range(dx0 - 4, dx0 + 5):
            for dy in range(dy0 - 4, dy0 + 5):
                canvas = np.zeros_like(cm)
                x0, y0 = max(dx, 0), max(dy, 0); x1, y1 = min(dx + w, 1024), min(dy + h, 1024)
                canvas[y0:y1, x0:x1] = om[y0 - dy:y1 - dy, x0 - dx:x1 - dx]
                iou = (canvas & cm).sum() / (canvas | cm).sum()
                if iou > best[0]: best = (iou, s, dx, dy)
    return best
if __name__ == '__main__':
    o = Image.open(sys.argv[1]); c = Image.open(sys.argv[2])
    print(register(o, c, sys.argv[3] == 'white'))
