"""The language the model writes and the chip runs: a small subset of Python for a 128x64 mono OLED.

    clear()                     blank the screen
    text(x, y, s)               s at column x, row y (6x8 pixel characters: 21 per line, 8 lines)
    pixel(x, y)                 one dot
    line(x0, y0, x1, y1)        a line
    rect(x, y, w, h)            an outline
    fill(x, y, w, h)            a filled rectangle
    circle(x, y, r)             a circle outline
    wait(ms)                    show what is drawn and pause; the end of the program shows it too

Hardware (the board maps each to a pin in its firmware, so a program never names a pin):

    led(v)                      the LED on (1) or off (0)
    rgb(r, g, b)                the colour LED, 0-255 each
    beep(ms)                    the buzzer for ms (it waits that long)
    button()                    1 while the button is held, else 0
    knob()                      the knob's position, 0-100

A car (four Mecanum wheels, a head on a servo with a distance sensor, two line sensors):

    move(f, s, r)               forward, sideways (right +), turn (right +), each -100..100; keeps going
    stop()                      all wheels stop
    look(a)                     the head turns to a degrees, -90 (left) .. 90 (right)
    distance()                  cm to whatever the head looks at
    track()                     line sensors under the car: 0 no line, 1 left, 2 right, 3 both
    tilt()                      degrees the car leans, 0 = flat (accelerometer)
    shaken()                    1 if it was bumped or shaken since the last call, else 0
    temp()                      degrees Celsius, humidity() percent

The robot on that car (eyes on the 8x8 NeoPixel, a passive buzzer for its voice, a microphone, a second servo that
tilts the head, a third for an arm, a distance sensor at the back):

    eyes(s)                     one of EYES: "open", "happy", "sad", "angry", "sleepy", "closed", "wink", "heart",
                                "left", "right", "up", "down", "surprised", "dizzy"; anything else is refused
    tone(hz, ms)                the passive buzzer at hz (0 is a rest) for ms (it waits that long)
    nod(a)                      the head tilts to a degrees, -45 (down) .. 45 (up)
    arm(a)                      the arm to a degrees, 0 (down) .. 180 (straight up)
    sound()                     how loud it is around the robot, 0-100 (a clap is a short jump)
    behind()                    cm to whatever is behind the car

A program that reacts runs `while 1:` with a wait() inside, until the next request stops it; the step budget
counts from the last wait, so a loop that never waits is still stopped.

Plus whole numbers and strings, variables, + - * // %, comparisons, and/or/not, str(), abs(), min(), max(),
`for i in range(...)`, `while`, `if/elif/else`. Nothing else parses: no imports, no attributes, no functions of
its own, no lists. Coordinates outside the screen are clipped, and the run stops after MAX_STEPS steps or
MAX_WAIT_MS of waiting, so whatever the model writes, the chip stays in charge.

This module is the reference interpreter: it checks a program, runs it and records the frames, which is how the
corpus is verified and how the model is scored (same pictures = same program, whatever the spelling).
"""
import ast

W, H = 128, 64
CW, CH = 6, 8
MAX_STEPS = 20_000
MAX_WAIT_MS = 30_000
MAX_STR = 127          # characters in one string (the chip keeps each variable in a fixed buffer)
MAX_VARS = 24
DRAW = {"clear": 0, "text": 3, "pixel": 2, "line": 4, "rect": 4, "fill": 4, "circle": 3, "wait": 1,
        "led": 1, "rgb": 3, "beep": 1, "move": 3, "stop": 0, "look": 1, "eyes": 1, "tone": 2, "nod": 1, "arm": 1}
SENSE = {"button": 0, "knob": 0, "distance": 0, "track": 0, "tilt": 0, "shaken": 0, "temp": 0, "humidity": 0,
         "sound": 0, "behind": 0}
EYES = ["open", "happy", "sad", "angry", "sleepy", "closed", "wink", "heart", "left", "right", "up", "down",
        "surprised", "dizzy"]
