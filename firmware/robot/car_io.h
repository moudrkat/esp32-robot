// car_io.h -- the robot car's hardware for the program interpreter (runtime/oled_lang.h).
//
// Part of the robot sketch (generated/car.h defines CAR_ROBOT). The model writes a program for the request, the interpreter
// runs it, and every hardware call lands here: wheels (two L9110S, four normal wheels: it drives and turns, the
// sideways argument of move() is ignored), a head on two servos with a distance sensor, an arm on a third servo,
// line sensors underneath, a second distance sensor at the back, an MPU6050, an SHT40, a microphone, an 8x8
// NeoPixel as its eyes (rgb() sets their colour), a passive buzzer as its voice and an active one as its horn.
// The OLED stays the screen the interpreter draws on, so text and faces work as on the desk board.
//
// Untested on the car: the parts were ordered on 14. 11. 2026. Pins, polarities and directions are #defines so
// the first power-up can fix them without touching the logic.
//
// Safety rules here, not in the model: any new request stops the wheels before the model starts writing; wheels a
// finished program left running stop after CAR_COAST_MS; the eyes are never brighter than EYES_BRIGHTNESS.

#ifndef CAR_IO_H
#define CAR_IO_H

#include <Wire.h>
#include <Adafruit_NeoPixel.h>
#include <math.h>

// ---------------------------------------------------------------- pins (ESP32-S3 N16R8; 26-37 are flash/PSRAM)
#ifndef PIN_ML_A
#define PIN_ML_A 4      // left L9110S, A-IA
#define PIN_ML_B 5      // left L9110S, A-IB
#define PIN_MR_A 6      // right L9110S, A-IA
#define PIN_MR_B 7      // right L9110S, A-IB
#endif
#define PIN_PAN    15   // head left/right servo
#define PIN_TILT   16   // head up/down servo
#define PIN_ARM    17   // arm servo
#define PIN_TRIG_F 9    // front HC-SR04 (on the head); RCWL-9610 runs on 3.3 V, so ECHO is safe without a divider
#define PIN_ECHO_F 10
#define PIN_TRIG_B 11   // rear HC-SR04
#define PIN_ECHO_B 12
#define PIN_LINE_L 13   // LF-2
#define PIN_LINE_R 14
#define PIN_EYES   21   // NeoPixel 8x8 DIN
#define PIN_HORN   38   // active buzzer
#define PIN_VOICE  39   // passive buzzer
#define PIN_MIC    1    // KY-037 AO (ADC1)
#define PIN_LED    48   // the board's own RGB LED, used by led()
// I2C (OLED 0x3C, MPU6050 0x68, SHT40 0x44) is the desk board's: OLED_SDA 18, OLED_SCL 8, in display.h.

#ifndef LINE_ACTIVE_HIGH
#define LINE_ACTIVE_HIGH 1     // LF-2 output on black (or past a table edge); flip if it reads inverted
#endif
#ifndef MOTOR_L_SIGN
#define MOTOR_L_SIGN 1         // -1 if the left wheels run backwards on move(60, 0, 0)
#define MOTOR_R_SIGN 1
#endif
#ifndef CAR_COAST_MS
#define CAR_COAST_MS 10000
#endif
#ifndef EYES_FLIP_X
#define EYES_FLIP_X 0          // 1 if the eyes come out mirrored left-right
#endif
#ifndef EYES_FLIP_Y
#define EYES_FLIP_Y 0          // 1 if they come out upside down
#endif
#ifndef EYES_SERPENTINE
#define EYES_SERPENTINE 0      // 1 if every other row of the matrix runs backwards (some 8x8 boards are wired so)
#endif
#ifndef EYES_BRIGHTNESS
#define EYES_BRIGHTNESS 24     // of 255: 64 LEDs at full white would pull >3 A from the boost
#endif

// ---------------------------------------------------------------- wheels
static int car_fwd = 0, car_turn = 0;
static unsigned long car_moved_at = 0;
static bool car_program_running = false;

