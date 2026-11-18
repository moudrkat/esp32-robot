// Steering vector on a knob, and one attention head on LEDs.
//
// Two hooks into llm_forward(), both compiled out unless you ask for them:
//
//   -DLLM_STEER      residual-stream injection at one layer, strength from a pot
//   -DLLM_ATTN_VIZ   capture one head's softmax weights for the LED ring
//
// Without those defines this header contributes nothing and llm.h is byte for
// byte the model it was before. That is deliberate: the numerics gate in
// host_verify has to keep meaning what it meant.
//
// The pure-C half (state, apply, capture) builds anywhere, so the same code
// runs under runtime/host_verify before it ever reaches the chip. The Arduino
// half (ADC, NeoPixel) is behind ARDUINO.

#ifndef STEER_H
#define STEER_H

#include <math.h>
#include <string.h>

// ---------------------------------------------------------------- state ---

#ifndef STEER_MAX_DIM
#define STEER_MAX_DIM 512        // raise if the model grows past this
#endif
#ifndef STEER_MAX_POS
#define STEER_MAX_POS 512        // attention viz buffer; seq_len or less
#endif

typedef struct {
  float v[STEER_MAX_DIM];  // the direction, in residual space
  int   dim;               // 0 = no vector loaded, injection is a no-op
  float gamma;             // knob, roughly -4..+4; 0 = bypass
  int   layer;             // which layer to inject at
  int   relative;          // 1 = scale by ||x||/||v|| (recommended)
} SteerState;

static SteerState g_steer = {{0}, 0, 0.f, 0, 1};

// Attention capture: one (layer, head), softmax weights over positions 0..pos.
typedef struct {
  float w[STEER_MAX_POS];
  int   len;               // pos+1 at the last capture
  int   layer, head;
} AttnViz;

static AttnViz g_attn = {{0}, 0, 0, 0};

// The same head as a square: the last ATTN_WIN tokens looking at the last ATTN_WIN tokens. Row r is one token's
// look back (r = ATTN_WIN-1 is the newest), kept as its weights on the ATTN_WIN positions ending at itself, so
// g_attn_rows[r][ATTN_WIN-1] is a token looking at itself. What it gave to older tokens is not kept.
#define ATTN_WIN 8
static float g_attn_rows[ATTN_WIN][ATTN_WIN];
static inline void attn_rows_clear(void) { memset(g_attn_rows, 0, sizeof g_attn_rows); }
// weight of the token in row r on the token in column c, both counted from the oldest of the last ATTN_WIN;
// above the diagonal there is nothing: a token cannot look at what has not been written yet
static inline float attn_cell(int r, int c) { return c > r ? 0.f : g_attn_rows[r][c - r + ATTN_WIN - 1]; }

// ------------------------------------------------------------ injection ---

// x += gamma * v, optionally scaled so gamma means the same thing at every
// depth. Residual norms grow with layer index, so an absolute gamma is a
// different intervention at layer 2 than at layer 8; the relative form divides
// that out and makes the knob position a number you can quote.
static inline void steer_apply(float *x, int D) {
  if (!g_steer.dim || g_steer.gamma == 0.f) return;
  int n = D < g_steer.dim ? D : g_steer.dim;

  float scale = g_steer.gamma;
  if (g_steer.relative) {
    float xn = 0.f, vn = 0.f;
    for (int i = 0; i < n; i++) { xn += x[i] * x[i]; vn += g_steer.v[i] * g_steer.v[i]; }
    scale *= sqrtf(xn) / (sqrtf(vn) + 1e-6f);
  }
  for (int i = 0; i < n; i++) x[i] += scale * g_steer.v[i];
}

// Load a direction and normalise it once, so the knob range does not depend on
// how the vector happened to be scaled when it was extracted.
static inline void steer_set_vector(const float *v, int dim) {
  int n = dim < STEER_MAX_DIM ? dim : STEER_MAX_DIM;
  float nn = 0.f;
  for (int i = 0; i < n; i++) nn += v[i] * v[i];
  nn = sqrtf(nn);
  if (nn < 1e-9f) { g_steer.dim = 0; return; }
  for (int i = 0; i < n; i++) g_steer.v[i] = v[i] / nn;
  g_steer.dim = n;
}

