// Host check for runtime/probe.h: the C model reads a few prompts with the probes on, and its scores at the last token
// must equal PyTorch's (research/robot/probe_export.py --golden writes the probes and the expected scores).
//
//   cc -O2 -DLLM_PROBE -o /tmp/probe_verify runtime/host_verify/probe_verify.c -lm
//   /tmp/probe_verify artifacts/car/model.bin probe_golden.txt
#include <stdio.h>
#include <stdlib.h>
#include "../llm.h"

int main(int argc, char **argv) {
  if (argc < 3) { fprintf(stderr, "usage: %s <model.bin> <probe_golden.txt>\n", argv[0]); return 2; }
  FILE *mf = fopen(argv[1], "rb"); if (!mf) { perror(argv[1]); return 1; }
  fseek(mf, 0, SEEK_END); size_t n = ftell(mf); fseek(mf, 0, SEEK_SET);
  uint8_t *buf = malloc(n); if (fread(buf, 1, n, mf) != n) return 1; fclose(mf);
  Model m; if (llm_load(buf, &m)) { fprintf(stderr, "bad magic\n"); return 1; }
  int D = m.c.dim, L = m.c.n_layers, P = m.c.ple_dim, F = m.c.ffn, V = m.out_vocab, S = m.c.seq_len;
  Scratch s;
  s.x = malloc(D * 4); s.h = malloc((F > D ? F : D) * 4); s.qkv = malloc(3 * D * 4); s.att = malloc(D * 4);
  s.g1 = malloc(F * 4); s.g2 = malloc((P > F ? P : F) * 4);
  s.ple = malloc(L * P * 4); s.tmpP = malloc(L * P * 4); s.trow = malloc(L * P * 4);
  s.logits = malloc(V * 4); s.scores = malloc(S * 4);
  s.kcache = calloc((size_t)L * S * D, 4); s.vcache = calloc((size_t)L * S * D, 4);

  FILE *g = fopen(argv[2], "r"); if (!g) { perror(argv[2]); return 1; }
  int layer, dim, k;
  if (fscanf(g, "%d %d %d", &layer, &dim, &k) != 3) return 1;
  float *w[PROBE_MAX];
  for (int j = 0; j < k; j++) { w[j] = malloc(dim * 4); for (int i = 0; i < dim; i++) if (fscanf(g, "%f", &w[j][i]) != 1) return 1; }
  g_probe.n = k; g_probe.layer = layer; g_probe.dim = dim;
  for (int j = 0; j < k; j++) { g_probe.w[j] = w[j]; if (fscanf(g, "%f", &g_probe.b[j]) != 1) return 1; }
  int T, cases = 0; double worst = 0;
  while (fscanf(g, "%d", &T) == 1) {
    int ids[512]; for (int i = 0; i < T; i++) if (fscanf(g, "%d", &ids[i]) != 1) return 1;
    float ref[PROBE_MAX]; for (int j = 0; j < k; j++) if (fscanf(g, "%f", &ref[j]) != 1) return 1;
    for (int pos = 0; pos < T; pos++) llm_forward(&m, ids[pos], pos, &s);
    printf("case %d:", cases);
    for (int j = 0; j < k; j++) {
      double d = fabs(g_probe.score[j] - ref[j]); if (d > worst) worst = d;
      printf("  C %.4f PyTorch %.4f", g_probe.score[j], ref[j]);
    }
    printf("\n"); cases++;
  }
  printf("%d cases, worst abs diff %.5f\n%s\n", cases, worst, worst < 1e-2 ? "PASS: C probes match PyTorch" : "FAIL");
  return worst < 1e-2 ? 0 : 1;
}