// One PWM pin and one direction pin per side: forward is IB low and IA high for `duty`; backward is IB high and IA
// low for `duty` (so the PWM is inverted). That leaves LEDC timers for the servos and the voice: LEDC channels share
// timers in pairs, and a tone on a timer a servo also uses would throw the servo.
static void motor(int pa, int pb, int v) {            // v -100..100
  int duty = abs(v) * 255 / 100;
  if (v >= 0) { digitalWrite(pb, LOW); ledcWrite(pa, duty); }
  else { digitalWrite(pb, HIGH); ledcWrite(pa, 255 - duty); }
}
static void car_wheels(int fwd, int turn) {
  car_fwd = fwd; car_turn = turn; car_moved_at = millis();
  int l = fwd + turn, r = fwd - turn;                 // turn right (+): left side faster
  l = l > 100 ? 100 : l < -100 ? -100 : l;
  r = r > 100 ? 100 : r < -100 ? -100 : r;
  motor(PIN_ML_A, PIN_ML_B, MOTOR_L_SIGN * l);
  motor(PIN_MR_A, PIN_MR_B, MOTOR_R_SIGN * r);
}
static void c_move(void *, int f, int sideways, int t) { (void)sideways; car_wheels(f, t); }

// ---------------------------------------------------------------- servos: 50 Hz, 500..2500 us
static void servo_deg(int pin, int deg) {             // 0..180
  int us = 500 + deg * 2000 / 180;
  ledcWrite(pin, (uint32_t)us * 16383 / 20000);       // 14-bit at 50 Hz: 20 000 us per period
}
static void c_look(void *, int a) { servo_deg(PIN_PAN, 90 + a); }
static void c_nod(void *, int a) { servo_deg(PIN_TILT, 90 + a); }
static void c_arm(void *, int a) { servo_deg(PIN_ARM, a); }

// ---------------------------------------------------------------- distance
static int sonar_cm(int trig, int echo) {
  digitalWrite(trig, LOW); delayMicroseconds(2);
  digitalWrite(trig, HIGH); delayMicroseconds(10); digitalWrite(trig, LOW);
  unsigned long us = pulseIn(echo, HIGH, 25000);      // ~4 m
  return us ? (int)(us / 58) : 400;
}

// ---------------------------------------------------------------- MPU6050: tilt and bumps
static float acc_g[3] = {0, 0, 1};
static bool bumped = false;
static void mpu_begin() {
  Wire.beginTransmission(0x68); Wire.write(0x6B); Wire.write(0); Wire.endTransmission();   // wake
}
static void mpu_read() {
  Wire.beginTransmission(0x68); Wire.write(0x3B);
  if (Wire.endTransmission(false) != 0) return;
  if (Wire.requestFrom(0x68, 6) != 6) return;
  for (int k = 0; k < 3; k++) { int16_t v = (Wire.read() << 8) | Wire.read(); acc_g[k] = v / 16384.f; }
  float n = sqrtf(acc_g[0] * acc_g[0] + acc_g[1] * acc_g[1] + acc_g[2] * acc_g[2]);
  if (fabsf(n - 1.f) > 0.6f) bumped = true;           // a knock or a shake: more than 0.6 g off resting
}
static int tilt_deg() {
  float n = sqrtf(acc_g[0] * acc_g[0] + acc_g[1] * acc_g[1] + acc_g[2] * acc_g[2]);
  if (n < 0.1f) return 0;
  float c = acc_g[2] / n; c = c > 1 ? 1 : c < -1 ? -1 : c;
  return (int)(acosf(c) * 57.2958f);
}

// ---------------------------------------------------------------- SHT40, read at most once a second
static int sht_t = 22, sht_h = 45;
static unsigned long sht_at = 0;
static void sht_read() {
  if (sht_at && millis() - sht_at < 1000) return;
  sht_at = millis();
  static uint8_t addr = 0x44;                         // SHT40-AD1B is 0x44, SHT40-BD1B 0x45
  Wire.beginTransmission(addr); Wire.write(0xFD);
  if (Wire.endTransmission() != 0) { addr = addr == 0x44 ? 0x45 : 0x44; return; }
  delay(10);
  if (Wire.requestFrom(addr, (uint8_t)6) != 6) return;
  uint16_t t = (Wire.read() << 8) | Wire.read(); Wire.read();
  uint16_t h = (Wire.read() << 8) | Wire.read(); Wire.read();
  sht_t = (int)lroundf(-45.f + 175.f * t / 65535.f);
  int rh = (int)lroundf(-6.f + 125.f * h / 65535.f);
  sht_h = rh < 0 ? 0 : rh > 100 ? 100 : rh;
}

