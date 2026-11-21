"""Rigby2D loops for Iris's hand-action poses (run with the rigby2d `run_script` tool).

Prepend `POSE = '<read|write|wave>'` and run against /mnt/e/rig_projects/iris/<dir>/<pose>.rigby
(reading2/read, working2/write, done2/wave). Animation names are the app's pose keys:
read -> reading (idle: eyes follow the lines, then a page turns), write -> working (the pen
hand keeps writing), wave -> done (open hand waving, talking).

The extra bones come from autorig on the split layers: `page` (art/iris/add_page.py) -> hand_l,
pen hand -> hand_r; in `wave` the open hand is cut out of arm_r into hand_r (the sleeve stays on the chest). Autorig places those
bones where it likes, so pivot_rotate() turns a bone about any canvas point instead: each
rotate key gets a translate key (in the parent's frame) that keeps the pivot in place.
Canvas px -> world: x - 512, 1024 - y (skeleton origin at the bottom centre, Y up).
"""
import math
import rigby
EIO = 'ease_in_out'
NAMES = {b.name for b in rigby.bones()}

def anim(name):
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

def pivot_rotate(a, bone, pivot, pts, curve=EIO):
    """Rotate `bone` about canvas point `pivot`: pts = [(t, degrees) or (t, degrees, (dx, dy))],
    dx/dy an extra world offset (screen px, y down) added on top."""
    if bone not in NAMES:
        return
    b = rigby.bone(bone); w = b.world; pw = b.parent.world
    px, py = pivot[0] - 512, 1024 - pivot[1]
    vx, vy = px - w['x'], py - w['y']
    phi = math.radians(pw['rotation'])
    for p in pts:
        t, deg = p[0], p[1]; ex, ey = p[2] if len(p) > 2 else (0, 0)
        c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
        dx = vx - (c * vx - s * vy) + ex          # world offset that keeps the pivot still
        dy = vy - (s * vx + c * vy) - ey
        lx = (math.cos(-phi) * dx - math.sin(-phi) * dy) / pw['scale_x']
        ly = (math.sin(-phi) * dx + math.cos(-phi) * dy) / pw['scale_y']
        a.key(bone, 'rotate', t, deg, curve)
        a.key(bone, 'translate', t, (lx, ly), curve)

def pupils(a, pts, curve=EIO):
    """Both irises look by (dx, dy) screen px (eye bones point screen-right)."""
    for p in ('pupil_r', 'pupil_l'):
        keys(a, p, 'translate', [(t, (dx, -dy)) for t, (dx, dy) in pts], curve)

def talk(a, T, opens):
    """Mouth flaps: `opens` = [(t, openness 0..1)] on the open-mouth layer."""
    keys(a, 'mouth', 'scale', [(t, (0.85 + 0.15 * o, 0.35 + 0.65 * o)) for t, o in opens] + [(T, (1, 1))], 'linear')

PAGE_PIVOT = (582, 374)        # top of the spine (art/iris/add_page.py)
WRIST = (440, 520)             # pen hand, under the sleeve cuff
WAVE_WRIST = (212, 338)        # raised open hand, inside the cardigan cuff

if POSE == 'read':             # 6s: eyes run along two lines, a small nod per line, then a page turns
    a = anim('reading'); T = 6.0
    breathe(a, T, 0.012, 2)
    keys(a, 'chest', 'rotate', [(0, 0), (T / 2, 0.5), (T, 0)])
    head_and_hair(a, [(0, 0), (1.4, -1.0), (1.6, -0.4), (3.0, -1.4), (3.3, -0.6), (4.2, 0.8), (5.0, 0.4), (T, 0)],
                  [(1.4, 0.4), (3.0, 0.5), (4.2, -0.5)])
    # read a line left -> right, flick back to the next line; follow the page across while it turns
    pupils(a, [(0, (-2.5, 0)), (1.4, (2.5, 0.6)), (1.6, (-2.5, 1.2)), (3.0, (2.5, 1.8)), (3.3, (1.5, 0.5)),
               (3.7, (2.5, -0.5)), (4.4, (-2.0, -0.8)), (5.0, (-2.5, 0)), (T, (-2.5, 0))])
    pivot_rotate(a, 'hand_l', PAGE_PIVOT, [(0, 0), (3.5, 0), (4.0, 70), (4.55, 136), (T, 136)])
    blink(a, 2.1, 0.16); blink(a, 5.4, 0.15)
elif POSE == 'write':          # 3s: the pen keeps writing — small wrist strokes travelling along the line
    a = anim('working'); T = 3.0
    keys(a, 'chest', 'scale', [(0, (1, 1)), (1.5, (1.008, 1.003)), (T, (1, 1))])
    keys(a, 'chest', 'rotate', [(0, 0), (0.75, -0.5), (1.5, 0), (2.25, -0.5), (T, 0)])
    head_and_hair(a, [(0, 0), (0.6, -1.0), (1.3, -0.4), (2.0, -1.2), (2.5, -0.3), (T, 0)])
    pupils(a, [(0, (-1.0, 0)), (2.4, (1.5, 0.3)), (2.7, (-1.0, 0)), (T, (-1.0, 0))])
    pts = []
    n = 20                                   # strokes over 2.5s while the hand drifts right
    for i in range(n + 1):
        t = 2.5 * i / n
        drift = 3.5 * i / n
        pts.append((t, (1.6 if i % 2 else -1.4), (drift, 0.6 * drift / 3.5)))
    pts += [(2.75, 1.0, (1.2, -0.4)), (T, -1.4, (0, 0))]   # carriage return to the next line
    pivot_rotate(a, 'hand_r', WRIST, pts, 'linear')
    blink(a, 1.85, 0.16)
elif POSE == 'wave':           # 2.4s: open hand waving from the wrist, chatting happily
    a = anim('done'); T = 2.4
    keys(a, 'chest', 'scale', [(0, (1, 1)), (0.6, (1.012, 1.004)), (1.2, (1, 1)), (1.8, (1.012, 1.004)), (T, (1, 1))])
    keys(a, 'chest', 'rotate', [(0, 0), (0.6, 0.8), (1.2, 0), (1.8, -0.6), (T, 0)])
    head_and_hair(a, [(0, 0), (0.6, 2.4), (1.2, 0.4), (1.8, -1.8), (T, 0)], [(0.6, -1.0), (1.8, 1.0)])
    w = [(0, 0)] + [(0.3 * i, (12 if i % 2 else -10)) for i in range(1, 8)] + [(T, 0)]
    pivot_rotate(a, 'hand_r', WAVE_WRIST, w)
    talk(a, T, [(0, 1), (0.14, 0.2), (0.28, 0.9), (0.4, 0.3), (0.55, 1), (0.7, 0.1), (0.95, 0.8),
                (1.1, 0.3), (1.25, 1), (1.4, 0.2), (1.62, 0.9), (1.8, 0.4), (1.95, 1), (2.1, 0.2), (2.25, 0.7)])
    blink(a, 1.45, 0.15)
print([(x.name if hasattr(x, 'name') else x) for x in rigby.animations()])
