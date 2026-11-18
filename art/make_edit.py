import json, sys, copy
src, name, prompt, seed = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])
w = json.load(open('workflows/image_qwen_image_2_1_image_edit.json'))
w['links'] = [l for l in w['links'] if l[0] != 728 and l[1] != 475 and l[3] != 475]
w['nodes'] = [n for n in w['nodes'] if n['id'] != 475]
for n in w['nodes']:
    if n['id'] == 459:
        for i in n['inputs']:
            if i['name'] == 'images.image_2': i['link'] = None
        n['widgets_values'][1] = prompt
        n['widgets_values'][13] = seed
        n['widgets_values'][2] = True
        n['widgets_values'][3] = True
    if n['id'] == 470: n['widgets_values'][0] = src
    if n['id'] == 461: n['widgets_values'][0] = 'omalr_' + name
json.dump(w, open(f'workflows/edit_{name}.json', 'w'), ensure_ascii=False)
print(f'workflows/edit_{name}.json')
