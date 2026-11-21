"""Build a See-through layer-split workflow for one Claire pose.
usage: make_st.py <input filename in ComfyUI/input> <pose>"""
import json, sys, os
src, name = sys.argv[1], sys.argv[2]
here = os.path.dirname(os.path.abspath(__file__))
w = json.load(open(f'{here}/workflows/st_base.json'))
for n in w['nodes']:
    if n['id'] == 27: n['widgets_values'][0] = src
    if n['id'] == 21: n['widgets_values'][0] = 'omalr_claire_' + name
out = f'{here}/workflows/st_{name}.json'
json.dump(w, open(out, 'w'), ensure_ascii=False)
print(out)
