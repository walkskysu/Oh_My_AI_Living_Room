"""Contact strip of a packed pose sheet: preview.py <pose> <out.png> [zoom box x0,y0,x1,y1 in cell px]"""
import json, sys
from PIL import Image
d = '/home/walksky/workspace/Oh_My_AI_Living_Room/public/characters/claire/anim/'
pose, out = sys.argv[1], sys.argv[2]
box = tuple(map(int, sys.argv[3].split(','))) if len(sys.argv) > 3 else None
j = json.load(open(d + pose + '.json')); s = Image.open(d + pose + '.webp')
fr = j['frames']; pick = [fr[round(i * (len(fr) - 1) / 5)] for i in range(6)]
cells = []
for f in pick:
    r = f['frame']; o = f['spriteSourceSize']
    c = Image.new('RGBA', (f['sourceSize']['w'], f['sourceSize']['h']), 'white')
    c.alpha_composite(s.crop((r['x'], r['y'], r['x'] + r['w'], r['y'] + r['h'])), (o['x'], o['y']))
    if box: c = c.crop(box).resize(((box[2] - box[0]) * 2, (box[3] - box[1]) * 2))
    cells.append(c)
strip = Image.new('RGBA', (sum(c.width for c in cells), cells[0].height), 'white')
x = 0
for c in cells: strip.alpha_composite(c, (x, 0)); x += c.width
strip.save(out)
