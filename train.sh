#!/bin/sh
# From nothing to the brain on the board's flash: make the data by rules, train, export, regenerate the headers.
# Needs a GPU for the training (about ten minutes); torch, numpy, tokenizers.
set -e
cd "$(dirname "$0")"
export PYTHONPATH=src:.
python -m research.oled.gen --profile car --cond --n 500000 --out data/car/pairs.jsonl
python -m research.oled.prepare --vocab 2048 --data-dir data/car
python research/tinystories/train.py --arm ple --vocab 2048 --data-dir data/car --d-model 192 --n-layers 6 --n-heads 6 \
  --ple-dim 64 --fixed-ffn 512 --seq-len 256 --batch-size 64 --steps 12000 --lr 1e-3 --warmup 400 --eval-every 1000 \
  --tag car --n-cond 9 --cond-layer 0 --save-best
python -m research.oled.eval runs/ple-car-s0-best.pt --vocab 2048 --data-dir data/car --n 800
python research/tinystories/export.py ple-car-s0-best --tokenizer data/car/vocab-2048/tokenizer.json --out model
python -m research.robot.cond_export runs/ple-car-s0-best.pt --data-dir data/car --out model/cond.json
python -m research.robot.probe_export runs/ple-car-s0-best.pt --data-dir data/car --out model/probes.json
python tools/gen_headers.py
