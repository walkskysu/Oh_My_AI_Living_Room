"""Rigby2D loops for Poppy's action poses (run with the rigby2d `run_script` tool).

Prepend `POSE = '<mix|turn|wave>'` and run against /mnt/e/rig_projects/poppy/<pose>/<pose>.rigby.
These rigs have a `forearm_r` bone (elbow at the sleeve cuff; the forearm layer sits under the
sleeve so the cuff hides the joint) and, in `mix`/`turn`, a `hand_r` bone carrying the brush.
Animation names are the app's pose keys: mix -> reading (idle, mixing paint on the palette),
turn -> working (head turned to the easel, brush moving on the canvas), wave -> done (hand up, talking).
"""
import math
import rigby
EIO = 'ease_in_out'
NAMES = {b.name for b in rigby.bones()}

def anim(name):
    for a in rigby.animations():
        if (a.name if hasattr(a, 'name') else a) == name:
            rigby.delete_animation(name) if hasattr(rigby, 'delete_animation') else None
            break
    if name not in [(a.name if hasattr(a, 'name') else a) for a in rigby.animations()]:
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

def head(a, pts, lag=0.25, amount=0.5):
    keys(a, 'head', 'rotate', pts)
    T = pts[-1][0]
    sway = [(0, 0)] + [(min(t + lag, T - 0.01), -amount * v) for t, v in pts[1:-1]] + [(T, 0)]
    keys(a, 'hair', 'rotate', sway)

def breathe(a, T, amount=0.012, n=1):
    pts = []
    for i in range(n):
        t0 = T * i / n
        pts += [(t0, (1, 1)), (t0 + T / n / 2, (1 + amount, 1 + amount * 0.4))]
    pts.append((T, (1, 1)))
    keys(a, 'chest', 'scale', pts)

def loops(t0, n, period, r, steps=8):
    """Translate keys tracing n small circles of radius r (a swirl of the brush)."""
    pts = []
    for i in range(n * steps):
        ang = 2 * math.pi * i / steps
        pts.append((t0 + period * i / steps, (r * math.sin(ang), r * (1 - math.cos(ang)) * 0.8)))
    return pts

def talk(a, T, opens):
    """Mouth flaps: `opens` = [(t, openness 0..1)], closed = squashed open-mouth layer."""
    keys(a, 'mouth', 'scale', [(t, (0.85 + 0.15 * o, 0.35 + 0.65 * o)) for t, o in opens] + [(T, (1, 1))], 'linear')

if POSE == 'mix':              # 4.8s: swirl paint on the palette, lift the brush, look, mix again
    a = anim('reading'); T = 4.8
    breathe(a, T, 0.012, 2)
    keys(a, 'chest', 'rotate', [(0, 0), (1.2, 0.6), (2.4, 0), (3.4, 0.8), (T, 0)])
    head(a, [(0, 0), (1.2, 1.4), (2.4, 0.2), (3.2, 2.4), (4.0, 2.0), (T, 0)])
    sw = loops(0, 3, 0.8, 6)                       # three brisk swirls
    keys(a, 'forearm_r', 'translate', sw + [(2.4, (0, 0)), (3.0, (0, 0)), (3.8, (0, 0)), (T, (0, 0))], 'linear')
    keys(a, 'forearm_r', 'rotate', [(0, 0), (0.4, 2), (0.8, 0), (1.2, 2), (1.6, 0), (2.0, 2), (2.4, 0),
                                    (2.9, -9), (3.5, -9.5), (4.2, -1), (T, 0)])   # lift the brush and back down
    keys(a, 'hand_r', 'rotate', [(0, 0), (0.2, 4), (0.6, -4), (1.0, 4), (1.4, -4), (1.8, 4), (2.2, -4), (2.4, 0),
                                 (2.9, 6), (3.5, 5), (4.2, 0), (T, 0)])
    blink(a, 1.5); blink(a, 3.9, 0.15)
elif POSE == 'turn':           # 3.6s: facing the easel, brush strokes up and down the canvas
    a = anim('working'); T = 3.6
    breathe(a, T, 0.008, 2)
    keys(a, 'chest', 'rotate', [(0, 0), (0.45, 0.8), (0.9, 0), (1.35, 0.8), (1.8, 0), (2.25, 1.0), (2.7, 0), (3.15, 0.6), (T, 0)])
    head(a, [(0, 0), (0.9, 1.0), (1.8, -0.4), (2.7, 1.2), (T, 0)], 0.2, 0.4)
    # strokes: the forearm sweeps the brush up/down; the wrist flicks into each stroke
    keys(a, 'forearm_r', 'rotate', [(0, 0), (0.45, 7), (0.9, -2), (1.35, 6), (1.8, -1), (2.25, 8), (2.7, -3), (3.15, 4), (T, 0)])
    keys(a, 'forearm_r', 'translate', [(0, (0, 0)), (0.9, (3, 5)), (1.8, (0, 0)), (2.7, (-3, -5)), (T, (0, 0))])
    keys(a, 'hand_r', 'rotate', [(0, 0), (0.3, -6), (0.6, 5), (0.9, 0), (1.2, -6), (1.5, 5), (1.8, 0),
                                 (2.1, -7), (2.4, 5), (2.7, 0), (3.0, -5), (3.3, 4), (T, 0)])
    blink(a, 2.0, 0.16)
elif POSE == 'wave':           # 2.4s: waving hand, chatting happily
    a = anim('done'); T = 2.4
    keys(a, 'chest', 'scale', [(0, (1, 1)), (0.6, (1.015, 1.004)), (1.2, (1, 1)), (1.8, (1.015, 1.004)), (T, (1, 1))])
    keys(a, 'chest', 'rotate', [(0, 0), (0.6, 1.0), (1.2, 0), (1.8, -0.8), (T, 0)])
    head(a, [(0, 0), (0.6, 2.4), (1.2, 0.4), (1.8, -1.6), (T, 0)], 0.15, 0.6)
    w = [(0, 0)] + [(0.3 * i, (9 if i % 2 else -7)) for i in range(1, 8)] + [(T, 0)]
    keys(a, 'forearm_r', 'rotate', w)
    talk(a, T, [(0, 1), (0.14, 0.2), (0.28, 0.9), (0.4, 0.3), (0.55, 1), (0.7, 0.1), (0.95, 0.8),
                (1.1, 0.3), (1.25, 1), (1.4, 0.2), (1.62, 0.9), (1.8, 0.4), (1.95, 1), (2.1, 0.2), (2.25, 0.7)])
    blink(a, 1.45, 0.15)
print([(x.name if hasattr(x, 'name') else x) for x in rigby.animations()])