// ---------------------------------------------------------------- microphone: loudness as peak to peak, 0..100
static int mic_level() {
  int lo = 4095, hi = 0;
  unsigned long t0 = micros();
  while (micros() - t0 < 5000) { int v = analogRead(PIN_MIC); if (v < lo) lo = v; if (v > hi) hi = v; }
  int pp = hi - lo;                                    // a quiet room ~20-60 counts, a clap close by >1500
  int s = pp * 100 / 2000;
  return s > 100 ? 100 : s;
}

static int c_sense(void *, int which) {
  switch (which) {
  case OL_S_DISTANCE: return sonar_cm(PIN_TRIG_F, PIN_ECHO_F);
  case OL_S_BEHIND: return sonar_cm(PIN_TRIG_B, PIN_ECHO_B);
  case OL_S_TRACK: {
    int l = digitalRead(PIN_LINE_L) == (LINE_ACTIVE_HIGH ? HIGH : LOW);
    int r = digitalRead(PIN_LINE_R) == (LINE_ACTIVE_HIGH ? HIGH : LOW);
    return l | (r << 1);                               // 0 none, 1 left, 2 right, 3 both
  }
  case OL_S_TILT: mpu_read(); return tilt_deg();
  case OL_S_SHAKEN: { mpu_read(); bool b = bumped; bumped = false; return b ? 1 : 0; }
  case OL_S_TEMP: sht_read(); return sht_t;
  case OL_S_HUMIDITY: sht_read(); return sht_h;
  case OL_S_SOUND: return mic_level();
  }
  return 0;
}

// ---------------------------------------------------------------- eyes: two eyes on the 8x8, one byte per row
static Adafruit_NeoPixel eyes_px(64, PIN_EYES, NEO_GRB + NEO_KHZ800);
static uint8_t eye_r = 0, eye_g = 160, eye_b = 255; // rgb() recolours them; rgb(0, 0, 0) turns them off
static int eye_mood = 0;
// order as OL_EYES: open happy sad angry sleepy closed wink heart left right up down surprised dizzy
static const uint8_t EYE_ROWS[OL_EYES_N][8] = {
  {0x00, 0x66, 0xFF, 0xFF, 0xFF, 0x66, 0x00, 0x00},   // open
  {0x00, 0x66, 0xFF, 0x99, 0x00, 0x00, 0x00, 0x00},   // happy: arcs
  {0x00, 0x00, 0x00, 0x66, 0xFF, 0x99, 0x00, 0x00},   // sad: drooping
  {0x00, 0x81, 0xC3, 0xE7, 0xFF, 0x66, 0x00, 0x00},   // angry: brows down to the middle
  {0x00, 0x00, 0x00, 0x00, 0xFF, 0x66, 0x00, 0x00},   // sleepy: half shut
  {0x00, 0x00, 0x00, 0x00, 0xE7, 0x00, 0x00, 0x00},   // closed
  {0x00, 0x60, 0xF0, 0xF7, 0xF0, 0x60, 0x00, 0x00},   // wink: left open, right a line
  {0x00, 0x66, 0xFF, 0xFF, 0x7E, 0x3C, 0x18, 0x00},   // heart
  {0x00, 0x66, 0x99, 0x99, 0x99, 0x66, 0x00, 0x00},   // left: pupils drawn by eyes_show
  {0x00, 0x66, 0x99, 0x99, 0x99, 0x66, 0x00, 0x00},   // right
  {0x00, 0x66, 0x99, 0x99, 0x99, 0x66, 0x00, 0x00},   // up
  {0x00, 0x66, 0x99, 0x99, 0x99, 0x66, 0x00, 0x00},   // down
  {0xE7, 0xA5, 0xA5, 0xA5, 0xE7, 0x00, 0x00, 0x00},   // surprised: wide rings
  {0x00, 0xA5, 0x42, 0xA5, 0x00, 0x00, 0x00, 0x00},   // dizzy: crosses
};
static int eye_px(int x, int y) {                     // matrix pixel for (column, row), 0..7 each
  if (EYES_FLIP_X) x = 7 - x;
  if (EYES_FLIP_Y) y = 7 - y;
  if (EYES_SERPENTINE && (y & 1)) x = 7 - x;
  return y * 8 + x;
}
static void eyes_show() {
  eyes_px.clear();
  for (int y = 0; y < 8; y++)
    for (int x = 0; x < 8; x++)
      if (EYE_ROWS[eye_mood][y] & (0x80 >> x)) eyes_px.setPixelColor(eye_px(x, y), eye_r, eye_g, eye_b);
  if (eye_mood >= 8 && eye_mood <= 11) {               // looking somewhere: a white pupil inside each ring
    // each eye is a ring 4 wide (left eye columns 0-3, right eye 4-7), rows 1-5; its inside is columns 1-2, rows 2-4
    static const int8_t PUP[4][2][2] = {                // mood -> two pixels (x, y) of the left eye's pupil
      {{1, 3}, {1, 3}},                                 // left
      {{2, 3}, {2, 3}},                                 // right
      {{1, 2}, {2, 2}},                                 // up
      {{1, 4}, {2, 4}},                                 // down
    };
    for (int e = 0; e < 2; e++)
      for (int k = 0; k < 2; k++)
        eyes_px.setPixelColor(eye_px(PUP[eye_mood - 8][k][0] + 4 * e, PUP[eye_mood - 8][k][1]), 255, 255, 255);
  }
  eyes_px.show();
}
static void c_eyes(void *, int mood) { eye_mood = mood; eyes_show(); }
static void c_rgb(void *, int r, int g, int b) { eye_r = r; eye_g = g; eye_b = b; eyes_show(); }

