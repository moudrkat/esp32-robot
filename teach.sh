#!/bin/sh
# Franta learns your tricks: research/robot/tricks.jsonl, one line each (a program, and the ways to ask for it).
# Starts from the finished model (model/franta.pt), so a few hundred steps do: about a minute on a GPU.
#   ./teach.sh            then   MODEL=model-teach ./flash.sh
# Needs torch, numpy, tokenizers. English only for now.
set -e
cd "$(dirname "$0")"
export PYTHONPATH=src:.
D=data/teach; M=model-teach; T=teach; STEPS=${STEPS:-500}
rm -rf $D; mkdir -p $D/vocab-2048; cp model/tokenizer.json $D/vocab-2048/      # Franta's own words, so his weights still fit
python -m research.oled.gen --profile talk --cond --timed --bank research/robot/phrases.jsonl \
  --tricks research/robot/tricks.jsonl --n ${N:-30000} --out $D/pairs.jsonl
python -m research.oled.prepare --vocab 2048 --data-dir $D
python research/tinystories/train.py --arm ple --vocab 2048 --data-dir $D --d-model 192 --n-layers 6 --n-heads 6 \
  --ple-dim 64 --fixed-ffn 512 --seq-len 256 --batch-size 64 --steps $STEPS --lr 3e-4 --warmup 50 --eval-every 250 \
  --tag $T --n-cond 9 --cond-layer 0 --save-best --init model/franta.pt
mkdir -p $M
python research/tinystories/export.py ple-$T-s0-best --tokenizer $D/vocab-2048/tokenizer.json --out $M
cp $D/vocab-2048/tokenizer.json $M/
python -m research.robot.cond_export runs/ple-$T-s0-best.pt --data-dir $D --out $M/cond.json
python -m research.robot.probe_export runs/ple-$T-s0-best.pt --data-dir $D --out $M/probes.json
python -m research.robot.talk_test runs/ple-$T-s0-best.pt research/robot/tricks_test.txt --data-dir $D 2>/dev/null || true
echo "done: $M/. On the board: MODEL=$M ./flash.sh"
