"""Rigby2D loops for Claire's poses (run with the rigby2d `run_script` tool).

Prepend `POSE = '<reading|bored|working|done>'` and run against
/mnt/e/rig_projects/claire/<pose>/<pose>.rigby. Animation names are the app's pose keys:
reading (idle: eyes run over the report, the hand holding it tilts it toward her),
bored (arm stretched up, yawning, swaying), working (finger taps / swipes on the tablet
while her eyes follow the chart), done (thumbs-up that bobs, with a nod).

Bones come from autorig: hand_r = the hand that acts (paper hand / pointing finger /
thumbs-up), cut into its own layer with art/tools/split_layer.py. pivot_rotate() turns a
bone about any canvas point (wrist): each rotate key gets a translate key in the parent's
frame that keeps the pivot in place. Canvas px -> world: x - 512, 1024 - y.
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
    """Head rotation; the long hair counter-rotates so it stays behind the body, plus optional sway."""
    keys(a, 'head', 'rotate', pts)
    sway = dict(sway)
    for h in ('hair', 'hair1'):        # autorig names a one-piece hair 'hair', a chain hair1/hair2
        keys(a, h, 'rotate', [(t, -0.8 * v + sway.get(t, 0)) for t, v in pts])
    keys(a, 'hair2', 'rotate', [(t, 0.6 * sway.get(t, 0)) for t, v in pts])

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
        dx = vx - (c * vx - s * vy) + ex
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
    keys(a, 'mouth', 'scale', [(t, (0.85 + 0.15 * o, 0.35 + 0.65 * o)) for t, o in opens] + [(T, (1, 1))], 'linear')

PAPER_WRIST = (540, 528)       # reading: the hand holding the report
SHOULDER = (370, 215)          # bored: the arm stretched up
POINT_WRIST = (505, 482)       # working: the pointing hand
THUMB_ELBOW = (530, 482)       # done: the thumbs-up forearm

if POSE == 'reading':          # 6s: reads the report line by line, tilts it toward her, small nods
    a = anim('reading'); T = 6.0
    breathe(a, T, 0.012, 2)
    keys(a, 'chest', 'rotate', [(0, 0), (T / 2, 0.6), (T, 0)])
    head_and_hair(a, [(0, 0), (1.2, -1.2), (1.5, -0.4), (2.8, -1.6), (3.2, -0.6), (4.4, 1.0), (5.2, 0.5), (T, 0)],
                  [(1.2, 0.5), (2.8, 0.6), (4.4, -0.6)])
    pupils(a, [(0, (-1.5, -0.5)), (1.2, (2.0, 0.2)), (1.45, (-1.5, 0.8)), (2.8, (2.0, 1.4)), (3.2, (0.5, 2.0)),
               (4.4, (1.5, 2.4)), (5.0, (-1.0, 0)), (T, (-1.5, -0.5))])
    pivot_rotate(a, 'hand_r', PAPER_WRIST, [(0, 0), (1.5, 1.5, (0, -1)), (3.0, 3.0, (-0.5, -1)), (4.2, 3.5, (-0.5, -1.5)),
                                            (5.2, 1.0, (0, -0.5)), (T, 0)])
    blink(a, 2.0, 0.16); blink(a, 5.5, 0.15)
elif POSE == 'bored':          # 4s: stretched arm sways, a long yawn, leaning a little
    a = anim('bored'); T = 4.0
    breathe(a, T, 0.02, 1)
    keys(a, 'chest', 'rotate', [(0, 0), (1.6, -1.2), (2.8, 0.6), (T, 0)])
    head_and_hair(a, [(0, 0), (1.4, 2.5), (2.6, 1.0), (3.4, -0.5), (T, 0)], [(1.4, -0.8), (2.6, 0.6)])
    pivot_rotate(a, 'hand_r', SHOULDER, [(0, 0), (1.4, 4.5, (0, -3)), (2.6, -2.0, (0, -1)), (3.4, 1.0), (T, 0)])
    keys(a, 'mouth', 'scale', [(0, (1, 1)), (0.8, (1.08, 1.3)), (1.8, (1.08, 1.35)), (2.6, (0.9, 0.55)), (3.3, (0.95, 0.8)), (T, (1, 1))])
elif POSE == 'working':        # 3s: taps the tablet twice, then swipes the chart; eyes follow the finger
    a = anim('working'); T = 3.0
    keys(a, 'chest', 'scale', [(0, (1, 1)), (1.5, (1.008, 1.003)), (T, (1, 1))])
    head_and_hair(a, [(0, 0), (0.5, -0.8), (1.6, -0.3), (2.3, -1.0), (T, 0)])
    pupils(a, [(0, (0, 0)), (0.4, (1.5, 0.5)), (1.4, (2.5, 1.0)), (2.2, (1.0, 1.5)), (T, (0, 0))])
    pivot_rotate(a, 'hand_r', POINT_WRIST, [
        (0, 0), (0.25, -2.0, (3, 1)), (0.4, 0), (0.65, -2.0, (3, 1)), (0.8, 0),          # tap tap
        (1.2, -1.5, (3, 1)), (1.9, 1.5, (7, 4)), (2.2, 1.0, (5, 3)), (2.6, 0.5, (1, 1)), (T, 0)])  # swipe
    blink(a, 2.45, 0.15)
elif POSE == 'done':           # 2.4s: the thumbs-up bobs, a confident smile and nod
    a = anim('done'); T = 2.4
    keys(a, 'chest', 'scale', [(0, (1, 1)), (0.6, (1.012, 1.004)), (1.2, (1, 1)), (1.8, (1.012, 1.004)), (T, (1, 1))])
    keys(a, 'chest', 'rotate', [(0, 0), (0.6, 0.6), (1.2, 0), (1.8, -0.5), (T, 0)])
    head_and_hair(a, [(0, 0), (0.6, 2.0), (1.2, 0.4), (1.8, -1.5), (T, 0)], [(0.6, -0.8), (1.8, 0.8)])
    pivot_rotate(a, 'hand_r', THUMB_ELBOW, [(0, 0), (0.3, 5, (0, -4)), (0.6, -1), (0.9, 4, (0, -3)), (1.2, 0),
                                            (1.6, 3, (0, -2)), (2.0, -1), (T, 0)])
    blink(a, 1.45, 0.15)
print([(x.name if hasattr(x, 'name') else x) for x in rigby.animations()])