// ---------------------------------------------------------------- sound, led
static void c_buzz(void *, int on) { digitalWrite(PIN_HORN, on ? HIGH : LOW); }
static void c_tone(void *, int hz) { ledcWriteTone(PIN_VOICE, hz); }
static void c_led(void *, int on) { rgbLedWrite(PIN_LED, on ? 40 : 0, on ? 40 : 0, on ? 40 : 0); }
static int c_knob(void *) { return analogRead(2) * 100 / 4095; }   // the steering pot doubles as knob()

// ---------------------------------------------------------------- the interpreter's wait: sample the bump sensor
// while waiting, so a knock between two shaken() calls is not missed
static void car_wait(void *, int ms) {
  oled.display();                                     // once: a frame takes ~25 ms on I2C, and wait(700) must be 700
  unsigned long t0 = millis();
  while ((long)(millis() - t0) < ms) {
    mpu_read();
    if (poll_serial_line()) { olm->stop = 1; return; }
    long left = ms - (long)(millis() - t0);
    if (left > 0) delay(left < 10 ? left : 10);
  }
}

static ol_io car_io() {
  ol_io io = {nullptr, g_clear, g_text, g_pixel, g_line, g_rect, g_fill, g_circle, car_wait, g_done,
              c_led, c_rgb, c_buzz, nullptr, c_knob, c_move, c_look, c_sense, c_eyes, c_tone, c_nod, c_arm};
  return io;
}

// ---------------------------------------------------------------- lifecycle
#if defined(CAR_COND)
static void cond_reset();
#endif
#if defined(CAR_WEB)
static void web_setup();
#endif
#if defined(CAR_PROBE)
static void car_probe_setup();
#endif
static ol_machine *olm_early;             // runs a plain first line while the rest is being written (see below)
static bool early_done = false;
static void car_setup() {
  // channels 0,1 -> timer 0 (motors, 20 kHz); 2,3 -> timer 1 and 4 -> timer 2 (servos, 50 Hz); 6 -> timer 3 (voice)
  pinMode(PIN_ML_B, OUTPUT); pinMode(PIN_MR_B, OUTPUT);
  ledcAttachChannel(PIN_ML_A, 20000, 8, 0); ledcAttachChannel(PIN_MR_A, 20000, 8, 1);
  car_wheels(0, 0);
  ledcAttachChannel(PIN_PAN, 50, 14, 2); ledcAttachChannel(PIN_TILT, 50, 14, 3); ledcAttachChannel(PIN_ARM, 50, 14, 4);
  servo_deg(PIN_PAN, 90); servo_deg(PIN_TILT, 90); servo_deg(PIN_ARM, 0);
  pinMode(PIN_TRIG_F, OUTPUT); pinMode(PIN_ECHO_F, INPUT);
  pinMode(PIN_TRIG_B, OUTPUT); pinMode(PIN_ECHO_B, INPUT);
  pinMode(PIN_LINE_L, INPUT); pinMode(PIN_LINE_R, INPUT);
  pinMode(PIN_HORN, OUTPUT); digitalWrite(PIN_HORN, LOW);
  ledcAttachChannel(PIN_VOICE, 2000, 10, 6); ledcWriteTone(PIN_VOICE, 0);
  mpu_begin();                                          // Wire is already up: display.h began it on 18/8
#if defined(CAR_COND)
  cond_reset();
#endif
  olm_early = (ol_machine *)heap_caps_malloc(sizeof(ol_machine), MALLOC_CAP_SPIRAM);
#if defined(CAR_PROBE)
  car_probe_setup();
#endif
#if defined(CAR_WEB)
  web_setup();
#endif
  eyes_px.begin(); eyes_px.setBrightness(EYES_BRIGHTNESS);
  eye_mood = 0; eyes_show();
}

