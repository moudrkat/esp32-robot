#!/bin/sh
# From nothing to the model on the board's flash: make the data by rules, train, export, regenerate the headers.
# Needs a GPU for the training (about ten minutes); torch, numpy, tokenizers.
set -e
cd "$(dirname "$0")"
export PYTHONPATH=src:.
# SPEAK=cs ./train.sh trains the Czech one: the same programs asked for in Czech, its own vocabulary, into model-cs/
L=${SPEAK:-en}
if [ "$L" = cs ]; then D=data/car-cs; M=model-cs; T=carcs; G="--lang cs --bank research/robot/phrases_cs.jsonl"
else D=data/car; M=model; T=car; G="--bank research/robot/phrases.jsonl"; fi
python -m research.oled.gen --profile talk --cond --timed $G --n 800000 --out $D/pairs.jsonl
python -m research.oled.prepare --vocab 2048 --data-dir $D
python research/tinystories/train.py --arm ple --vocab 2048 --data-dir $D --d-model 192 --n-layers 6 --n-heads 6 \
  --ple-dim 64 --fixed-ffn 512 --seq-len 256 --batch-size 64 --steps 18000 --lr 1e-3 --warmup 400 --eval-every 1000 \
  --tag $T --n-cond 9 --cond-layer 0 --save-best
python -m research.oled.eval runs/ple-$T-s0-best.pt --vocab 2048 --data-dir $D --n 800
mkdir -p $M
python research/tinystories/export.py ple-$T-s0-best --tokenizer $D/vocab-2048/tokenizer.json --out $M
cp $D/vocab-2048/tokenizer.json $M/
python -m research.robot.cond_export runs/ple-$T-s0-best.pt --data-dir $D --out $M/cond.json
python -m research.robot.probe_export runs/ple-$T-s0-best.pt --data-dir $D --out $M/probes.json
[ "$L" = en ] && python tools/gen_headers.py      # the headers in the repo are the English model's; flash.sh makes the Czech ones
