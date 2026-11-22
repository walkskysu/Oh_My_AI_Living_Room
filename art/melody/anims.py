"""Rigby2D loops for Melody's poses (run with the rigby2d `run_script` tool).

Prepend `POSE = '<reading|bored|working|done>'` and run against
/mnt/e/rig_projects/melody/<pose>/<pose>.rigby. Animation names are the app's pose keys:
reading (idle: eyes closed, head sways to the beat of her headphones, the crossed foot taps),
bored (big yawn, the arm stretched above her head sways), working (the pencil hand writes notes
in the notebook while her eyes follow), done (waves with an open palm, smiling).

Bones come from autorig: shin_l = the crossed (top) leg's shin + sock, hand_r = the hand that
acts (stretched arm / pencil hand / waving hand), both cut out with art/tools/split_layer.py
(see build_layers.sh); ribbon (the headphones) rides an ear bone, so it stays on the head.
pivot_rotate() turns a bone about any canvas point (knee, wrist, shoulder): each rotate key
gets a translate key in the parent's frame that keeps the pivot in place.
Canvas px -> world: x - 512, 1024 - y.
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


def breathe(a, T, amount=0.012, n=1):
    pts = []
    for i in range(n):
        t0 = T * i / n
        pts += [(t0, (1, 1)), (t0 + T / n / 2, (1 + amount, 1 + amount * 0.4))]
    pts.append((T, (1, 1)))
    keys(a, 'chest', 'scale', pts)


def head_sway(a, pts, hair_lag=0.12, hair_amount=0.5):
    """Head rotation; the bob of short hair trails it a little."""
    keys(a, 'head', 'rotate', pts)
    T = pts[-1][0]
    keys(a, 'hair', 'rotate', [(min(T, t + hair_lag) if t > 0 else 0, -hair_amount * v) for t, v in pts])


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


def foot_taps(a, T, beats, up=2.2):
    """The crossed foot kicks up on each beat time (positive = toes up and out)."""
    pts = [(0, 0)]
    for t in beats:
        pts += [(t, 0), (t + 0.14, up), (t + 0.34, 0)]
    pts.append((T, 0))
    pivot_rotate(a, 'shin_l', KNEE, sorted(set(pts)))


KNEE = (585, 490)            # the crossed leg's knee
SHOULDER = (470, 330)        # bored: the arm stretched up
PEN_WRIST = (432, 452)       # working: the writing hand
WAVE_WRIST = (278, 338)      # done: the waving hand

if POSE == 'reading':        # 4s at 90 BPM: head sways side to side on the beat, foot taps along
    a = anim('reading'); T = 4.0; beat = T / 6
    breathe(a, T, 0.012, 2)
    head_sway(a, [(0, 0), (beat, 1.8), (2 * beat, -1.6), (3 * beat, 1.8), (4 * beat, -1.6), (5 * beat, 1.6), (T, 0)])
    keys(a, 'chest', 'rotate', [(0, 0), (beat * 1.2, 0.6), (beat * 2.2, -0.5), (beat * 3.2, 0.6), (beat * 4.2, -0.5), (beat * 5.2, 0.4), (T, 0)])
    foot_taps(a, T, [i * beat for i in range(6)])
    keys(a, 'mouth', 'scale', [(0, (1, 1)), (T / 2, (1.06, 1.1)), (T, (1, 1))])
elif POSE == 'bored':        # 4s: the stretched arm sways, a long yawn, head lolls; the foot swings slowly
    a = anim('bored'); T = 4.0
    breathe(a, T, 0.022, 1)
    keys(a, 'chest', 'rotate', [(0, 0), (1.6, 1.0), (2.8, -0.5), (T, 0)])
    head_sway(a, [(0, 0), (1.4, -2.5), (2.6, -1.0), (3.4, 0.6), (T, 0)])
    pivot_rotate(a, 'hand_r', SHOULDER, [(0, 0), (1.3, 3.5, (0, -3)), (2.5, -2.0, (0, -1)), (3.3, 1.0), (T, 0)])
    keys(a, 'mouth', 'scale', [(0, (1, 1)), (0.9, (1.06, 1.22)), (1.9, (1.06, 1.25)), (2.7, (0.92, 0.7)), (3.3, (0.96, 0.88)), (T, (1, 1))])
    pivot_rotate(a, 'shin_l', KNEE, [(0, 0), (1.0, 1.5), (2.0, 0), (3.0, 1.5), (T, 0)])
elif POSE == 'working':      # 3s: the pencil writes a short line of notes and lifts back; eyes follow
    a = anim('working'); T = 3.0
    keys(a, 'chest', 'scale', [(0, (1, 1)), (1.5, (1.008, 1.003)), (T, (1, 1))])
    head_sway(a, [(0, 0), (0.8, -1.0), (1.6, -0.4), (2.3, -1.2), (T, 0)])
    pupils(a, [(0, (0, 0)), (0.5, (1.0, 0.5)), (1.4, (2.2, 1.2)), (2.0, (1.5, 1.5)), (2.5, (0, 0.5)), (T, (0, 0))])
    pen = [(0, 0)]
    for i in range(6):                         # little scribbles drifting right along the staff
        t = 0.15 + i * 0.28
        pen += [(t, -1.4, (1.0 + i * 1.1, 0.8)), (t + 0.14, 0.6, (1.6 + i * 1.1, -0.4))]
    pen += [(2.2, 1.5, (5.5, -2.5)), (2.6, 0.5, (2.0, -1.0)), (T, 0)]   # lift and return to the line start
    pivot_rotate(a, 'hand_r', PEN_WRIST, pen)
    foot_taps(a, T, [0.0, 1.5], up=1.6)
    blink(a, 2.4, 0.16)
elif POSE == 'done':         # 2.4s: waves with the open palm, head tilted, chatty smile
    a = anim('done'); T = 2.4
    keys(a, 'chest', 'scale', [(0, (1, 1)), (0.6, (1.012, 1.004)), (1.2, (1, 1)), (1.8, (1.012, 1.004)), (T, (1, 1))])
    keys(a, 'chest', 'rotate', [(0, 0), (0.6, 0.6), (1.2, 0), (1.8, 0.6), (T, 0)])
    head_sway(a, [(0, 0), (0.6, 2.2), (1.2, 0.8), (1.8, 2.0), (T, 0)])
    pivot_rotate(a, 'hand_r', WAVE_WRIST, [(0, 0), (0.3, 9), (0.6, -6), (0.9, 9), (1.2, -6), (1.5, 8), (1.8, -4), (2.1, 4), (T, 0)])
    keys(a, 'mouth', 'scale', [(0, (1, 1)), (0.3, (1.05, 1.2)), (0.6, (0.98, 0.9)), (0.9, (1.05, 1.18)), (1.3, (1, 1)), (T, (1, 1))], 'linear')
    foot_taps(a, T, [0.0, 1.2], up=2.0)
    blink(a, 1.5, 0.15)
print([(x.name if hasattr(x, 'name') else x) for x in rigby.animations()])
