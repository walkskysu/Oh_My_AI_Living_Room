"""Build a Qwen-Image-2.1 edit workflow (single input image) for one Poppy pose.
usage: make_edit.py <input filename in ComfyUI/input> <pose> <prompt> <seed>"""
import json, sys, os
src, name, prompt, seed = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])
here = os.path.dirname(os.path.abspath(__file__))
w = json.load(open(f'{here}/workflows/image_edit_base.json'))
w['links'] = [l for l in w['links'] if l[0] != 728 and l[1] != 475 and l[3] != 475]
w['nodes'] = [n for n in w['nodes'] if n['id'] != 475]
for n in w['nodes']:
    if n['id'] == 459:
        for i in n['inputs']:
            if i['name'] == 'images.image_2': i['link'] = None
        n['widgets_values'][1] = prompt
        n['widgets_values'][13] = seed
        n['widgets_values'][2] = True   # prompt enhancer
        n['widgets_values'][3] = True
    if n['id'] == 470: n['widgets_values'][0] = src
    if n['id'] == 461: n['widgets_values'][0] = 'omalr_poppy_' + name
out = f'{here}/workflows/edit_{name}.json'
json.dump(w, open(out, 'w'), ensure_ascii=False)
print(out)
