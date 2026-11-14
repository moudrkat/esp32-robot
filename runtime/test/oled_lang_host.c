// Host harness for oled_lang.h: runs programs separated by a line holding only "\x01", draws into a
// framebuffer with the same algorithms as research/oled/lang.py's Screen, and prints per program either
// "OK <fnv of each frame, comma-separated>|<hardware log>" or "ERR <reason>". research/oled/test_c.py compares.
// A program preceded by a line "R" reacts: it runs with research/oled/gen.py's PROBE inputs (three button presses,
// the knob turned up in steps) and a 3,000 ms horizon, as lang.run(src, PROBE, horizon=3000) does.
#include <stdio.h>
#include <stdlib.h>
#include "../oled_lang.h"

#define W 128
#define H 64
typedef struct {
  uint8_t px[W * H]; char out[1 << 16]; int outn;
  long t; int io[13]; char log[1 << 14]; int logn; long last_t;   // led, r, g, b, buzzer, fwd, side, turn, head,
                                                                    // eyes, tone, nod, arm
} fb;

static void put(fb *f, int x, int y) { if (x >= 0 && x < W && y >= 0 && y < H) f->px[y * W + x] = 1; }
static void frame(fb *f) {
  uint64_t h = 1469598103934665603ULL;
  for (int i = 0; i < W * H; i++) { h ^= f->px[i]; h *= 1099511628211ULL; }
  f->outn += snprintf(f->out + f->outn, sizeof f->out - f->outn, "%s%016llx", f->outn > 3 ? "," : "", (unsigned long long)h);
}
static void c_clear(void *c) { memset(((fb *)c)->px, 0, W * H); }
static void c_text(void *c, int x, int y, const char *s) {
  for (int i = 0; s[i]; i++) if (s[i] != ' ')
    for (int dx = 0; dx < 5; dx++) for (int dy = 0; dy < 7; dy++) if ((dx + dy) % 2 == 0) put(c, x + i * 6 + dx, y + dy);
}
static void c_pixel(void *c, int x, int y) { put(c, x, y); }
static void c_line(void *c, int x0, int y0, int x1, int y1) {
  int dx = abs(x1 - x0), dy = -abs(y1 - y0), sx = x0 < x1 ? 1 : -1, sy = y0 < y1 ? 1 : -1, err = dx + dy;
  for (int k = 0; k < W + H + 2; k++) {
    put(c, x0, y0);
    if (x0 == x1 && y0 == y1) break;
    int e2 = 2 * err;
    if (e2 >= dy) { err += dy; x0 += sx; }
    if (e2 <= dx) { err += dx; y0 += sy; }
  }
}
static void c_rect(void *c, int x, int y, int w, int h) {
  if (w <= 0 || h <= 0) return;
  c_line(c, x, y, x + w - 1, y); c_line(c, x, y + h - 1, x + w - 1, y + h - 1);
  c_line(c, x, y, x, y + h - 1); c_line(c, x + w - 1, y, x + w - 1, y + h - 1);
}
static void c_fill(void *c, int x, int y, int w, int h) {
  for (int yy = y < 0 ? 0 : y; yy < (y + h < H ? y + h : H); yy++)
    for (int xx = x < 0 ? 0 : x; xx < (x + w < W ? x + w : W); xx++) ((fb *)c)->px[yy * W + xx] = 1;
}
static void c_circle(void *c, int cx, int cy, int r) {
  int x = r, y = 0, err = 1 - r;
  while (x >= y) {
    int pts[8][2] = {{x, y}, {y, x}, {-y, x}, {-x, y}, {-x, -y}, {-y, -x}, {y, -x}, {x, -y}};
    for (int k = 0; k < 8; k++) put(c, cx + pts[k][0], cy + pts[k][1]);
    y++;
    if (err < 0) err += 2 * y + 1; else { x--; err += 2 * (y - x) + 1; }
  }
}
static void c_wait(void *c, int ms) { frame(c); ((fb *)c)->t += ms; }

