#!/bin/sh
# A model for a robot of your own, from nothing: only your tricks, and "can't do that" for everything else.
#   ./mine.sh robots/plant        reads robots/plant/tricks.jsonl (and test.txt, if there is one)
#   MODEL=robots/plant/model ./flash.sh
# A 1M-parameter model, 600 steps: seconds on a GPU, a few minutes on a laptop-sized CPU. Needs torch, numpy, tokenizers.
set -e
cd "$(dirname "$0")"
export PYTHONPATH=src:.
R=${1:?which robot? ./mine.sh robots/plant}; R=${R%/}; [ -f "$R/tricks.jsonl" ] || { echo "no $R/tricks.jsonl"; exit 1; }
T=mine-$(basename "$R"); D=$R/data; M=$R/model; STEPS=${STEPS:-600}
rm -rf $D
python -m research.oled.gen --profile mine --tricks $R/tricks.jsonl --n 50000 --out $D/pairs.jsonl
python -m research.oled.prepare --vocab 512 --data-dir $D
python research/tinystories/train.py --arm ple --vocab 512 --data-dir $D --d-model 128 --n-layers 4 --n-heads 4 \
  --ple-dim 32 --fixed-ffn 384 --seq-len 128 --batch-size 64 --steps $STEPS --lr 2e-3 --warmup 100 --eval-every 300 \
  --tag $T --save-best
mkdir -p $M
python research/tinystories/export.py ple-$T-s0-best --tokenizer $D/vocab-512/tokenizer.json --out $M
cp $D/vocab-512/tokenizer.json $M/
# no moods and no probes in a robot of your own: the firmware gets them as zeros, so they do nothing
python - "$M" 128 <<'PY'
import json, sys
m, d = sys.argv[1], int(sys.argv[2])
ch = ["angry", "caution", "child", "cold", "happy", "low_battery", "playful", "scared", "tired"]
json.dump({"layer": 0, "channels": ch, "vectors": [[0.0] * d for _ in ch]}, open(f"{m}/cond.json", "w"))
json.dump({"layer": 0, "names": ["crash", "speed"], "w": [[0.0] * d, [0.0] * d], "b": [-1.0, 30.0]}, open(f"{m}/probes.json", "w"))
PY
[ -f "$R/test.txt" ] && python -m research.robot.talk_test runs/ple-$T-s0-best.pt $R/test.txt --data-dir $D --vocab 512 2>/dev/null || true
# the chip's own C code, run here on the same input: if it agrees with PyTorch, the chip will compute what you trained
if command -v cc >/dev/null 2>&1; then
  mkdir -p build && cc -O2 -o build/verify runtime/host_verify/verify.c -lm && ./build/verify $M/model.bin $M/golden.txt | tail -1
else echo "no C compiler here: skipped the check that the chip computes the same"; fi
echo "done: $M/. On the board: MODEL=$M ./flash.sh"
