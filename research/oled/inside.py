"""Look inside the oled model, on the int4 weights the board runs.

Two measurements, both at the last token of the request (the newline after "# <request>"), where the model has
read everything and writes nothing yet:

  probe  "can it draw this?": the mean difference between requests it answers with "?" (unknown family) and
         requests for shapes it can draw, per layer; AUC on held-out requests.
  steer  "small -> big": the mean difference between "draw a big X" and "draw a small X", added after one layer
         at every position as gamma * ||x|| * v_hat (the board's relative dose, runtime/steer.h). For neutral
         requests ("draw a house") the steered program is run; reported: how many still run, and how wide the
         picture is.

    PYTHONPATH=src:. python -m research.oled.inside runs/ple-oled-s0-best.pt --out runs/oled-inside.json
"""
import argparse
import json
import random
import sys
from pathlib import Path

import numpy as np
import torch
from tokenizers import Tokenizer

from research.oled import eval as E
from research.oled.lang import LangError, W, run
from research.tinystories.export import quant_pack

ROOT = Path(__file__).resolve().parents[2]
SHAPES = ["circle", "square", "triangle", "heart", "house", "sun", "star", "smiley"]
DRAWABLE = {"circle", "square", "triangle", "heart", "house", "sun", "star", "smiley", "box", "rings", "row", "arrow"}


def load_int4(ckpt, device):
    model, cfg = E.load(ckpt, "cpu")
    sd = model.state_dict()
    for k, v in sd.items():
        if v.dim() == 2 and "norm" not in k:
            sd[k] = torch.as_tensor(quant_pack(v)[2]).reshape(v.shape).to(v.dtype)
    model.load_state_dict(sd)
    return model.to(device).eval(), cfg


@torch.no_grad()
def last_states(model, tok, prompts, device):
    """Residual after each block at the request's last token: [n, layers, d]."""
    out, cache = [], []
    hooks = [b.register_forward_hook(lambda m, i, o: cache.append(o[0, -1].float().cpu())) for b in model.blocks]
    try:
        for p in prompts:
            cache.clear()
            model(torch.tensor([tok.encode(f"# {p}\n").ids], device=device))
            out.append(torch.stack(cache))
    finally:
        for h in hooks:
            h.remove()
    return torch.stack(out)


def auc(pos, neg):
    s = np.concatenate([pos, neg])
    r = s.argsort().argsort() + 1
    return (r[:len(pos)].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg))


def width(screen):
    px = np.frombuffer(screen.frames[-1][1], dtype=np.uint8).reshape(-1, W)
    cols = np.where(px.any(0))[0]
    return int(cols[-1] - cols[0] + 1) if len(cols) else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("ckpt")
    ap.add_argument("--vocab", type=int, default=2048)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    device = "cuda" if torch.cuda.is_available() else "cpu"
    d = ROOT / "data" / "oled" / f"vocab-{args.vocab}"
    tok = Tokenizer.from_file(str(d / "tokenizer.json"))
    eot = tok.token_to_id("<|endoftext|>")
    model, cfg = load_int4(args.ckpt, device)
    L = len(model.blocks)
    rng = random.Random(0)
    result = {}

    # ---- probe: unknown vs drawable, held-out requests only
    pairs = [json.loads(l) for l in open(d / "val_pairs.jsonl")]
    unk = [p["prompt"] for p in pairs if p["family"] == "unknown"]
    drw = [p["prompt"] for p in pairs if p["family"] in DRAWABLE]
    rng.shuffle(unk), rng.shuffle(drw)
    n = min(len(unk), len(drw), 400)
    unk, drw = unk[:n], drw[:n]
    hu, hd = last_states(model, tok, unk, device), last_states(model, tok, drw, device)
    h = n // 2
    probe = []
    for l in range(L):
        v = hu[:h, l].mean(0) - hd[:h, l].mean(0)
        a = auc((hu[h:, l] @ v).numpy(), (hd[h:, l] @ v).numpy())
        probe.append(round(float(a), 3))
    result["probe_auc_by_layer"] = probe
    result["probe_n"] = {"train": 2 * h, "test": 2 * (n - h)}
    print("probe 'can it draw this?' AUC by layer:", probe, f"(n={n} per class)")

    # ---- steer: small -> big
    wheres = ["", " in the middle", " on the left", " on the right"]
    verbs = ["draw", "make", "show"]
    small = [f"{v} a small {s}{w}" for s in SHAPES for v in verbs for w in wheres]
    big = [f"{v} a big {s}{w}" for s in SHAPES for v in verbs for w in wheres]
    hs, hb = last_states(model, tok, small, device), last_states(model, tok, big, device)
    neutral = [f"draw a {s}" for s in SHAPES]
    base = {}
    for p in neutral:
        base[p] = width(run(E.write(model, tok, eot, p, device, cfg["seq_len"])))
    doses = [-1.0, -0.5, -0.25, 0.0, 0.25, 0.5, 1.0, 1.5, 2.0]
    steer = {}
    for l in range(L):
        v = (hb[:, l].mean(0) - hs[:, l].mean(0))
        v = (v / v.norm()).to(device)
        row = {}
        for g in doses:
            def hook(m, i, o, g=g):
                return o + g * o.norm(dim=-1, keepdim=True) * v
            hk = model.blocks[l].register_forward_hook(hook)
            ran, wd = 0, []
            try:
                for p in neutral:
                    prog = E.write(model, tok, eot, p, device, cfg["seq_len"])
                    try:
                        wd.append(width(run(prog)) - base[p])
                        ran += 1
                    except LangError:
                        pass
            finally:
                hk.remove()
            row[g] = {"ran": ran, "of": len(neutral), "mean_width_change": round(float(np.mean(wd)), 1) if wd else None}
        steer[l] = row
        print(f"layer {l}: " + "  ".join(f"{g:+.2f}:{r['ran']}/{r['of']},{r['mean_width_change']}" for g, r in row.items()))
    result["steer_small_to_big"] = {"neutral": neutral, "base_width": base, "by_layer": steer}
    if args.out:
        Path(args.out).write_text(json.dumps(result, indent=1))


if __name__ == "__main__":
    sys.exit(main())