# led, r, g, b, buzzer, forward, sideways, turn, head angle, eyes (index in EYES), tone hz, head tilt, arm
IO0 = (0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
PURE = {"str": str, "abs": abs, "min": min, "max": max}


class LangError(Exception):
    pass


class Screen:
    def __init__(self, inputs=None, horizon=None):
        self.px = bytearray(W * H)
        self.frames = []          # (ms since start, bytes) at every wait and at the end
        self.t = 0
        self.texts = []           # (x, y, s) drawn since the last clear, for checks that read the words
        self.io = IO0               # led, r, g, b, buzzer, forward, sideways, turn, head, eyes, tone, nod, arm
        self.io_log = [(0, self.io)]  # (ms, io state) whenever it changes
        self.inputs = inputs or Inputs()
        self.horizon = horizon    # None: a program must end; else the run is cut here, as a new request would

    def set_io(self, io):
        if io != self.io:
            self.io = io
            if self.io_log and self.io_log[-1][0] == self.t:
                self.io_log[-1] = (self.t, io)
            else:
                self.io_log.append((self.t, io))

    def led(self, v):
        self.set_io((1 if v else 0,) + self.io[1:])

    def rgb(self, r, g, b):
        c = lambda v: max(0, min(255, v))
        self.set_io((self.io[0], c(r), c(g), c(b)) + self.io[4:])

    def beep(self, ms):
        self.set_io(self.io[:4] + (1,) + self.io[5:])
        self.wait(ms)
        self.set_io(self.io[:4] + (0,) + self.io[5:])

    def move(self, f, s, r):
        c = lambda v: max(-100, min(100, v))
        self.set_io(self.io[:5] + (c(f), c(s), c(r)) + self.io[8:])

    def stop(self):
        self.set_io(self.io[:5] + (0, 0, 0) + self.io[8:])

    def look(self, a):
        self.set_io(self.io[:8] + (max(-90, min(90, a)),) + self.io[9:])

    def eyes(self, s):
        if not isinstance(s, str):
            raise LangError("eyes takes a mood")
        if s not in EYES:
            raise LangError(f"unknown eyes {s!r}")
        self.set_io(self.io[:9] + (EYES.index(s),) + self.io[10:])

    def tone(self, hz, ms):
        self.set_io(self.io[:10] + (max(0, min(5000, hz)),) + self.io[11:])
        self.wait(ms)
        self.set_io(self.io[:10] + (0,) + self.io[11:])

    def nod(self, a):
        self.set_io(self.io[:11] + (max(-45, min(45, a)),) + self.io[12:])

    def arm(self, a):
        self.set_io(self.io[:12] + (max(0, min(180, a)),))

    def set(self, x, y):
        if 0 <= x < W and 0 <= y < H:
            self.px[y * W + x] = 1

    def clear(self):
        self.px = bytearray(W * H)
        self.texts = []

    def text(self, x, y, s):
        s = str(s)
        self.texts.append((x, y, s))
        for i, ch in enumerate(s):
            if ch != " ":
                for dx in range(CW - 1):          # a block per character: the interpreter does not
                    for dy in range(CH - 1):      # need glyphs to compare two programs' pictures
                        if (dx + dy) % 2 == 0:
                            self.set(x + i * CW + dx, y + dy)

    def pixel(self, x, y):
        self.set(x, y)

    def line(self, x0, y0, x1, y1):
        dx, dy = abs(x1 - x0), -abs(y1 - y0)
        sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
        err = dx + dy
        for _ in range(W + H + 2):
            self.set(x0, y0)
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 >= dy:
                err += dy; x0 += sx
            if e2 <= dx:
                err += dx; y0 += sy

    def rect(self, x, y, w, h):
        if w <= 0 or h <= 0:
            return
        self.line(x, y, x + w - 1, y); self.line(x, y + h - 1, x + w - 1, y + h - 1)
        self.line(x, y, x, y + h - 1); self.line(x + w - 1, y, x + w - 1, y + h - 1)

    def fill(self, x, y, w, h):
        for yy in range(max(0, y), min(H, y + h)):
            for xx in range(max(0, x), min(W, x + w)):
                self.px[yy * W + xx] = 1

    def circle(self, cx, cy, r):
        x, y, err = r, 0, 1 - r
        while x >= y:
            for a, b in ((x, y), (y, x), (-y, x), (-x, y), (-x, -y), (-y, -x), (y, -x), (x, -y)):
                self.set(cx + a, cy + b)
            y += 1
            if err < 0:
                err += 2 * y + 1
            else:
                x -= 1; err += 2 * (y - x) + 1

    def wait(self, ms):
        self.frames.append((self.t, bytes(self.px)))
        self.t += max(0, int(ms))
        self.waited = True
        if self.horizon is not None and self.t >= self.horizon:
            raise _Stop
        if self.t > MAX_WAIT_MS:
            raise LangError("waits too long")


class Inputs:
    """What the button and the knob do over time, for a simulated run: button pressed during the given
    (start, end) ms intervals; knob a list of (ms, value) points, held between them."""
    def __init__(self, presses=(), knob=((0, 50),), distance=((0, 200),), line=((0, 0),), tilt=((0, 0),),
                 shakes=(), temp=((0, 22),), humidity=((0, 45),), sound=((0, 0),), behind=((0, 200),)):
        self.presses, self.knob_pts = list(presses), sorted(knob)
        self.dist_pts, self.line_pts, self.tilt_pts = sorted(distance), sorted(line), sorted(tilt)
        self.shakes, self.temp_pts, self.hum_pts = sorted(shakes), sorted(temp), sorted(humidity)
        self.sound_pts, self.behind_pts = sorted(sound), sorted(behind)
        self.shake_seen = -1

    def button(self, t):
        return int(any(a <= t < b for a, b in self.presses))

    @staticmethod
    def _held(pts, t):
        v = pts[0][1]
        for tt, vv in pts:
            if tt <= t:
                v = vv
        return v

    def knob(self, t):
        return self._held(self.knob_pts, t)

    def distance(self, t):
        return self._held(self.dist_pts, t)

    def track(self, t):
        return self._held(self.line_pts, t)

    def tilt(self, t):
        return self._held(self.tilt_pts, t)

    def temp(self, t):
        return self._held(self.temp_pts, t)

    def humidity(self, t):
        return self._held(self.hum_pts, t)

    def sound(self, t):
        return self._held(self.sound_pts, t)

    def behind(self, t):
        return self._held(self.behind_pts, t)

    def shaken(self, t):
        """1 once per bump: a bump at time b is reported by the first call at or after b."""
        for b in self.shakes:
            if self.shake_seen < b <= t:
                self.shake_seen = b
                return 1
        return 0


class _Stop(Exception):
    pass


ALLOWED = (ast.Module, ast.Expr, ast.Assign, ast.AugAssign, ast.For, ast.While, ast.If, ast.Call, ast.Name,
           ast.Constant, ast.BinOp, ast.UnaryOp, ast.Compare, ast.BoolOp, ast.Load, ast.Store, ast.Add, ast.Sub,
           ast.Mult, ast.FloorDiv, ast.Mod, ast.USub, ast.Not, ast.And, ast.Or, ast.Eq, ast.NotEq, ast.Lt,
           ast.LtE, ast.Gt, ast.GtE, ast.Pass, ast.Break, ast.Continue)


def check(src):
    """Parse and refuse anything outside the language. Returns the tree."""
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        raise LangError(f"syntax: {e.msg}")
    for node in ast.walk(tree):
        if not isinstance(node, ALLOWED):
            raise LangError(f"not in the language: {type(node).__name__}")
        if isinstance(node, ast.Constant) and not isinstance(node.value, (int, str)) or \
                isinstance(node, ast.Constant) and isinstance(node.value, bool):
            raise LangError("only whole numbers and strings")
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.keywords:
                raise LangError("calls are name(args)")
            f = node.func.id
            if f == "range":
                if not 1 <= len(node.args) <= 3:
                    raise LangError("range takes 1 to 3 numbers")
            elif f in DRAW:
                if len(node.args) != DRAW[f]:
                    raise LangError(f"{f} takes {DRAW[f]} arguments")
            elif f in SENSE:
                if node.args:
                    raise LangError(f"{f} takes no arguments")
            elif f not in PURE:
                raise LangError(f"unknown function {f}")
        if isinstance(node, ast.For):
            if not (isinstance(node.target, ast.Name) and isinstance(node.iter, ast.Call)
                    and isinstance(node.iter.func, ast.Name) and node.iter.func.id == "range") or node.orelse:
                raise LangError("for only as: for i in range(...)")
        if isinstance(node, (ast.Assign,)) and (len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name)):
            raise LangError("assign to names only")
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and (len(node.value) > MAX_STR or "\\" in node.value):
            raise LangError("string too long" if len(node.value) > MAX_STR else "no escapes in strings")
    return tree


