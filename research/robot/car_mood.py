"""Can a mood be put into the robot's head without words? Measured on the int4 weights the board runs.

For each mood (angry, tired, scared, happy, cold) the direction is the mean state of requests that say the mood
("you're angry, turn left") minus the same requests without it, at the request's last token, per layer. It is then
added, read side only (prompt positions, the way the board can do it once per request), to plain requests that
never mention a mood. For every program written:

  eyes    does it start with that mood's eyes, as when the mood is said in words?
  speed   the wheel speeds it sets, against the same request unsteered (the mood scales them: angry x1.5,
          tired x0.5, ...)
  intact  is it still the program asked for (same moves in the same order, speeds aside)?

The words themselves are the reference: the same plain requests with the mood said in front.

    PYTHONPATH=src:. python -m research.robot.car_mood runs/ple-car-s0-best.pt --data-dir data/car --out runs/car-mood.json
"""
import argparse
import json
import random
import re
import sys
from pathlib import Path

import numpy as np
import torch
from tokenizers import Tokenizer

from research.oled import eval as E
from research.oled.gen import MOOD_EYES, MOOD_SOUND, MOODS
from research.oled.inside import last_states, load_int4

BASE = ["drive forward 2 seconds", "turn left", "go", "drive in a square", "back up a bit", "turn right",
        "drive forward", "go to the door", "spin around twice", "drive in a circle", "reverse 3 seconds", "zigzag",
        "honk", "look left", "wave", "go forward a bit", "turn around", "drive forward 3 seconds", "patrol back and forth",
        "go to the wall"]
TEST = ["drive forward 1 second", "turn left 90 degrees", "go straight a bit", "do a little dance", "drive in a triangle",
        "back up 2 seconds", "turn right", "honk twice", "look right", "go to the couch", "spin around", "go forward"]


def shape(prog):
    """The program with its numbers in move() replaced: what it does, speeds aside."""
    body = prog
    if body.startswith("eyes("):                       # a mood's preamble: its eyes, then its sound
        body = body.split("\n", 1)[1] if "\n" in body else ""
        for snd in MOOD_SOUND.values():
            if body.startswith(snd):
                body = body[len(snd):]
                break
    return re.sub(r"move\((-?\d+), (-?\d+), (-?\d+)\)", lambda m: f"move({np.sign(int(m.group(1)))}, 0, {np.sign(int(m.group(3)))})", body)


def speeds(prog):
    return [max(abs(int(a)), abs(int(c))) for a, _, c in re.findall(r"move\((-?\d+), (-?\d+), (-?\d+)\)", prog)]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("ckpt")
    ap.add_argument("--data-dir", default="data/car")
    ap.add_argument("--vocab", type=int, default=2048)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    device = "cuda" if torch.cuda.is_available() else "cpu"
    d = Path(args.data_dir) / f"vocab-{args.vocab}"
    tok = Tokenizer.from_file(str(d / "tokenizer.json"))
    eot = tok.token_to_id("<|endoftext|>")
    model, cfg = load_int4(args.ckpt, device)
    L = len(model.blocks)
    rng = random.Random(0)
    n_prompt = {"n": 0}

    def write(p):
        n_prompt["n"] = len(tok.encode(f"# {p}\n").ids)
        return E.write(model, tok, eot, p, device, cfg["seq_len"])

    plain = {p: write(p) for p in TEST}
    result = {"test": TEST, "plain": plain, "moods": {}}
    for mood, said in MOODS.items():
        eye = f'eyes("{MOOD_EYES[mood]}")'
        moody = [f"{rng.choice(said)}, {b}" for b in BASE for _ in range(3)]
        hm = last_states(model, tok, moody, device)
        hb = last_states(model, tok, [b for b in BASE for _ in range(3)], device)
        # the reference: the mood in words
        words = {p: write(f"{said[0]}, {p}") for p in TEST}
        ref_eyes = sum(w.startswith(eye) for w in words.values())
        print(f"\n{mood}: in words, {ref_eyes}/{len(TEST)} start with {eye}", flush=True)
        res = {"words": words, "by_layer": {}}
        for l in range(L):
            v = hm[:, l].mean(0) - hb[:, l].mean(0)
            v = (v / v.norm()).to(device)
            row = {}
            for g in (1.0, 2.0, 3.0, 4.0):
                def hook(m, i, o, g=g):
                    out = o.clone()
                    n = n_prompt["n"]
                    out[:, :n] = o[:, :n] + g * o[:, :n].norm(dim=-1, keepdim=True) * v
                    return out
                hk = model.blocks[l].register_forward_hook(hook)
                try:
                    progs = {p: write(p) for p in TEST}
                finally:
                    hk.remove()
                n_eyes = sum(q.startswith(eye) for q in progs.values())
                intact = sum(shape(q) == shape(plain[p]) for p, q in progs.items())
                ratios = [np.mean(speeds(q)) / np.mean(speeds(plain[p])) for p, q in progs.items()
                          if speeds(q) and speeds(plain[p]) and shape(q) == shape(plain[p])]
                row[g] = {"eyes": n_eyes, "intact": intact, "speed_ratio": round(float(np.mean(ratios)), 2) if ratios else None,
                          "programs": progs}
            res["by_layer"][l] = row
            print(f"  layer {l}: " + "  ".join(f"+{g:.0f}: eyes {r['eyes']}/12 intact {r['intact']}/12 speed x{r['speed_ratio']}"
                                               for g, r in row.items()), flush=True)
        result["moods"][mood] = res
    if args.out:
        Path(args.out).write_text(json.dumps(result, indent=1))


if __name__ == "__main__":
    sys.exit(main())
