"""Rigby2D idle loops for Poppy's four pose rigs (run with the rigby2d `run_script` tool).

Prepend `POSE = '<reading|bored|working|done>'` and run against
/mnt/e/rig_projects/poppy/<pose>/<pose>.rigby. Same bone conventions as Iris
(art/rig/anims.py), except Poppy's bob is a child of the head: it follows the
head and only gets a small lagging sway of its own. Arms and hand-held props ride the chest; the stool is unrigged (root), so the hip never moves.
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

def head(a, pts, lag=0.25, amount=0.5):
    """Head rotation; the bob follows and swings back a little, slightly delayed."""
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

if POSE == 'reading':          # 6s idle at the easel: breathing, cheerful head bob, two blinks
    a = anim('reading'); T = 6.0
    breathe(a, T, 0.012, 2)
    keys(a, 'chest', 'rotate', [(0, 0), (1.5, 0.8), (3.0, 0), (4.5, 0.6), (T, 0)])
    head(a, [(0, 0), (1.5, 2.2), (3.0, 0.4), (4.5, 2.6), (T, 0)])
    blink(a, 2.2); blink(a, 5.3, 0.15)
elif POSE == 'bored':          # 6s: deep yawn breath, slight droopy tilt, mouth opens wider
    a = anim('bored'); T = 6.0
    keys(a, 'chest', 'scale', [(0, (1, 1)), (1.8, (1.022, 1.008)), (2.6, (1.022, 1.008)), (T, (1, 1))])
    keys(a, 'chest', 'rotate', [(0, 0), (1.5, -1.0), (3.0, 0.3), (4.5, 0.8), (T, 0)])
    # small: the hand covering her mouth rides the chest, not the head
    head(a, [(0, 0), (1.6, -1.0), (3.0, -1.3), (4.6, 0.5), (T, 0)], 0.3, 1.2)
    keys(a, 'mouth', 'scale', [(0, (1, 1)), (1.4, (1.12, 1.15)), (2.6, (1.12, 1.15)), (3.4, (1, 1)), (T, (1, 1))])
elif POSE == 'working':        # 3s: brisk little dabs — chest rocks toward the canvas, focused nods
    a = anim('working'); T = 3.0
    keys(a, 'chest', 'scale', [(0, (1, 1)), (1.5, (1.008, 1.003)), (T, (1, 1))])
    keys(a, 'chest', 'rotate', [(0, 0), (0.35, 1.2), (0.75, 0), (1.1, 1.0), (1.5, 0), (1.9, 1.4), (2.3, 0.2), (T, 0)])
    head(a, [(0, 0), (0.4, 1.6), (0.8, 0.4), (1.2, 1.8), (1.6, 0.2), (2.1, 1.4), (2.6, 0.4), (T, 0)], 0.15, 0.4)
    blink(a, 1.85, 0.16)
elif POSE == 'done':           # 2s: happy bounce, showing the painting off with a sway
    a = anim('done'); T = 2.0
    # seated on a static stool: the hip stays put, the bounce lives in the chest
    keys(a, 'chest', 'scale', [(0, (1, 1)), (0.25, (1.025, 1.006)), (0.5, (1, 1)), (0.75, (1.018, 1.004)), (1.0, (1, 1)), (T, (1, 1))])
    keys(a, 'chest', 'rotate', [(0, 0), (0.5, 1.6), (1.0, 0), (1.5, -1.4), (T, 0)])
    head(a, [(0, 0), (0.5, 3.0), (1.0, 0), (1.5, -2.5), (T, 0)], 0.15, 0.6)
    keys(a, 'mouth', 'scale', [(0, (1, 1)), (0.5, (1.06, 1.08)), (1.0, (1, 1)), (1.5, (1.06, 1.08)), (T, (1, 1))])
print([(x.name if hasattr(x, 'name') else x) for x in rigby.animations()])