// The cheap first vector: the difference between two token embeddings. Not a
// behavioural direction -- it is an input embedding -- but it lives in the right
// space, needs no host tooling, and tells you the wiring works tonight.
#ifdef LLM_H
static inline void steer_from_token_pair(Model *m, int tok_a, int tok_b) {
  static float a[STEER_MAX_DIM], b[STEER_MAX_DIM];
  int D = m->c.dim > STEER_MAX_DIM ? STEER_MAX_DIM : m->c.dim;
  deq_row(&m->tok_emb, tok_a, a);
  deq_row(&m->tok_emb, tok_b, b);
  for (int i = 0; i < D; i++) a[i] -= b[i];
  steer_set_vector(a, D);
}
#endif

// -------------------------------------------------------------- capture ---

// Called from inside the head loop once the softmax denominator is known.
static inline void attn_capture(const float *scores, float maxs, float denom,
                                int pos) {
  int n = pos + 1;
  if (n > STEER_MAX_POS) n = STEER_MAX_POS;
  for (int t = 0; t < n; t++) g_attn.w[t] = expf(scores[t] - maxs) / denom;
  g_attn.len = n;
  if (pos == 0) attn_rows_clear();                       // a new text
  memmove(g_attn_rows[0], g_attn_rows[1], sizeof(float) * ATTN_WIN * (ATTN_WIN - 1));
  for (int j = 0; j < ATTN_WIN; j++) {
    int k = pos - (ATTN_WIN - 1) + j;
    g_attn_rows[ATTN_WIN - 1][j] = (k >= 0 && k < n) ? g_attn.w[k] : 0.f;
  }
}

// ------------------------------------------------------- Arduino plumbing ---
#ifdef ARDUINO
#include <Arduino.h>

#ifndef PIN_GAMMA
#define PIN_GAMMA 4          // ADC1 on the S3. Never ADC2 with Wi-Fi up.
#endif
#ifndef STEER_GAMMA_RANGE
#define STEER_GAMMA_RANGE 4.f
#endif

// Read once per token, never inside llm_forward(): an ADC read is ~100 us and
// the forward pass runs it L times if you put it there. EMA because a bare pot
// jitters by a couple of counts and you would hear it.
static inline void steer_read_pot(void) {
  float raw = analogRead(PIN_GAMMA) / 4095.f;              // 0..1
  float target = (raw * 2.f - 1.f) * STEER_GAMMA_RANGE;    // -R..+R
  if (fabsf(target) < 0.15f) target = 0.f;                 // detent around zero
  g_steer.gamma = 0.85f * g_steer.gamma + 0.15f * target;
}

#ifdef STEER_USE_NEOPIXEL
#include <Adafruit_NeoPixel.h>

#ifndef PIN_ATTN_RING
#define PIN_ATTN_RING 5
#endif
#ifndef ATTN_RING_LEDS
#define ATTN_RING_LEDS 24
#endif

static Adafruit_NeoPixel attn_ring(ATTN_RING_LEDS, PIN_ATTN_RING,
                                   NEO_GRB + NEO_KHZ800);

static inline void attn_ring_begin(void) {
  attn_ring.begin();
  attn_ring.setBrightness(60);
  attn_ring.clear();
  attn_ring.show();
}

// One LED per position. Up to ATTN_RING_LEDS positions map 1:1; past that the
// ring becomes a sliding window over the most recent tokens -- except LED 0,
// which stays pinned to position 0, because the attention sink is the whole
// point and it must not scroll off.
static inline void attn_ring_show(void) {
  attn_ring.clear();
  if (g_attn.len <= 0) { attn_ring.show(); return; }

  int n = g_attn.len;
  for (int led = 0; led < ATTN_RING_LEDS; led++) {
    int t;
    if (n <= ATTN_RING_LEDS) {
      t = led;
      if (t >= n) break;
    } else if (led == 0) {
      t = 0;                                  // the sink, always visible
    } else {
      t = n - ATTN_RING_LEDS + led;           // sliding window over the rest
    }
    // sqrt, not linear: one weight is usually an order of magnitude above the
    // others and a linear map shows one lit LED and twenty-three dark ones.
    float w = sqrtf(g_attn.w[t]);
    uint8_t val = (uint8_t)(w * 255.f + 0.5f);
    // Cyan for the sink, warm white for the window: the eye separates them
    // without a legend.
    if (led == 0 && n > ATTN_RING_LEDS) attn_ring.setPixelColor(led, 0, val, val);
    else attn_ring.setPixelColor(led, val, val * 0.8f, val * 0.4f);
  }
  attn_ring.show();
}
#endif  // STEER_USE_NEOPIXEL
#endif  // ARDUINO

#endif  // STEER_H
