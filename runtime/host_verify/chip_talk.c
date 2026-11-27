// The robot's whole path on a computer, with the chip's own code: a sentence goes through the device's tokenizer
// (generated/tokenizer_encoder.h), the model writes greedily as on the board, and the tokens come back through the
// device's vocabulary (generated/vocab.h). Same program as the Python side? Then the chip will write it too.
//   cc -O2 -I firmware/robot -o build/chip_talk runtime/host_verify/chip_talk.c -lm
//   build/chip_talk robots/plant/model/model.bin < sentences.txt
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "../llm.h"
#include "../bpe_tokenizer.h"
#include "generated/tokenizer_encoder.h"
#include "generated/vocab.h"

int main(int argc, char **argv) {
  if (argc < 2) { fprintf(stderr, "usage: %s <model.bin> < sentences\n", argv[0]); return 2; }
  FILE *f = fopen(argv[1], "rb"); if (!f) { perror(argv[1]); return 1; }
  fseek(f, 0, SEEK_END); size_t n = ftell(f); fseek(f, 0, SEEK_SET);
  uint8_t *buf = malloc(n); if (fread(buf, 1, n, f) != n) return 1; fclose(f);
  Model m; if (llm_load(buf, &m)) { fprintf(stderr, "bad model magic\n"); return 1; }
  if (VOCAB_N < m.out_vocab) { fprintf(stderr, "vocab.h has %d tokens, the model %d: headers are for another model\n", VOCAB_N, m.out_vocab); return 1; }
  BpeTokenizer tok;
  if (bpe_tokenizer_load(TOKENIZER_ENCODER_ASSET, TOKENIZER_ENCODER_ASSET_SIZE, &tok)) { fprintf(stderr, "tokenizer load failed\n"); return 1; }
  int eot = -1; const char *e = "<|endoftext|>";
  for (int v = 0; v < VOCAB_N; v++)
    if (VOCAB_OFF[v + 1] - VOCAB_OFF[v] == (int)strlen(e) && !memcmp(VOCAB_BLOB + VOCAB_OFF[v], e, strlen(e))) { eot = v; break; }
  int D = m.c.dim, L = m.c.n_layers, P = m.c.ple_dim, F = m.c.ffn, V = m.out_vocab, S = m.c.seq_len;
  Scratch s;
  s.x = malloc(D * 4); s.h = malloc((F > D ? F : D) * 4); s.qkv = malloc(3 * D * 4); s.att = malloc(D * 4);
  s.g1 = malloc(F * 4); s.g2 = malloc((P > F ? P : F) * 4);
  s.ple = malloc(L * P * 4); s.tmpP = malloc(L * P * 4); s.trow = malloc(L * P * 4);
  s.logits = malloc(V * 4); s.scores = malloc(S * 4);
  s.kcache = malloc((size_t)L * S * D * 4); s.vcache = malloc((size_t)L * S * D * 4);
  char line[300];
  while (fgets(line, sizeof line, stdin)) {
    line[strcspn(line, "\n")] = 0; if (!*line) continue;
    char wrapped[320]; snprintf(wrapped, sizeof wrapped, "# %s\n", line);
    uint16_t enc[96]; int k = bpe_encode_ascii(&tok, wrapped, enc, 96);
    printf("### %s\n", line);
    if (k <= 0) { printf("(ascii only, or prompt too long)\n\n"); continue; }
    int pos = 0;
    for (int i = 0; i < k; i++) llm_forward(&m, enc[i], pos++, &s);
    while (pos < S) {
      int best = 0; for (int v = 1; v < V; v++) if (s.logits[v] > s.logits[best]) best = v;
      if (best == eot) break;
      fwrite(VOCAB_BLOB + VOCAB_OFF[best], 1, VOCAB_OFF[best + 1] - VOCAB_OFF[best], stdout);
      llm_forward(&m, best, pos++, &s);
    }
    printf("\n");
  }
  return 0;
}