// a new request: stop first, then look up while thinking (the model writes for a few seconds)
static void car_on_request() {
  car_wheels(0, 0);
  ledcWriteTone(PIN_VOICE, 0); digitalWrite(PIN_HORN, LOW);
  eye_mood = 10; eyes_show();                           // "up"
  early_done = false;
}
// while the model writes, the thinking eyes show the steering dose: blue calm (knob left), the usual colour at
// zero, red wild (knob right)
static uint8_t keep_r, keep_g, keep_b;
static bool dose_shown = false;
static void car_show_dose() {
#ifdef LLM_STEER
  if (!dose_shown) { keep_r = eye_r; keep_g = eye_g; keep_b = eye_b; dose_shown = true; }
  float k = g_steer.gamma / STEER_GAMMA_RANGE;        // -1..1
  if (k > 0) { eye_r = 255; eye_g = (uint8_t)(160 * (1 - k)); eye_b = (uint8_t)(255 * (1 - k)); }
  else if (k < 0) { eye_r = 0; eye_g = (uint8_t)(160 * (1 + k)); eye_b = 255; }
  else { eye_r = keep_r; eye_g = keep_g; eye_b = keep_b; }
  eyes_show();
#endif
}
// ---------------------------------------------------------------- inputs that are not words (CAR_COND)
// The model learned, beside the words, a few strengths (angry, caution, child, …): sum_k s_k * c_k is added to the
// residual after layer COND_LAYER at every position. Here that is steer.h with the raw vector. "@angry" puts a mood
// on the knob, "@angry 0.7" sets it fixed, "@off" clears all. Strengths hold until changed.
#if defined(CAR_COND)
#include "generated/cond_vec.h"   // COND_N, COND_D, COND_LAYER, COND_NAMES[], COND_VEC[COND_N][COND_D]
static float cond_fixed[COND_N];  // -1: not set
static int cond_knob = -1;        // the channel the knob drives, or -1
static void cond_reset() { for (int k = 0; k < COND_N; k++) cond_fixed[k] = -1.f; cond_knob = -1; }
static bool cond_auto = true;     // the sensors set some inputs by themselves ("@auto off" to stop)
static int cond_index(const char *name) { for (int k = 0; k < COND_N; k++) if (!strcmp(COND_NAMES[k], name)) return k; return -1; }
// what the robot feels on its own: lifted or tipped -> scared, loud around it -> scared, cold air -> cold
static float cond_from_sensors(int k) {
  if (!cond_auto) return 0.f;
  if (k == cond_index("scared")) {
    mpu_read();
    float s = tilt_deg() > 30 ? 1.f : 0.f;
    int loud = mic_level();
    if (loud > 70) s = s > 0.8f ? s : 0.8f;
    return s;
  }
  if (k == cond_index("cold")) {
    sht_read();
    return sht_t >= 20 ? 0.f : (20 - sht_t) / 8.f > 1.f ? 1.f : (20 - sht_t) / 8.f;
  }
  return 0.f;
}
static float cond_now[COND_N];    // what was applied for the last request, for the phone page
static void car_cond_apply() {
  static float v[COND_D];
  float knob_s = analogRead(2) / 4095.f;
  memset(v, 0, sizeof v);
  int any = 0;
  for (int k = 0; k < COND_N; k++) {
    float s = k == cond_knob ? knob_s : cond_fixed[k];
    float a = cond_from_sensors(k);
    if (a > s) s = a;
    cond_now[k] = s > 0.f ? s : 0.f;
    if (s <= 0.f) continue;
    any = 1;
    for (int i = 0; i < COND_D; i++) v[i] += s * COND_VEC[k][i];
    Serial.printf("[%s %.2f] ", COND_NAMES[k], s);
  }
  memcpy(g_steer.v, v, sizeof v);
  g_steer.dim = any ? COND_D : 0; g_steer.gamma = 1.f; g_steer.relative = 0; g_steer.layer = COND_LAYER;
}
static void car_cond_command(const char *line) {  // "@off", "@angry", "@angry 0.7"
  char name[24] = {0}; float s = -1.f;
  int got = sscanf(line, "%23s %f", name, &s);
  if (got >= 1 && !strcmp(name, "off")) { cond_reset(); Serial.println("inputs off"); return; }
  if (got >= 1 && !strcmp(name, "auto")) {          // "@auto" on, "@auto 0" off
    cond_auto = got < 2 || s > 0.f; Serial.printf("sensor inputs %s\n", cond_auto ? "on" : "off"); return;
  }
  for (int k = 0; k < COND_N; k++) if (!strcmp(name, COND_NAMES[k])) {
    if (got == 2) { cond_fixed[k] = s < 0 ? 0 : s > 1 ? 1 : s; if (cond_knob == k) cond_knob = -1; }
    else cond_knob = k;
    Serial.printf("%s: %s\n", COND_NAMES[k], got == 2 ? "fixed" : "on the knob");
    return;
  }
  Serial.print("inputs:"); for (int k = 0; k < COND_N; k++) Serial.printf(" %s", COND_NAMES[k]); Serial.println();
}
#endif