// the hardware log, in lang.Screen.set_io's form: a change at the same ms as the last entry replaces it
static void log_io(fb *f, int k, int v) {
  if (f->io[k] == v) return;
  f->io[k] = v;
  if (f->logn && f->last_t == f->t) {                       // drop the last entry, write it again
    int i = f->logn - 2; while (i > 0 && f->log[i - 1] != ';') i--;
    f->logn = i;
  }
  f->logn += snprintf(f->log + f->logn, sizeof f->log - f->logn, "%ld:%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d;", f->t,
                      f->io[0], f->io[1], f->io[2], f->io[3], f->io[4], f->io[5], f->io[6], f->io[7], f->io[8],
                      f->io[9], f->io[10], f->io[11], f->io[12]);
  f->last_t = f->t;
}
static void c_led(void *c, int on) { log_io(c, 0, on); }
static void c_rgb(void *c, int r, int g, int b) {
  fb *f = c;
  if (f->io[1] == r && f->io[2] == g && f->io[3] == b) return;
  f->io[2] = g; f->io[3] = b; f->io[1] = -1;     // one change of state, logged once with all three
  log_io(f, 1, r);
}
static void c_buzz(void *c, int on) { log_io(c, 4, on); }
static int reacting;
static int c_button(void *c) {
  long t = ((fb *)c)->t;
  if (!reacting) return 0;
  return (t >= 300 && t < 500) || (t >= 900 && t < 1000) || (t >= 1500 && t < 1900);
}
static void c_move(void *c, int fw, int sd, int tn) {
  fb *f = c;
  if (f->io[5] == fw && f->io[6] == sd && f->io[7] == tn) return;
  f->io[6] = sd; f->io[7] = tn; f->io[5] = fw + 1000;   // force one logged change with all three
  log_io(f, 5, fw);
}
static void c_look(void *c, int a) { log_io(c, 8, a); }
static void c_eyes(void *c, int k) { log_io(c, 9, k); }
static void c_tone(void *c, int hz) { log_io(c, 10, hz); }
static void c_nod(void *c, int a) { log_io(c, 11, a); }
static void c_arm(void *c, int a) { log_io(c, 12, a); }
// research/oled/gen.py PROBE, as held values over time; shaken reports each bump once
static int held(const long *t, const int *v, int n, long now) { int r = v[0]; for (int i = 0; i < n; i++) if (t[i] <= now) r = v[i]; return r; }
static long shake_seen;
static int c_sense(void *c, int which) {
  long t = ((fb *)c)->t;
  static const long dt[] = {0, 600, 900, 1500, 1800}; static const int dv[] = {120, 15, 60, 10, 90};
  static const long lt[] = {0, 300, 600, 900, 1200, 1500}; static const int lv[] = {0, 1, 0, 2, 3, 0};
  static const long tt[] = {0, 1000, 1300}; static const int tv[] = {0, 45, 0};
  static const long et[] = {0, 1000}; static const int ev[] = {24, 19};
  static const long ht[] = {0, 1200}; static const int hv[] = {40, 75};
  static const long st[] = {0, 500, 700, 1400, 1600}; static const int sv[] = {5, 80, 5, 90, 5};
  static const long bt[] = {0, 1000, 1500}; static const int bv[] = {100, 15, 100};
  static const long bumps[] = {700, 1600};
  if (!reacting) {                                        // lang.Inputs() defaults
    static const int def[] = {200, 0, 0, 0, 22, 45, 0, 200}; return def[which];
  }
  switch (which) {
  case OL_S_DISTANCE: return held(dt, dv, 5, t);
  case OL_S_TRACK: return held(lt, lv, 6, t);
  case OL_S_TILT: return held(tt, tv, 3, t);
  case OL_S_TEMP: return held(et, ev, 2, t);
  case OL_S_HUMIDITY: return held(ht, hv, 2, t);
  case OL_S_SOUND: return held(st, sv, 5, t);
  case OL_S_BEHIND: return held(bt, bv, 3, t);
  case OL_S_SHAKEN:
    for (int i = 0; i < 2; i++) if (shake_seen < bumps[i] && bumps[i] <= t) { shake_seen = bumps[i]; return 1; }
    return 0;
  }
  return 0;
}
static int c_knob(void *c) {
  long t = ((fb *)c)->t;
  if (!reacting) return 50;                 // lang.Inputs() default
  return t >= 1600 ? 95 : t >= 800 ? 60 : 10;
}
static void c_done(void *c) { frame(c); }

static ol_machine M;
static fb F;
int main(void) {
  static char buf[1 << 27]; size_t n = fread(buf, 1, sizeof buf - 1, stdin); buf[n] = 0;
  ol_io io = {&F, c_clear, c_text, c_pixel, c_line, c_rect, c_fill, c_circle, c_wait, c_done,
              c_led, c_rgb, c_buzz, c_button, c_knob, c_move, c_look, c_sense, c_eyes, c_tone, c_nod, c_arm};
  char *p = buf;
  while (*p) {
    char *end = strstr(p, "\n\x01\n");
    if (end) *end = 0;
    reacting = !strncmp(p, "R\n", 2);
    if (reacting) p += 2;
    memset(&F, 0, sizeof F); strcpy(F.out, "OK ");  F.outn = 3;
    F.logn = snprintf(F.log, sizeof F.log, "0:0,0,0,0,0,0,0,0,0,0,0,0,0;"); F.last_t = 0; shake_seen = -1;
    M.horizon = reacting ? 3000 : 0; M.forever = 0;
    if (ol_parse(&M, p) != 0) printf("ERR %s\n", M.err);
    else if (ol_run(&M, &io) != 0) printf("ERR %s\n", M.err);
    else printf("%s|%s\n", F.out, F.log);
    if (!end) break;
    p = end + 3;
  }
  return 0;
}
