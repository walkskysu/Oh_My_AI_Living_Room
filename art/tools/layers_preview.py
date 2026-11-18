"""Composite seethrough layers (far→near by depth) and write a contact sheet."""
import json, sys, glob, os
from PIL import Image, ImageDraw
O = '/mnt/e/Comfy-Desktop/ComfyUI-Shared/output/'
prefix, out = sys.argv[1], sys.argv[2]
m = json.load(open(sorted(glob.glob(O + prefix + '_*_layers.json'))[-1]))
W, H = m['width'], m['height']
layers = sorted(m['layers'], key=lambda l: -l['depth_median'])
comp = Image.new('RGBA', (W, H))
tiles = []
for l in layers:
    im = Image.open(O + l['filename']).convert('RGBA')
    full = Image.new('RGBA', (W, H)); full.paste(im, (l['left'], l['top']))
    comp.alpha_composite(full)
    t = Image.new('RGBA', (W, H), (235, 235, 240, 255)); t.alpha_composite(full)
    t = t.resize((256, 256)); ImageDraw.Draw(t).text((4, 4), l['name'], fill=(200, 0, 0))
    tiles.append(t)
os.makedirs(out, exist_ok=True)
comp.save(f'{out}/{prefix}_composite.png')
cols = 6; rows = (len(tiles) + cols - 1) // cols
sheet = Image.new('RGB', (cols * 256, rows * 256), 'white')
for i, t in enumerate(tiles): sheet.paste(t.convert('RGB'), ((i % cols) * 256, (i // cols) * 256))
sheet.save(f'{out}/{prefix}_sheet.png')
bg = Image.new('RGBA', (W, H), (255, 255, 255, 255)); bg.alpha_composite(comp); bg.convert('RGB').resize((512, 512)).save(f'{out}/{prefix}_comp_small.png')
print(len(layers), 'layers', W, H)
