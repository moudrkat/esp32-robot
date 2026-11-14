// Host check for the robot's non-word inputs: the model was trained with sum_k s_k * c_k added to the residual
// after block cond_layer, at every position. On the chip that is steer.h with the raw vector (no normalising, no
// relative scale, gamma 1). This runs the C model that way on a prompt and compares the last-position logits to
// PyTorch's for the same prompt and strengths (research/robot/cond_golden.py writes the reference).
//
//   cc -O2 -DLLM_STEER -o /tmp/cond_verify runtime/host_verify/cond_verify.c -lm
//   /tmp/cond_verify artifacts/car/model.bin cond_golden.txt
#include <stdio.h>
#include <stdlib.h>
#include "../llm.h"

static uint8_t *read_file(const char *path, size_t *n) {
  FILE *f = fopen(path, "rb");
  if (!f) { perror(path); exit(1); }
  fseek(f, 0, SEEK_END); *n = ftell(f); fseek(f, 0, SEEK_SET);
  uint8_t *b = malloc(*n);
  if (fread(b, 1, *n, f) != *n) { fprintf(stderr, "short read\n"); exit(1); }
  fclose(f); return b;
}

int main(int argc, char **argv) {
  if (argc < 3) { fprintf(stderr, "usage: %s <model.bin> <cond_golden.txt>\n", argv[0]); return 2; }
  size_t n;
  uint8_t *buf = read_file(argv[1], &n);
  Model m;
  if (llm_load(buf, &m)) { fprintf(stderr, "bad magic\n"); return 1; }
  int D = m.c.dim, L = m.c.n_layers, P = m.c.ple_dim, F = m.c.ffn, V = m.out_vocab, S = m.c.seq_len;
  Scratch s;
  s.x = malloc(D * 4); s.h = malloc((F > D ? F : D) * 4);
  s.qkv = malloc(3 * D * 4); s.att = malloc(D * 4);
  s.g1 = malloc(F * 4); s.g2 = malloc((P > F ? P : F) * 4);
  s.ple = malloc(L * P * 4); s.tmpP = malloc(L * P * 4); s.trow = malloc(L * P * 4);
  s.logits = malloc(V * 4);
  s.scores = malloc(S * 4);
  s.kcache = calloc((size_t)L * S * D, 4); s.vcache = calloc((size_t)L * S * D, 4);

  FILE *g = fopen(argv[2], "r");
  if (!g) { perror(argv[2]); return 1; }
  int cases = 0, worst_top = 0; double worst = 0;
  int T;
  while (fscanf(g, "%d", &T) == 1) {
    int ids[512]; for (int i = 0; i < T; i++) if (fscanf(g, "%d", &ids[i]) != 1) return 1;
    int layer; if (fscanf(g, "%d", &layer) != 1) return 1;
    float vec[STEER_MAX_DIM]; for (int i = 0; i < D; i++) if (fscanf(g, "%f", &vec[i]) != 1) return 1;
    float *ref = malloc(V * 4); for (int i = 0; i < V; i++) if (fscanf(g, "%f", &ref[i]) != 1) return 1;
    memcpy(g_steer.v, vec, D * 4); g_steer.dim = D; g_steer.gamma = 1.f; g_steer.relative = 0; g_steer.layer = layer;
    memset(s.kcache, 0, (size_t)L * S * D * 4); memset(s.vcache, 0, (size_t)L * S * D * 4);
    for (int pos = 0; pos < T; pos++) llm_forward(&m, ids[pos], pos, &s);
    double md = 0; int ct = 0, rt = 0;
    for (int i = 0; i < V; i++) {
      double d = fabs((double)s.logits[i] - ref[i]); if (d > md) md = d;
      if (s.logits[i] > s.logits[ct]) ct = i;
      if (ref[i] > ref[rt]) rt = i;
    }
    printf("case %d: max abs diff %.5f, top C=%d PyTorch=%d\n", cases, md, ct, rt);
    if (md > worst) worst = md;
    if (ct != rt) worst_top++;
    cases++; free(ref);
  }
  printf("%d cases, worst max abs diff %.5f, top token differs in %d\n", cases, worst, worst_top);
  printf(worst < 1e-3 && !worst_top ? "PASS: C with the input vector matches PyTorch with the input\n" : "FAIL\n");
  return worst < 1e-3 && !worst_top ? 0 : 1;
}