class _Break(Exception): pass
class _Continue(Exception): pass


class Machine:
    def __init__(self, inputs=None, horizon=None):
        self.screen, self.vars, self.steps = Screen(inputs, horizon), {}, 0
        self.screen.waited = False

    def setvar(self, name, v):
        if name not in self.vars and len(self.vars) >= MAX_VARS:
            raise LangError("too many variables")
        if isinstance(v, bool):
            v = int(v)                  # the chip has no booleans: a comparison is 1 or 0
        self.vars[name] = v

    def tick(self):
        if self.screen.waited and self.screen.horizon is not None:
            self.steps, self.screen.waited = 0, False   # a reacting program: the budget runs from the last wait
        self.steps += 1
        if self.steps > MAX_STEPS:
            raise LangError("too many steps")

    def ev(self, n):
        self.tick()
        if isinstance(n, ast.Constant):
            return n.value
        if isinstance(n, ast.Name):
            if n.id not in self.vars:
                raise LangError(f"unknown name {n.id}")
            return self.vars[n.id]
        if isinstance(n, ast.BinOp):
            a, b = self.ev(n.left), self.ev(n.right)
            try:
                if isinstance(n.op, ast.Add):
                    r = a + b
                    if isinstance(r, str) and len(r) > MAX_STR: raise LangError("string too long")
                    return r
                if isinstance(n.op, ast.Sub): return a - b
                if isinstance(n.op, ast.Mult):
                    r = a * b
                    if isinstance(r, str) and len(r) > MAX_STR: raise LangError("string too long")
                    return r
                if isinstance(n.op, ast.FloorDiv): return a // b
                if isinstance(n.op, ast.Mod): return a % b
            except (TypeError, ZeroDivisionError) as e:
                raise LangError(str(e))
        if isinstance(n, ast.UnaryOp):
            v = self.ev(n.operand)
            if isinstance(n.op, ast.USub):
                if isinstance(v, str):
                    raise LangError("bad operand for unary -")
                return -v
            return int(not v)
        if isinstance(n, ast.BoolOp):
            vals = n.values
            if isinstance(n.op, ast.And):
                r = True
                for v in vals:
                    r = self.ev(v)
                    if not r: return r
                return r
            r = False
            for v in vals:
                r = self.ev(v)
                if r: return r
            return r
        if isinstance(n, ast.Compare):
            left = self.ev(n.left)
            for op, right in zip(n.ops, n.comparators):
                r = self.ev(right)
                ok = {ast.Eq: left == r, ast.NotEq: left != r}.get(type(op))
                if ok is None:
                    try:
                        ok = {ast.Lt: left < r, ast.LtE: left <= r, ast.Gt: left > r, ast.GtE: left >= r}[type(op)]
                    except TypeError as e:
                        raise LangError(str(e))
                if not ok: return 0
                left = r
            return 1
        if isinstance(n, ast.Call):
            f, args = n.func.id, [self.ev(a) for a in n.args]
            if f in PURE:
                try:
                    return PURE[f](*args)
                except (TypeError, ValueError) as e:
                    raise LangError(str(e))
            if f in SENSE:
                return getattr(self.screen.inputs, f)(self.screen.t)
            if f == "eyes":
                self.screen.eyes(args[0])
                return None
            if f in DRAW:
                if f != "text" and not all(isinstance(a, int) for a in args):
                    raise LangError(f"{f} takes whole numbers")
                if f == "text" and not (isinstance(args[0], int) and isinstance(args[1], int)):
                    raise LangError("text takes x, y and a string")
                getattr(self.screen, f)(*args)
                return None
            raise LangError(f"range only in a for loop")
        raise LangError(f"cannot evaluate {type(n).__name__}")

    def run_block(self, body):
        for s in body:
            self.ex(s)

    def ex(self, s):
        self.tick()
        if isinstance(s, ast.Expr):
            self.ev(s.value)
        elif isinstance(s, ast.Assign):
            v = self.ev(s.value)
            for t in s.targets:
                self.setvar(t.id, v)
        elif isinstance(s, ast.AugAssign):
            fake = ast.BinOp(left=ast.Name(id=s.target.id, ctx=ast.Load()), op=s.op, right=s.value)
            self.setvar(s.target.id, self.ev(fake))
        elif isinstance(s, ast.If):
            self.run_block(s.body if self.ev(s.test) else s.orelse)
        elif isinstance(s, ast.For):
            args = [self.ev(a) for a in s.iter.args]
            if not all(isinstance(a, int) for a in args):
                raise LangError("range takes whole numbers")
            for i in range(*args):
                self.setvar(s.target.id, i)
                try:
                    self.run_block(s.body)
                except _Break:
                    break
                except _Continue:
                    continue
        elif isinstance(s, ast.While):
            while self.ev(s.test):
                try:
                    self.run_block(s.body)
                except _Break:
                    break
                except _Continue:
                    continue
        elif isinstance(s, ast.Break):
            raise _Break
        elif isinstance(s, ast.Continue):
            raise _Continue
        elif isinstance(s, ast.Pass):
            pass
        else:
            raise LangError(f"cannot run {type(s).__name__}")


