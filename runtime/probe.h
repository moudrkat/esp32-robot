// probe.h -- read a direction off the residual stream while the model reads a request.
//
// Compiled in only with -DLLM_PROBE. After layer g_probe.layer, every token's residual x is scored against a few
// directions: score_k = x . w_k + b_k. The firmware reads the scores once the prompt has been read, so they describe the
// request's last token: what the model is about to do, before it writes anything (research/robot/probe_export.py
// fits the directions; runtime/host_verify/probe_verify.c checks them against PyTorch).
#ifndef PROBE_H
#define PROBE_H

#ifndef PROBE_MAX
#define PROBE_MAX 4
#endif
#ifndef PROBE_MAX_DIM
#define PROBE_MAX_DIM 512
#endif

typedef struct {
  int n;                              // directions loaded; 0 = off
  int layer;                          // after which layer to read
  int dim;
  const float *w[PROBE_MAX];          // [dim] each
  float b[PROBE_MAX];
  float score[PROBE_MAX];             // at the last token read
} ProbeState;

static ProbeState g_probe = {0, 0, 0, {0}, {0}, {0}};

static inline void probe_read(const float *x, int D) {
  if (!g_probe.n) return;
  int n = D < g_probe.dim ? D : g_probe.dim;
  for (int k = 0; k < g_probe.n; k++) {
    float s = g_probe.b[k];
    for (int i = 0; i < n; i++) s += x[i] * g_probe.w[k][i];
    g_probe.score[k] = s;
  }
}

#endif  // PROBE_H
