"""Mixing two moods in the robot's head: is a mood a direction you can add, or a switch?

Two mood directions (as in car_mood.py: mood said in words minus the same request without it, at the request's
last token) are mixed as a*v1 + (1-a)*v2, normalised, and added read side only at one layer and dose to plain
requests. For each mix the programs' eyes (which mood, if any) and wheel speeds against the unsteered program are
counted. A direction you can compute with would give blends: eyes switching at some a, speeds sliding between the
two moods' factors. A switch gives one mood or the other, and nothing in between.

    PYTHONPATH=src:. python -m research.robot.car_mix runs/v6-ple-car-s0-best.pt --layer 3 --dose 2 --out runs/car-mix.json
"""
import argparse
import json
import random
import re
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import torch
from tokenizers import Tokenizer

from research.oled import eval as E
from research.robot.car_mood import BASE, TEST, shape, speeds
from research.oled.gen import MOOD_EYES, MOODS
from research.oled.inside import last_states, load_int4

PAIRS = [("angry", "tired"), ("happy", "scared"), ("angry", "happy"), ("tired", "cold")]
EYE_OF = {f'eyes("{e}")': m for m, e in MOOD_EYES.items()}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("ckpt")
    ap.add_argument("--data-dir", default="data/car")
    ap.add_argument("--vocab", type=int, default=2048)
    ap.add_argument("--layer", type=int, required=True)
    ap.add_argument("--dose", type=float, required=True)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    device = "cuda" if torch.cuda.is_available() else "cpu"
    d = Path(args.data_dir) / f"vocab-{args.vocab}"
    tok = Tokenizer.from_file(str(d / "tokenizer.json"))
    eot = tok.token_to_id("<|endoftext|>")
    model, cfg = load_int4(args.ckpt, device)
    rng = random.Random(0)
    n_prompt = {"n": 0}

    def write(p):
        n_prompt["n"] = len(tok.encode(f"# {p}\n").ids)
        return E.write(model, tok, eot, p, device, cfg["seq_len"])

    hb = last_states(model, tok, [b for b in BASE for _ in range(3)], device)[:, args.layer]
    vec = {}
    for mood, said in MOODS.items():
        hm = last_states(model, tok, [f"{rng.choice(said)}, {b}" for b in BASE for _ in range(3)], device)[:, args.layer]
        v = hm.mean(0) - hb.mean(0)
        vec[mood] = v / v.norm()
    plain = {p: write(p) for p in TEST}
    result = {"layer": args.layer, "dose": args.dose, "pairs": {}}
    for m1, m2 in PAIRS:
        rows = {}
        print(f"\n{m1} <-> {m2}  (cosine of the two directions {float(vec[m1] @ vec[m2]):.2f})")
        for a in (0.0, 0.25, 0.5, 0.75, 1.0):
            v = a * vec[m1] + (1 - a) * vec[m2]
            v = (v / v.norm()).to(device)

            def hook(m, i, o):
                out = o.clone()
                n = n_prompt["n"]
                out[:, :n] = o[:, :n] + args.dose * o[:, :n].norm(dim=-1, keepdim=True) * v
                return out
            hk = model.blocks[args.layer].register_forward_hook(hook)
            try:
                progs = {p: write(p) for p in TEST}
            finally:
                hk.remove()
            eyes = Counter(EYE_OF.get(q.split("\n", 1)[0], "none") for q in progs.values())
            ratios = [np.mean(speeds(q)) / np.mean(speeds(plain[p])) for p, q in progs.items()
                      if speeds(q) and speeds(plain[p]) and shape(q) == shape(plain[p])]
            intact = sum(shape(q) == shape(plain[p]) for p, q in progs.items())
            rows[a] = {"eyes": dict(eyes), "intact": intact,
                       "speed_ratio": round(float(np.mean(ratios)), 2) if ratios else None, "programs": progs}
            print(f"  {a:.2f} {m1} + {1 - a:.2f} {m2}: eyes {dict(eyes)}  intact {intact}/12  speed x{rows[a]['speed_ratio']}")
        result["pairs"][f"{m1}-{m2}"] = rows
    if args.out:
        Path(args.out).write_text(json.dumps(result, indent=1))


if __name__ == "__main__":
    sys.exit(main())
