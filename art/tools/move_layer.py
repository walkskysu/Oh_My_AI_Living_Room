"""Move a PSD layer in the draw order: move_layer.py <psd> <layer> <below|above> <other layer>; drops empty layers."""
import sys
from PIL import Image
from psd_tools import PSDImage
from psd_tools.api.layers import PixelLayer
path, name, where, other = sys.argv[1:5]
psd = PSDImage.open(path)
ls = [(l.name, l.topil().convert('RGBA'), l.left, l.top) for l in psd if l.topil() is not None and l.topil().getbbox()]
item = next(x for x in ls if x[0] == name)
ls.remove(item)
i = next(k for k, x in enumerate(ls) if x[0] == other)
ls.insert(i if where == 'below' else i + 1, item)
out = PSDImage.new('RGBA', (psd.width, psd.height))
for nm, im, left, top in ls:
    out.append(PixelLayer.frompil(im, out, nm, top=top, left=left))
out.save(path)
print([x[0] for x in ls])
