"""Steering a finished model vs a learned non-word input, seen from inside: UMAP of the state the model writes
from (last block, the request's last token), for the same 40 plain requests at 11 strengths.

Left: v6 (no input channel), the "angry" direction (mood said in words minus the same request without it, layer 3)
added read side at doses 0..4. Right: v9, the learned "angry" input at strengths 0..1. A scale shows up as a
smooth run of colour along each request; a switch as two islands.

    PYTHONPATH=src:. python -m research.robot.car_umap --steer-ckpt runs/v6-ple-car-s0-best.pt --steer-data data/car-v6 \
        --input-ckpt runs/v9-ple-car-s0-best.pt --input-data data/car --out runs/car-umap.png
"""
import argparse
import json
import random
import sys
from pathlib import Path

import numpy as np
import torch
from tokenizers import Tokenizer

from research.robot.car_mood import BASE, TEST
from research.oled.gen import MOODS
from research.oled.inside import last_states, load_int4

REQS = BASE + TEST + ["drive forward 3 seconds", "turn right 90 degrees", "do a square", "zigzag twice", "go back a bit",
                      "spin around", "look left", "drive in a circle"]


def final_states(model, tok, prompts, device, hook_layer=None, add=None, cond=None):
    out = []
    with torch.no_grad():
        for p in prompts:
            ids = torch.tensor([tok.encode(f"# {p}\n").ids], device=device)
            hk = None
            if add is not None:
                hk = model.blocks[hook_layer].register_forward_hook(
                    lambda m, i, o: o + add * o.norm(dim=-1, keepdim=True))
            cache = []
            h2 = model.blocks[-1].register_forward_hook(lambda m, i, o: cache.append(o[0, -1].float().cpu()))
            c = None if cond is None else torch.tensor(cond, device=device).expand(1, ids.shape[1], -1)
            model(ids, cond=c) if cond is not None else model(ids)
            h2.remove()
            if hk:
                hk.remove()
            out.append(cache[0])
    return torch.stack(out).numpy()


def at_number_states(model, tok, eot, reqs, levels, device, seq_len, steer=None, chans=None, mood=None):
    """For each request and strength: the program the model writes under it, then the state (last block) at the
    token just before the first speed number, i.e. right after "move(". Skips programs without move()."""
    from research.oled import eval as E
    X, S = [], []
    for a in levels:
        for p in reqs:
            hk = None
            cond = None
            if steer is not None:
                layer, v = steer
                hk = model.blocks[layer].register_forward_hook(lambda m, i, o, a=a: o + 4.0 * a * o.norm(dim=-1, keepdim=True) * v)
            else:
                cond = [a if k == mood else 0.0 for k in chans]
            try:
                prog = E.write(model, tok, eot, p, device, seq_len, cond=cond)
                if "move(" not in prog:
                    continue
                prefix = f"# {p}\n" + prog[:prog.index("move(") + 5]
                ids = tok.encode(prefix).ids
                cache = []
                h2 = model.blocks[-1].register_forward_hook(lambda m, i, o: cache.append(o[0, -1].float().cpu()))
                with torch.no_grad():
                    t = torch.tensor([ids], device=device)
                    c = None if cond is None else torch.tensor(cond, device=device).expand(1, t.shape[1], -1)
                    model(t, cond=c) if c is not None else model(t)
                h2.remove()
                X.append(cache[0].numpy()); S.append(a)
            finally:
                if hk:
                    hk.remove()
    return np.array(X), np.array(S)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--steer-ckpt", required=True)
    ap.add_argument("--steer-data", required=True)
    ap.add_argument("--input-ckpt", required=True)
    ap.add_argument("--input-data", required=True)
    ap.add_argument("--mood", default="angry")
    ap.add_argument("--out", required=True)
    ap.add_argument("--at", default="end", choices=["end", "number"], help="end of the request, or just before the speed number")
    args = ap.parse_args()
    import umap
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    device = "cuda" if torch.cuda.is_available() else "cpu"
    reqs = list(dict.fromkeys(REQS))[:40]
    levels = np.linspace(0, 1, 11)

    # left: steering a finished model
    d = Path(args.steer_data) / "vocab-2048"
    tok = Tokenizer.from_file(str(d / "tokenizer.json"))
    model, cfg = load_int4(args.steer_ckpt, device)
    rng = random.Random(0)
    hm = last_states(model, tok, [f"{rng.choice(MOODS[args.mood])}, {b}" for b in BASE for _ in range(3)], device)[:, 3]
    hb = last_states(model, tok, [b for b in BASE for _ in range(3)], device)[:, 3]
    v = hm.mean(0) - hb.mean(0)
    v = (v / v.norm()).to(device)
    eot = tok.token_to_id("<|endoftext|>")
    if args.at == "number":
        left, sl = at_number_states(model, tok, eot, reqs, levels, device, cfg["seq_len"], steer=(3, v))
    else:
        left = np.concatenate([final_states(model, tok, reqs, device, 3, 4.0 * a * v) for a in levels])
        sl = np.repeat(levels, len(reqs))

    # right: the learned input
    d = Path(args.input_data) / "vocab-2048"
    tok = Tokenizer.from_file(str(d / "tokenizer.json"))
    model, cfg = load_int4(args.input_ckpt, device)
    ch = json.loads((d / "manifest.json").read_text())["cond_channels"]
    eot = tok.token_to_id("<|endoftext|>")
    if args.at == "number":
        right, sr = at_number_states(model, tok, eot, reqs, levels, device, cfg["seq_len"], chans=ch, mood=args.mood)
    else:
        right = np.concatenate([final_states(model, tok, reqs, device, cond=[a if k == args.mood else 0.0 for k in ch])
                                for a in levels])
        sr = np.repeat(levels, len(reqs))
    print(f"points: left {len(left)}, right {len(right)} (of {len(reqs) * len(levels)}; programs without move() skipped)")
    fig, axes = plt.subplots(1, 2, figsize=(11, 5.2), dpi=150)
    where = "the request's last token" if args.at == "end" else "just before the speed number"
    for ax, X, strength, title, unit in ((axes[0], left, sl, "steering a finished model (v6)", "dose 0 → 4"),
                                         (axes[1], right, sr, "learned non-word input (v9)", "strength 0 → 1")):
        Y = umap.UMAP(n_neighbors=15, min_dist=0.1, random_state=0).fit_transform(X)
        if args.at == "end":
            for j in range(len(reqs)):                 # each request's path through the strengths
                idx = [j + i * len(reqs) for i in range(len(levels))]
                ax.plot(Y[idx, 0], Y[idx, 1], color="#c9c9cf", lw=0.6, zorder=1)
        sc = ax.scatter(Y[:, 0], Y[:, 1], c=strength, cmap="Blues", vmin=-0.15, vmax=1, s=14,
                        edgecolors="white", linewidths=0.4, zorder=2)
        ax.set_title(f"{title}\n\"{args.mood}\", {unit}", fontsize=11)
        ax.set_xticks([]), ax.set_yticks([])
        for s in ax.spines.values():
            s.set_color("#d9dade")
    cb = fig.colorbar(sc, ax=axes, fraction=0.025, pad=0.02)
    cb.set_label("strength of \"" + args.mood + "\" (light = none, dark = full)")
    fig.suptitle(f"Same 40 requests, state at {where}." + (" Grey lines join one request across strengths." if args.at == "end" else ""),
                 fontsize=10, y=0.02)
    fig.savefig(args.out, bbox_inches="tight")
    print("wrote", args.out)


if __name__ == "__main__":
    sys.exit(main())