// ---------------------------------------------------------------- reacting before the program is finished
// When the model has written its first line and it is a look or a gesture (eyes, head, arm, lights, stop), run that
// line at once, while the rest is still being written. Never the wheels: "move(60, 0, 0) / wait(2000) / stop()" started
// early would drive for the writing time on top of its two seconds. The whole program runs afterwards as usual.
static void car_early_check(const char *prog, int len) {
  if (early_done || !olm_early) return;
  const char *nl = (const char *)memchr(prog, '\n', len);
  if (!nl) return;
  early_done = true;
  static const char *ok[] = {"stop()", "eyes(", "look(", "nod(", "arm(", "rgb("};
  bool plain = false;
  for (const char *p : ok) if (!strncmp(prog, p, strlen(p))) plain = true;
  if (!plain) return;
  static char line[96];
  int n = nl - prog + 1; if (n >= (int)sizeof line) return;
  memcpy(line, prog, n); line[n] = 0;
  ol_io io = car_io();
  if (ol_parse(olm_early, line) == 0) ol_run(olm_early, &io);
}

// ---------------------------------------------------------------- the phone: a page served by the robot itself
// The robot opens its own Wi-Fi (no internet anywhere): join it, open http://192.168.4.1, type to it, set its inputs.
#if defined(CAR_WEB)
#include <WiFi.h>
#include <WebServer.h>
#ifndef CAR_WIFI_NAME
#define CAR_WIFI_NAME "robot-brain"
#endif
#ifndef CAR_WIFI_PASS
#error "CAR_WEB needs CAR_WIFI_PASS (8+ characters): the Wi-Fi password is yours: ROBOT_WIFI_PASS=... ./flash.sh"
#endif
static WebServer web(80);
static char web_line[200];
static bool web_ready = false;
static char last_program[OL_MAX_SRC];
static const char WEB_PAGE[] PROGMEM = R"HTML(<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>robot brain</title><style>body{font:16px system-ui;margin:16px;max-width:520px}input,button,select{font:inherit;padding:8px;margin:4px 0}
#t{width:100%;box-sizing:border-box}pre{background:#f2f2f4;padding:8px;white-space:pre-wrap}button{margin-right:6px}</style>
<h2>robot brain</h2><input id=t placeholder="yo buddy, let's go" autofocus><button onclick="say(t.value)">send</button>
<button onclick="say('stop')">stop</button><p>
<select id=m></select> <input id=s type=range min=0 max=100 value=0 oninput="v.textContent=s.value/100"> <span id=v>0</span>
<button onclick="fetch('/input?name='+m.value+'&s='+s.value/100)">set</button><button onclick="fetch('/input?name=off')">all off</button></p>
<p>what it wrote:</p><pre id=p></pre><p id=i></p>
<script>t.onkeydown=e=>{if(e.key=='Enter')say(t.value)};
function say(x){if(x)fetch('/say?text='+encodeURIComponent(x));t.value=''}
async function poll(){try{let j=await (await fetch('/state')).json();p.textContent=j.program;i.textContent=j.inputs;
if(!m.options.length)j.names.forEach(n=>m.add(new Option(n)))}catch(e){}setTimeout(poll,800)}poll()</script>)HTML";
static void web_setup() {
  WiFi.mode(WIFI_AP);
  WiFi.softAP(CAR_WIFI_NAME, CAR_WIFI_PASS);
  web.on("/", []() { web.send_P(200, "text/html", WEB_PAGE); });
  web.on("/say", []() {
    snprintf(web_line, sizeof web_line, "%s", web.arg("text").c_str());
    web_ready = web_line[0] != 0;
    web.send(200, "text/plain", "ok");
  });
  web.on("/input", []() {
#if defined(CAR_COND)
    String name = web.arg("name"), s = web.arg("s");
    String cmd = name + (s.length() ? " " + s : "");
    car_cond_command(cmd.c_str());
#endif
    web.send(200, "text/plain", "ok");
  });
  web.on("/state", []() {
    String inputs, names;
#if defined(CAR_COND)
    for (int k = 0; k < COND_N; k++) {
      names += String(k ? "," : "") + "\"" + COND_NAMES[k] + "\"";
      if (cond_now[k] > 0) inputs += String(COND_NAMES[k]) + " " + String(cond_now[k], 2) + "  ";
    }
#endif
    String prog = last_program; prog.replace("\\", "\\\\"); prog.replace("\"", "\\\""); prog.replace("\n", "\\n");
    web.send(200, "application/json", "{\"program\":\"" + prog + "\",\"inputs\":\"" + inputs + "\",\"names\":[" + names + "]}");
  });
  web.begin();
  Serial.printf("phone: join Wi-Fi \"%s\", open http://%s\n", CAR_WIFI_NAME, WiFi.softAPIP().toString().c_str());
}
// called from poll_serial_line(), between tokens and in every wait: a line from the phone counts as a typed line
static bool car_web_poll() {
  web.handleClient();
  if (!web_ready) return false;
  web_ready = false;
  memcpy(pending_line, web_line, strlen(web_line) + 1);
  pending_ready = true;
  return true;
}
#endif

