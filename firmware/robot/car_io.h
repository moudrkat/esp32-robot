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
// (the 8x8 LEDs are driven by Leds64 below; no NeoPixel library)
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
#endif
#ifndef MOTOR_R_SIGN
#define MOTOR_R_SIGN 1
#endif
// Weak batteries: a geared motor needs more to start than to keep turning, so a side that starts from rest or turns
// around gets full power for this long first. flash.sh writes generated/kick.h for KICK=150 (ms); 0 is off.
#if __has_include("generated/kick.h")
#include "generated/kick.h"
#endif
#ifndef MOTOR_KICK_MS
#define MOTOR_KICK_MS 0
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
#if defined(CAR_DESK)
static void desk_draw();
static void desk_led();
#endif
static void car_wheels(int fwd, int turn) {
  car_fwd = fwd; car_turn = turn; car_moved_at = millis();
#if defined(CAR_DESK)
  desk_led(); desk_draw(); return;                    // no motors on the table: the board's light and the screen
#endif
  int l = fwd + turn, r = fwd - turn;                 // turn right (+): left side faster
  l = l > 100 ? 100 : l < -100 ? -100 : l;
  r = r > 100 ? 100 : r < -100 ? -100 : r;
  static int l_was = 0, r_was = 0;
  bool kl = l && abs(l) < 100 && (!l_was || (l > 0) != (l_was > 0));
  bool kr = r && abs(r) < 100 && (!r_was || (r > 0) != (r_was > 0));
  if (MOTOR_KICK_MS > 0 && (kl || kr)) {
    motor(PIN_ML_A, PIN_ML_B, MOTOR_L_SIGN * (kl ? (l > 0 ? 100 : -100) : l));
    motor(PIN_MR_A, PIN_MR_B, MOTOR_R_SIGN * (kr ? (r > 0 ? 100 : -100) : r));
    delay(MOTOR_KICK_MS);
  }
  l_was = l; r_was = r;
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
#if defined(SHT_SDA)
#define SHT_BUS Wire1                                 // the thermometer on two pins of its own (flash.sh SHT=4,5)
#else
#define SHT_BUS Wire
#endif
static int sht_t = 22, sht_h = 45;
static float sht_c = 22.f, sht_c0 = 22.f;             // the reading, and the first one after power-up
static bool sht_seen = false;
static unsigned long sht_at = 0;
static void sht_read() {
  if (sht_at && millis() - sht_at < 1000) return;
  sht_at = millis();
  static uint8_t addr = 0x44;                         // SHT40-AD1B is 0x44, SHT40-BD1B 0x45
  SHT_BUS.beginTransmission(addr); SHT_BUS.write(0xFD);
  if (SHT_BUS.endTransmission() != 0) { addr = addr == 0x44 ? 0x45 : 0x44; return; }
  delay(10);
  if (SHT_BUS.requestFrom(addr, (uint8_t)6) != 6) return;
  uint16_t t = (SHT_BUS.read() << 8) | SHT_BUS.read(); SHT_BUS.read();
  uint16_t h = (SHT_BUS.read() << 8) | SHT_BUS.read(); SHT_BUS.read();
  sht_c = -45.f + 175.f * t / 65535.f;
  if (!sht_seen) { sht_seen = true; sht_c0 = sht_c; }
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
#if defined(CAR_DESK)
  switch (which) {                                    // on the table: open road, level, quiet
  case OL_S_DISTANCE: case OL_S_BEHIND: return 100;
  case OL_S_TRACK: case OL_S_TILT: case OL_S_SHAKEN: case OL_S_SOUND: return 0;
  }
#endif
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
// The 64 LEDs are driven here: the whole frame is one waveform, handed to the SPI peripheral with DMA, so the
// hardware clocks it out in one piece and nothing the chip is doing meanwhile can stretch a pulse. Four SPI bits
// are one LED bit at 3.2 MHz: 1000 is a zero (0.31 us high), 1110 is a one (0.94 us high), a bit lasts 1.25 us.
// What failed first (18. 11. 2026): the NeoPixel library and the RMT peripheral driven directly (both need an
// interrupt to refill a 48-symbol buffer every ~30 us, and while the model writes a refill comes late: rows of
// full white, then random colours), and SPI fed by the CPU in 64-byte pieces (a stray wrong pixel now and then).
#include "driver/spi_master.h"
struct Leds64 {
  uint8_t px[64][3]; uint8_t bright = 255; bool up = false; int sent = 0;
  spi_device_handle_t dev = NULL; uint8_t *wave = NULL;
  enum { LEAD = 4, BODY = 64 * 24 / 2, TAIL = 44 };            // TAIL: the line low for > 100 us, the LEDs latch
  void begin() {
    spi_bus_config_t bus = {}; bus.mosi_io_num = PIN_EYES; bus.miso_io_num = -1; bus.sclk_io_num = -1;
    bus.quadwp_io_num = -1; bus.quadhd_io_num = -1; bus.max_transfer_sz = LEAD + BODY + TAIL;
    spi_device_interface_config_t cfg = {}; cfg.clock_speed_hz = 3200000; cfg.mode = 0; cfg.spics_io_num = -1; cfg.queue_size = 1;
    wave = (uint8_t *)heap_caps_calloc(1, LEAD + BODY + TAIL, MALLOC_CAP_DMA);
    up = wave && spi_bus_initialize(SPI3_HOST, &bus, SPI_DMA_CH_AUTO) == ESP_OK && spi_bus_add_device(SPI3_HOST, &cfg, &dev) == ESP_OK;
    clear();
  }
  void setBrightness(uint8_t b) { bright = b; }
  void clear() { memset(px, 0, sizeof px); }
  void setPixelColor(int i, int r, int g, int b) {
    if (i < 0 || i >= 64) return;
    px[i][0] = g < 0 ? 0 : g > 255 ? 255 : g; px[i][1] = r < 0 ? 0 : r > 255 ? 255 : r; px[i][2] = b < 0 ? 0 : b > 255 ? 255 : b;   // the wire order is G R B
  }
  void show() {
    if (!up) return;
    int n = LEAD;
    for (int i = 0; i < 64; i++)
      for (int c = 0; c < 3; c++) {
        uint8_t v = (uint16_t)px[i][c] * bright / 255;
        for (int bit = 7; bit >= 0; bit -= 2)                   // two LED bits in one SPI byte
          wave[n++] = ((v & (1 << bit)) ? 0xE0 : 0x80) | ((v & (1 << (bit - 1))) ? 0x0E : 0x08);
      }
    spi_transaction_t t = {}; t.length = (LEAD + BODY + TAIL) * 8; t.tx_buffer = wave;
    up = spi_device_transmit(dev, &t) == ESP_OK; sent = LEAD + BODY + TAIL;
  }
};
static Leds64 eyes_px;
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
#if defined(CAR_ATTN)
// ---------------------------------------------------------------- attention on the 8x8
// One head of the model, as it writes: row = the token that looks, column = the token it looks at, the last 8
// tokens both ways, newest at the bottom right. Brightness is the square root of the weight (the eye is not linear
// either). The half above the diagonal stays dark: the causal mask.
// The newest row is the chain's first eight LEDs, so the chain's last LED is a corner that is never lit
// (on her matrix that one LED is dead).
static bool attn_test = false;                          // a test picture stays until the next sentence or head
static void attn_show() {
  if (attn_test) return;
  static const uint8_t col[3] = {255, 110, 0};          // one colour: brightness is the only thing that speaks
  eyes_px.clear();
  for (int r = 0; r < ATTN_WIN; r++)
    for (int c = 0; c <= r; c++) {
      float b = sqrtf(attn_cell(r, c));
      if (b < 0.04f) continue;
      eyes_px.setPixelColor(eye_px(c, ATTN_WIN - 1 - r), (int)(col[0] * b), (int)(col[1] * b), (int)(col[2] * b));
    }
  eyes_px.show();
}
static void attn_head(int layer, int head) {            // out of range wraps; a new head starts with a dark square
  extern Model model;
  int L = model.c.n_layers, H = model.c.n_heads;
  if (head >= H) { head = 0; layer++; }
  g_attn.layer = ((layer % L) + L) % L; g_attn.head = ((head % H) + H) % H;
  attn_test = false; attn_rows_clear(); attn_show();
  Serial.printf("attention: layer %d head %d\n", g_attn.layer, g_attn.head);
}
static void attn_live() { attn_test = false; }
static void attn_next() { attn_head(g_attn.layer, g_attn.head + 1); }
#endif

static void eyes_show() {
#if defined(CAR_ATTN)
  attn_show(); return;                                  // the square belongs to the attention; eyes() and rgb() wait
#endif
  eyes_px.clear();
#if defined(CAR_DESK)
  // on the table a ring of 24 LEDs on the eyes' pin is a speedometer: more of the circle is faster, red is angry
  {
    int v = car_fwd ? car_fwd : car_turn; v = v < 0 ? -v : v; v = v > 100 ? 100 : v;
    int n = (v * 24 + 50) / 100;
    for (int i = 0; i < n; i++)
      eyes_px.setPixelColor(i, eye_mood == 3 ? 255 : eye_r, eye_mood == 3 ? 0 : eye_g, eye_mood == 3 ? 0 : eye_b);
    eyes_px.show();
    return;
  }
#endif
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
static void c_eyes(void *, int mood) {
  eye_mood = mood; eyes_show();
#if defined(CAR_DESK)
  desk_led(); desk_draw();
#endif
}
static void c_rgb(void *, int r, int g, int b) {
  eye_r = r; eye_g = g; eye_b = b; eyes_show();
#if defined(CAR_DESK)
  desk_led();
#endif
}

// ---------------------------------------------------------------- sound, led
#if defined(CAR_DESK)
// The board's own RGB LED is on pin 48 (Espressif DevKitC-1 v1.0) or 38 (v1.1, Waveshare): both are written.
static bool desk_light = false;
static void desk_led() {                              // the wheels as light: brighter is faster, red when the eyes are angry
  int v = car_fwd ? car_fwd : car_turn; v = v < 0 ? -v : v; v = v > 100 ? 100 : v;
  int r = eye_mood == 3 ? 255 : eye_r, g = eye_mood == 3 ? 0 : eye_g, b = eye_mood == 3 ? 0 : eye_b;
  if (desk_light) { r = g = b = 160; if (v < 25) v = 25; }
  r = r * v / 400; g = g * v / 400; b = b * v / 400;  // a quarter of full at speed 100: it is bright enough to film
#if !defined(CAR_ATTN)                                // the 8x8 has the RMT peripheral to itself
  rgbLedWrite(48, r, g, b); rgbLedWrite(38, r, g, b);
#endif
  eyes_show();                                        // and the ring, if there is one
}
static void c_buzz(void *, int) {}                    // no horn on the table
static void c_led(void *, int on) { desk_light = on; desk_led(); }
#else
static void c_buzz(void *, int on) { digitalWrite(PIN_HORN, on ? HIGH : LOW); }
static void c_led(void *, int on) { rgbLedWrite(PIN_LED, on ? 40 : 0, on ? 40 : 0, on ? 40 : 0); }
#endif
static void c_tone(void *, int hz) { ledcWriteTone(PIN_VOICE, hz); }
static int c_knob(void *) { return analogRead(2) * 100 / 4095; }   // the potentiometer; the language calls it knob()

// ---------------------------------------------------------------- the interpreter's wait: sample the bump sensor
// while waiting, so a knock between two shaken() calls is not missed
static void car_wait(void *, int ms) {
#if defined(CAR_DESK)
  desk_draw();
#endif
  oled.display();                                     // once: a frame takes ~25 ms on I2C, and wait(700) must be 700
  unsigned long t0 = millis();
  while ((long)(millis() - t0) < ms) {
    mpu_read();
    if (poll_serial_line()) { olm->stop = 1; return; }
    long left = ms - (long)(millis() - t0);
    if (left > 0) delay(left < 10 ? left : 10);
  }
}

#if defined(CAR_DESK)
static bool desk_cleared = false;
static void d_clear(void *c) { desk_cleared = true; g_clear(c); }
#define CAR_CLEAR d_clear
#else
#define CAR_CLEAR g_clear
#endif
static ol_io car_io() {
  ol_io io = {nullptr, CAR_CLEAR, g_text, g_pixel, g_line, g_rect, g_fill, g_circle, car_wait, g_done,
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
#if defined(SHT_SDA)
  Wire1.begin(SHT_SDA, SHT_SCL);
#endif
#if defined(CAR_ATTN)
  pinMode(0, INPUT_PULLUP);                             // BOOT: the next attention head
#endif
#if defined(CAR_DESK)
  pinMode(0, INPUT_PULLUP);                             // BOOT: the same sentence again, with the next input strength
  display_bottom = 54;                                  // the last text row is the input's
  sht_read(); sht_at = 0; sht_read();                   // twice: the first try may be at the other address
  Serial.printf("on the table: %s\n", sht_seen ? "thermometer found, \"@angry\" puts an input on it" : "no thermometer");
#else
  pinMode(PIN_ML_B, OUTPUT); pinMode(PIN_MR_B, OUTPUT);
  ledcAttachChannel(PIN_ML_A, 20000, 8, 0); ledcAttachChannel(PIN_MR_A, 20000, 8, 1);
  car_wheels(0, 0);
#endif
  ledcAttachChannel(PIN_PAN, 50, 14, 2); ledcAttachChannel(PIN_TILT, 50, 14, 3); ledcAttachChannel(PIN_ARM, 50, 14, 4);
  servo_deg(PIN_PAN, 90); servo_deg(PIN_TILT, 90); servo_deg(PIN_ARM, 0);
  pinMode(PIN_TRIG_F, OUTPUT); pinMode(PIN_ECHO_F, INPUT);
  pinMode(PIN_TRIG_B, OUTPUT); pinMode(PIN_ECHO_B, INPUT);
  pinMode(PIN_LINE_L, INPUT); pinMode(PIN_LINE_R, INPUT);
#if !defined(CAR_DESK)
  pinMode(PIN_HORN, OUTPUT); digitalWrite(PIN_HORN, LOW);
#endif
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
#if defined(CAR_ATTN)
  eyes_px.setBrightness(40);                            // few LEDs are lit at once
  g_attn.layer = 3; g_attn.head = 4;                    // the liveliest head whose weight stays inside the last 8 tokens (91 %)
#endif
  eye_mood = 0; eyes_show();
}

// a new request: stop first, then look up while thinking (the model writes for a few seconds)
static void car_on_request() {
  car_wheels(0, 0);
  ledcWriteTone(PIN_VOICE, 0);
#if defined(CAR_DESK)
  desk_light = false; desk_led();
#else
  digitalWrite(PIN_HORN, LOW);
#endif
  eye_mood = 10; eyes_show();                           // "up"
  early_done = false;
}
// while the model writes, the thinking eyes show the steering dose: blue calm (potentiometer left), the usual colour at
// zero, red wild (right)
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
// on the potentiometer, "@angry 0.7" sets it fixed, "@off" clears all. Strengths hold until changed.
#if defined(CAR_COND)
#include "generated/cond_vec.h"   // COND_N, COND_D, COND_LAYER, COND_NAMES[], COND_VEC[COND_N][COND_D]
static float cond_fixed[COND_N];  // -1: not set
static int cond_pot = -1;        // the channel the potentiometer drives, or -1
static void cond_reset() { for (int k = 0; k < COND_N; k++) cond_fixed[k] = -1.f; cond_pot = -1; }
#if defined(CAR_DESK)
static bool cond_auto = false;    // on the table the tilt sensor and the microphone are not there
static int desk_ch = -1, desk_level = -1;   // the input BOOT steps through 0, 0.5, 1 (the last one named; angry)
#else
static bool cond_auto = true;     // the sensors set some inputs by themselves ("@auto off" to stop)
#endif
static int cond_index(const char *name) { for (int k = 0; k < COND_N; k++) if (!strcmp(COND_NAMES[k], name)) return k; return -1; }
// what the robot feels on its own: lifted or tipped -> scared, loud around it -> scared, cold air -> cold
static float cond_from_sensors(int k) {
  if (!cond_auto) return 0.f;
#if !defined(CAR_DESK)
  if (k == cond_index("scared")) {
    mpu_read();
    float s = tilt_deg() > 30 ? 1.f : 0.f;
    int loud = mic_level();
    if (loud > 70) s = s > 0.8f ? s : 0.8f;
    return s;
  }
#endif
  if (k == cond_index("cold")) {
    sht_read();
    return sht_t >= 20 ? 0.f : (20 - sht_t) / 8.f > 1.f ? 1.f : (20 - sht_t) / 8.f;
  }
  return 0.f;
}
static float cond_now[COND_N];    // what was applied for the last request, for the phone page
static void car_cond_apply() {
  static float v[COND_D];
#if defined(CAR_DESK)
  // no potentiometer on the table: the thermometer is one. As warm as it woke up is 0, six degrees warmer (a hand) is 1.
  sht_read();
  float pot_s = !sht_seen ? 0.f : (sht_c - sht_c0) / 6.f;
  pot_s = pot_s < 0.f ? 0.f : pot_s > 1.f ? 1.f : pot_s;
#else
  float pot_s = analogRead(2) / 4095.f;
#endif
  memset(v, 0, sizeof v);
  int any = 0;
  for (int k = 0; k < COND_N; k++) {
    float s = k == cond_pot ? pot_s : cond_fixed[k];
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
  if (got >= 1 && !strcmp(name, "off")) {
    cond_reset(); Serial.println("inputs off");
#if defined(CAR_DESK)
    desk_level = -1;
#endif
    return;
  }
  if (got >= 1 && !strcmp(name, "leds")) {          // "@leds": every LED of the 8x8 on, to check the wiring
    for (int i = 0; i < 64; i++) eyes_px.setPixelColor(i, 60, 60, 60);
#if defined(CAR_ATTN)
    attn_test = true;
#endif
    eyes_px.show(); Serial.println("all 64 LEDs on, dim white"); return;
  }
#if defined(CAR_ATTN)
  if (got >= 1 && !strcmp(name, "tri")) {           // "@tri": the shape attention must have, standing still: a red
    eyes_px.clear();                                // triangle, its diagonal white, the newest token's corner green
    for (int r = 0; r < ATTN_WIN; r++)
      for (int c = 0; c <= r; c++)
        eyes_px.setPixelColor(eye_px(c, ATTN_WIN - 1 - r), c == r ? 200 : 120, c == r ? 200 : 0, c == r ? 200 : 0);
    eyes_px.setPixelColor(eye_px(ATTN_WIN - 1, 0), 0, 255, 0);
    attn_test = true;
    eyes_px.show(); Serial.printf("[leds: init %d, %d bytes] ", eyes_px.up, eyes_px.sent);
    Serial.println("triangle: red, white diagonal, green corner = newest token on itself"); return;
  }
  if (got >= 1 && !strcmp(name, "stat")) {          // "@stat": start counting; "@stat" again prints every head and resets
    if (g_attn_stat_on) {
      Serial.println("L H  self  -1   -2   -3   -4   -5   -6   -7  far  move  n");
      for (int l = 0; l < model.c.n_layers; l++)
        for (int h = 0; h < model.c.n_heads; h++) {
          int n = g_attn_cnt[l][h] ? g_attn_cnt[l][h] : 1;
          Serial.printf("%d %d ", l, h);
          for (int j = 0; j <= ATTN_WIN; j++) Serial.printf(" %.2f", g_attn_off[l][h][j] / n);
          Serial.printf("  %.2f  %d\n", g_attn_move[l][h] / n, g_attn_cnt[l][h]);
        }
    }
    attn_stat_clear(); g_attn_stat_on = 1; Serial.println("counting every head"); return;
  }
  if (got >= 1 && !strcmp(name, "head")) {          // "@head" next, "@head 2 3" layer 2 head 3
    int l = 0, h = 0;
    if (sscanf(line, "%*s %d %d", &l, &h) == 2) attn_head(l, h); else attn_next();
    return;
  }
#endif
  if (got >= 1 && !strcmp(name, "auto")) {          // "@auto" on, "@auto 0" off
    cond_auto = got < 2 || s > 0.f; Serial.printf("sensor inputs %s\n", cond_auto ? "on" : "off"); return;
  }
  for (int k = 0; k < COND_N; k++) if (!strcmp(name, COND_NAMES[k])) {
    if (got == 2) { cond_fixed[k] = s < 0 ? 0 : s > 1 ? 1 : s; if (cond_pot == k) cond_pot = -1; }
    else cond_pot = k;
#if defined(CAR_DESK)
    desk_ch = k; desk_level = -1;
    Serial.printf("%s: %s\n", COND_NAMES[k], got == 2 ? "fixed" : sht_seen ? "on the thermometer" : "on the thermometer, but there is none");
#else
    Serial.printf("%s: %s\n", COND_NAMES[k], got == 2 ? "fixed" : "on the potentiometer");
#endif
    return;
  }
  Serial.print("inputs:"); for (int k = 0; k < COND_N; k++) Serial.printf(" %s", COND_NAMES[k]); Serial.println();
}
#endif

// ---------------------------------------------------------------- reacting before the program is finished
// ---------------------------------------------------------------- on the table (CAR_DESK): the screen is the car
// No motors, no eyes: while a program runs, the screen shows the request, the program, what the wheels would be
// doing, the input that was applied and the eyes it chose. BOOT (or a typed "+") asks the same sentence again with
// the next strength of one input: 0, 0.5, 1.
#if defined(CAR_DESK)
static void desk_inputs(char *out, int n) {             // the strongest input applied to this request
  int best = -1;
  for (int k = 0; k < COND_N; k++) if (cond_now[k] > 0 && (best < 0 || cond_now[k] > cond_now[best])) best = k;
  if (best < 0) snprintf(out, n, "no input"); else snprintf(out, n, "%s %.2f", COND_NAMES[best], cond_now[best]);
}
static void desk_writing() {                            // while the model writes: the input, under the text
  char row[22]; desk_inputs(row, sizeof row);
#if defined(CAR_ATTN)
  snprintf(row, sizeof row, "layer %d  head %d", g_attn.layer, g_attn.head);   // which head the 8x8 is showing
#endif
  oled.fillRect(0, 54, SCR_W, 10, OLED_BLACK);
  oled.drawFastHLine(0, 54, SCR_W, OLED_WHITE);
  oled.setCursor(0, 56); oled.print(row);
  oled.display();
}
static void desk_draw() {
  if (!car_program_running) return;                     // not over the text while the model is still writing
  char row[24];
  oled.setTextSize(1);
  oled.fillRect(0, 0, SCR_W, CH + 2, OLED_WHITE);       // the request
  oled.setTextColor(OLED_BLACK);
  snprintf(row, sizeof row, "%.21s", oled_request);
  oled.setCursor(1, 1); oled.print(row);
  oled.setTextColor(OLED_WHITE);
  if (!desk_cleared) {                                  // the program, unless it is drawing something itself
    oled.fillRect(0, CH + 2, SCR_W, 33, OLED_BLACK);
    const char *p = program;
    for (int i = 0; i < 4 && *p; i++) {
      int n = 0; while (p[n] && p[n] != '\n') n++;
      snprintf(row, sizeof row, "%.*s", n > 21 ? 21 : n, p);
      oled.setCursor(0, CH + 4 + i * CH); oled.print(row);
      p += n; if (*p == '\n') p++;
    }
  }
  oled.fillRect(0, 44, SCR_W, 20, OLED_BLACK);          // the wheels and the input
  oled.drawFastHLine(0, 44, SCR_W, OLED_WHITE);
  int v = car_fwd ? car_fwd : car_turn;
  snprintf(row, sizeof row, "%s %d", car_fwd || !car_turn ? "speed" : "turn", v);
  oled.setCursor(0, 47); oled.print(row);
  oled.drawRect(66, 47, 62, 7, OLED_WHITE);
  int w = (v < 0 ? -v : v) * 60 / 100;
  oled.fillRect(67, 48, w > 60 ? 60 : w, 5, OLED_WHITE);
  desk_inputs(row, sizeof row);
  oled.setCursor(0, 56); oled.print(row);
  if (eye_mood) {                                       // the eyes it chose, by name
    const char *e = OL_EYES[eye_mood];
    oled.setCursor(SCR_W - (int)strlen(e) * CW, 56); oled.print(e);
  }
}
#endif

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
#define CAR_WIFI_NAME "esp32-robot"
#endif
#ifndef CAR_WIFI_PASS
#error "CAR_WEB needs CAR_WIFI_PASS (8+ characters): the Wi-Fi password is yours: ROBOT_WIFI_PASS=... ./flash.sh"
#endif
static WebServer web(80);
static char web_line[200];
static bool web_ready = false;
static char last_program[OL_MAX_SRC];
static const char WEB_PAGE[] PROGMEM = R"HTML(<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>robot</title><style>body{font:16px system-ui;margin:16px;max-width:520px}input,button,select{font:inherit;padding:8px;margin:4px 0}
#t{width:100%;box-sizing:border-box}pre{background:#f2f2f4;padding:8px;white-space:pre-wrap}button{margin-right:6px}</style>
<h2>robot</h2><input id=t placeholder="yo buddy, let's go" autofocus><button onclick="say(t.value)">send</button>
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
#if defined(CAR_DESK)
  desk_cleared = false; desk_draw(); oled.display();
#endif
}
static void car_after_program() {
#if defined(CAR_DESK)
  desk_draw(); oled.display();                          // what it ended on stays on the screen
#endif
  car_program_running = false; car_moved_at = millis();
}

// from loop(): wheels left running by a finished program coast to a stop
static void car_loop() {
  if (!car_program_running && (car_fwd || car_turn) && millis() - car_moved_at > CAR_COAST_MS) car_wheels(0, 0);
}

#endif  // CAR_IO_H