def run(src, inputs=None, horizon=None):
    """Check and run a program. Returns the Screen: .frames is [(ms, pixels)], the last one the final picture;
    .io_log is [(ms, (led, r, g, b, buzzer))]. With a horizon the run is cut there (as the next request would cut
    it on the board) instead of the program having to end; inputs say what the button and knob do meanwhile."""
    tree = check(src)
    if inputs is not None:
        inputs.shake_seen = -1          # each run starts with no bump reported yet
    m = Machine(inputs, horizon)
    try:
        m.run_block(tree.body)
    except (_Break, _Continue):
        raise LangError("break outside a loop")
    except _Stop:
        pass
    m.screen.frames.append((m.screen.t, bytes(m.screen.px)))
    return m.screen


def same(a, b):
    """Do two programs do the same thing? Same frames in the same order, ignoring how long each stays, and the
    same hardware states in the same order (LED, colour, buzzer, wheels, head, eyes, tone, arm)."""
    fa, fb = [f for _, f in a.frames], [f for _, f in b.frames]
    dedup = lambda fs: [f for i, f in enumerate(fs) if i == 0 or f != fs[i - 1]]
    return dedup(fa) == dedup(fb) and dedup([v for _, v in a.io_log]) == dedup([v for _, v in b.io_log])


def same_timed(a, b, step=10):
    """For reacting programs: the same hardware state and picture at every `step` ms up to the shorter run, so an
    LED that follows the button late or not at all is a different program."""
    def at(log, t):
        v = log[0][1]
        for tt, vv in log:
            if tt <= t:
                v = vv
        return v
    end = min(a.frames[-1][0], b.frames[-1][0])
    fa, fb = [(t, f) for t, f in a.frames], [(t, f) for t, f in b.frames]
    return all(at(a.io_log, t) == at(b.io_log, t) and at(fa, t) == at(fb, t) for t in range(0, end + 1, step))


def png(screen, path, scale=4, frame=-1):
    """A preview of one frame, white on black like the panel (text drawn as blocks, not glyphs)."""
    from PIL import Image
    px = screen.frames[frame][1]
    img = Image.new("1", (W, H))
    img.putdata([255 if p else 0 for p in px])
    img.resize((W * scale, H * scale), Image.NEAREST).save(path)


def gif(screen, path, scale=3):
    from PIL import Image
    frames, durs = [], []
    for i, (t, px) in enumerate(screen.frames):
        img = Image.new("L", (W, H)); img.putdata([230 if p else 10 for p in px])
        frames.append(img.resize((W * scale, H * scale), Image.NEAREST))
        nxt = screen.frames[i + 1][0] if i + 1 < len(screen.frames) else t + 1500
        durs.append(max(60, nxt - t))
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=durs, loop=0)
