"""Rigby2D idle loops for Iris's four pose rigs (run with the rigby2d `run_script` tool).

Prepend `POSE = '<reading|bored|working|done>'` and run against
/mnt/e/rig_projects/iris/<pose>/<pose>.rigby. Bone directions (from sample_pose):
eye bones point screen-right (blink = scale y), brows are children of the head
(local +x = up), hip translate is in root space (+y = up).
"""
import rigby
EIO = 'ease_in_out'
NAMES = {b.name for b in rigby.bones()}

def anim(name):
    for a in rigby.animations():
        if (a.name if hasattr(a, 'name') else a) == name:
            break
    else:
        rigby.add_animation(name)
    return rigby.animation(name)

def keys(a, bone, ch, pts, curve=EIO):
    if bone not in NAMES:
        return
    for t, v in pts:
        a.key(bone, ch, t, v, curve)

def blink(a, t, d=0.18, low=0.1):
    for eye in ('eye_r', 'eye_l'):
        keys(a, eye, 'scale', [(t, (1, 1)), (t + d / 2, (1, low)), (t + d, (1, 1))], 'linear')
    for brow in ('brow_r', 'brow_l'):
        keys(a, brow, 'translate', [(t, (0, 0)), (t + d / 2, (-2.5, 0)), (t + d, (0, 0))], 'linear')

def head_and_hair(a, pts, sway=()):
    """Head rotation; long hair counter-rotates so it stays behind the body, plus optional sway."""
    keys(a, 'head', 'rotate', pts)
    sway = dict(sway)
    keys(a, 'hair', 'rotate', [(t, -0.8 * v + sway.get(t, 0)) for t, v in pts])

def breathe(a, T, amount=0.012, n=1):
    pts = []
    for i in range(n):
        t0 = T * i / n
        pts += [(t0, (1, 1)), (t0 + T / n / 2, (1 + amount, 1 + amount * 0.4))]
    pts.append((T, (1, 1)))
    keys(a, 'chest', 'scale', pts)

if POSE == 'reading':          # 6s: breathing, slow reading nods, two blinks
    a = anim('reading'); T = 6.0
    breathe(a, T, 0.012, 2)
    keys(a, 'chest', 'rotate', [(0, 0), (T / 2, 0.5), (T, 0)])
    head_and_hair(a, [(0, 0), (1.5, -1.6), (3.0, -0.6), (4.5, -1.8), (T, 0)], [(1.5, 0.6), (4.5, -0.5)])
    blink(a, 2.9); blink(a, 5.85, 0.15)
elif POSE == 'bored':          # 6s: deep yawn breath, head tilt (small: hand stays at mouth), sleepy blink
    a = anim('bored'); T = 6.0
    keys(a, 'chest', 'scale', [(0, (1, 1)), (1.8, (1.022, 1.008)), (2.6, (1.022, 1.008)), (T, (1, 1))])
    keys(a, 'chest', 'rotate', [(0, 0), (1.5, -1.2), (3.0, 0.3), (4.5, 1.0), (T, 0)])
    head_and_hair(a, [(0, 0), (1.6, 2.4), (3.0, 3.0), (4.6, -1.2), (T, 0)], [(1.6, 1.0), (4.6, -1.0)])
    keys(a, 'mouth', 'scale', [(0, (1, 1)), (1.4, (1.12, 1.12)), (2.6, (1.12, 1.12)), (3.4, (1, 1)), (T, (1, 1))])
    for eye in ('eye_r', 'eye_l'):
        keys(a, eye, 'scale', [(0, (1, 1)), (3.6, (1, 1)), (3.85, (1, 0.15)), (4.3, (1, 1)), (T, (1, 1))])
elif POSE == 'working':        # 3s: quick focused nods while writing
    a = anim('working'); T = 3.0
    keys(a, 'chest', 'scale', [(0, (1, 1)), (1.5, (1.008, 1.003)), (T, (1, 1))])
    keys(a, 'chest', 'rotate', [(0, 0), (0.75, -0.5), (1.5, 0), (2.25, -0.5), (T, 0)])
    head_and_hair(a, [(0, 0), (0.4, -1.3), (0.8, -0.3), (1.2, -1.5), (1.6, -0.2), (2.1, -1.2), (2.6, -0.4), (T, 0)])
    blink(a, 1.85, 0.16)
elif POSE == 'done':           # 2s: happy hop, head sway, waving V-sign
    a = anim('done'); T = 2.0
    keys(a, 'hip', 'translate', [(0, (0, 0)), (0.25, (0, 6)), (0.5, (0, 0)), (0.75, (0, 4)), (1.0, (0, 0)), (T, (0, 0))])
    keys(a, 'chest', 'scale', [(0, (1, 1)), (0.25, (1.012, 1)), (0.5, (1, 1)), (0.75, (1.008, 1)), (1.0, (1, 1)), (T, (1, 1))])
    head_and_hair(a, [(0, 0), (0.5, 3.0), (1.0, 0), (1.5, -2.5), (T, 0)], [(0.5, -1.2), (1.5, 1.2)])
    keys(a, 'upperarm_r', 'rotate', [(0, 0), (0.5, 2.0), (1.0, 0), (1.5, -2.0), (T, 0)])
    keys(a, 'forearm_r', 'rotate', [(0, 0), (0.25, 6), (0.5, 0), (0.75, 6), (1.0, 0), (1.25, -4), (1.5, 0), (1.75, -4), (T, 0)])
    keys(a, 'mouth', 'scale', [(0, (1, 1)), (0.5, (1.06, 1.08)), (1.0, (1, 1)), (1.5, (1.06, 1.08)), (T, (1, 1))])
print([(x.name if hasattr(x, 'name') else x) for x in rigby.animations()])
