"""Speed steering, read side only: the direction is added while the model reads the request (prompt positions),
never while it writes the program, so the code itself is left alone and the dose can go higher.

Three directions, each per layer: calm->wild at the request's last token, fast-vs-slow where the speed number is
decided (just before the number after "move("), and the speed probe's own ridge weights. Reported per dose: how
many plain requests still give a program that runs, and the mean wheel speed those programs set.

    PYTHONPATH=src:. python -m research.robot.car_steer runs/ple-car-s0-best.pt --data-dir data/car --out runs/car-steer.json
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
from research.robot.car_inside import BASES, CALM, PLAIN, WILD, speed
from research.oled.gen import PROBE, reacts
from research.oled.inside import last_states, load_int4
from research.oled.lang import LangError, run


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
    pairs = [json.loads(l) for l in open(d / "val_pairs.jsonl")]

    n_prompt = {"n": 0}

    def score(p):
        n_prompt["n"] = len(tok.encode(f"# {p}\n").ids)
        prog = E.write(model, tok, eot, p, device, cfg["seq_len"])
        try:
            s = run(prog, PROBE, horizon=3000) if reacts(prog) else run(prog)
        except LangError:
            return None
        return speed(s)

    dirs = {}
    hw = last_states(model, tok, [b + w for b in BASES for w in WILD], device)
    hc = last_states(model, tok, [b + c for b in BASES for c in CALM], device)
    dirs["calm_to_wild"] = [hw[:, l].mean(0) - hc[:, l].mean(0) for l in range(L)]

    def top_speed(prog):
        ms = re.findall(r"move\((-?\d+), (-?\d+), (-?\d+)\)", prog)
        if not ms or "move(" in re.sub(r"move\(-?\d+, -?\d+, -?\d+\)", "", prog):
            return None
        return max(max(abs(int(a)), abs(int(c))) for a, _, c in ms)
    rows = [(p["prompt"], top_speed(p["program"])) for p in pairs]
    rows = [r for r in rows if r[1] is not None]
    random.Random(0).shuffle(rows)
    rows = rows[:1200]
    hs = last_states(model, tok, [p for p, _ in rows], device)
    y = torch.tensor([float(v) for _, v in rows])
    ridge = []
    for l in range(L):
        X = hs[:, l] - hs[:, l].mean(0)
        w = torch.linalg.solve(X.T @ X + 1.0 * torch.eye(X.shape[1]), X.T @ (y - y.mean()))
        ridge.append(w)
    dirs["speed_probe"] = ridge

    doses = [-4.0, -3.0, -2.0, -1.0, 0.0, 1.0, 2.0, 3.0, 4.0]
    result = {"plain": PLAIN, "doses": doses}
    for name, vs in dirs.items():
        result[name] = {}
        for l in range(L):
            v = (vs[l] / vs[l].norm()).to(device)

            def hook(m, i, o, g=0.0):
                n = n_prompt["n"]
                add = torch.zeros_like(o)
                add[:, :n] = g * o[:, :n].norm(dim=-1, keepdim=True) * v
                return o + add
            row = {}
            for g in doses:
                hk = model.blocks[l].register_forward_hook(lambda m, i, o, g=g: hook(m, i, o, g))
                try:
                    sp = [score(p) for p in PLAIN]
                finally:
                    hk.remove()
                ok = [x for x in sp if x is not None]
                row[g] = {"ran": len(ok), "mean_speed": round(float(np.mean(ok)), 1) if ok else None, "speeds": sp}
            result[name][l] = row
            print(f"{name} layer {l}: " + "  ".join(f"{g:+.0f}:{r['ran']}/12,{r['mean_speed']}" for g, r in row.items()),
                  flush=True)
    if args.out:
        Path(args.out).write_text(json.dumps(result, indent=1))


if __name__ == "__main__":
    sys.exit(main())