// ---------------------------------------------------------------- the eyes show what it is about to do (CAR_PROBE)
// Two probes read the residual at the request's last token, before a single token of the program is written:
// "will this end in a bump?" and "how fast will I drive?". While it thinks, the eyes go angry red for a bump, and
// otherwise take a colour from blue (slow) to red (fast). Measured, not perfect: see research/robot/probe_export.py.
#if defined(CAR_PROBE)
#include "generated/probe_vec.h"   // PROBE_LAYER, PROBE_DIM, PROBE_W[2][PROBE_DIM], PROBE_B[2]
static void car_probe_setup() {
  g_probe.n = 2; g_probe.layer = PROBE_LAYER; g_probe.dim = PROBE_DIM;
  for (int k = 0; k < 2; k++) { g_probe.w[k] = PROBE_W[k]; g_probe.b[k] = PROBE_B[k]; }
}
static void car_probe_show() {
  float crash = g_probe.score[0], speed = g_probe.score[1];
  Serial.printf("[probe: crash %+.2f, speed %.0f] ", crash, speed);
  if (!dose_shown) { keep_r = eye_r; keep_g = eye_g; keep_b = eye_b; dose_shown = true; }
  if (crash > 0) { eye_mood = 3; eye_r = 255; eye_g = 0; eye_b = 0; }            // angry, red
  else {
    float k = (speed - 20.f) / 80.f; k = k < 0 ? 0 : k > 1 ? 1 : k;
    eye_mood = 10; eye_r = (uint8_t)(255 * k); eye_g = 40; eye_b = (uint8_t)(255 * (1 - k));
  }
  eyes_show();
}
#endif

static void car_before_program() {
#if defined(CAR_WEB)
  snprintf(last_program, sizeof last_program, "%s", program);
#endif
  if (dose_shown) { eye_r = keep_r; eye_g = keep_g; eye_b = keep_b; dose_shown = false; }
  eye_mood = 0; eyes_show(); car_program_running = true;
}
static void car_after_program() { car_program_running = false; car_moved_at = millis(); }

// from loop(): wheels left running by a finished program coast to a stop
static void car_loop() {
  if (!car_program_running && (car_fwd || car_turn) && millis() - car_moved_at > CAR_COAST_MS) car_wheels(0, 0);
}

#endif  // CAR_IO_H
