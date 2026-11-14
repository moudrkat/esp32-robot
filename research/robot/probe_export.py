"""Fit the two probes the robot's eyes show before it writes, on the int4 weights the board runs, and export them.

  crash  "will this program end in a bump?": labelled by the program (drives forward until shaken()), not by words.
         Mean-difference direction at one layer; score > 0 means "crash" (threshold halfway between the classes).
  speed  "how fast will I drive?": ridge regression to the largest wheel speed the program sets.

Both read the residual after the same layer (the board reads one), at the request's last token, with no non-word
input. Reported on held-out requests: the crash probe's AUC and accuracy at its threshold, the speed probe's r and
mean error; then every line of the free-form files with both scores, to see what they do on real talk.

    PYTHONPATH=src:. python -m research.robot.probe_export runs/v10-ple-car-s0-best.pt --data-dir data/car --out artifacts/car/probes.json
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

from research.oled.eval import load
from research.oled.inside import auc
from research.tinystories.export import quant_pack

HITS = re.compile(r"move\((\d+), 0, -?\d+\)\n(while shaken\(\) == 0|while not \(shaken\(\)\)):")


def top_speed(prog):
    ms = re.findall(r"move\((-?\d+), (-?\d+), (-?\d+)\)", prog)
    if not ms or "move(" in re.sub(r"move\(-?\d+, -?\d+, -?\d+\)", "", prog):
        return None
    return max(max(abs(int(a)), abs(int(c))) for a, _, c in ms)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("ckpt")
    ap.add_argument("--data-dir", default="data/car")
    ap.add_argument("--layer", type=int, default=None, help="default: the layer where both probes do best together")
    ap.add_argument("--talk", nargs="*", default=["research/robot/car_talk.txt", "research/robot/robot_talk.txt"])
    ap.add_argument("--out", required=True)
    ap.add_argument("--golden", default=None, help="also write probes and expected scores for probe_verify.c")
    args = ap.parse_args()
    d = Path(args.data_dir) / "vocab-2048"
    tok = Tokenizer.from_file(str(d / "tokenizer.json"))
    model, cfg = load(args.ckpt, "cpu")
    sd = model.state_dict()
    for k, v in sd.items():                      # the int4 weights the chip runs
        if v.dim() == 2 and "norm" not in k and not k.startswith("cond_proj"):
            sd[k] = torch.as_tensor(quant_pack(v)[2]).reshape(v.shape).to(v.dtype)
    model.load_state_dict(sd)
    L = len(model.blocks)

    @torch.no_grad()
    def states(prompts):
        out, cache = [], []
        hooks = [b.register_forward_hook(lambda m, i, o: cache.append(o[0, -1].float())) for b in model.blocks]
        try:
            for p in prompts:
                cache.clear()
                model(torch.tensor([tok.encode(f"# {p}\n").ids]))
                out.append(torch.stack(cache))
        finally:
            for h in hooks:
                h.remove()
        return torch.stack(out)                  # [n, L, D]

    pairs = [json.loads(l) for l in open(d / "val_pairs.jsonl")]
    pairs = [p for p in pairs if "cond" not in p]
    rng = random.Random(0)
    rng.shuffle(pairs)
    pos = [p["prompt"] for p in pairs if HITS.search(p["program"])][:300]
    # the negatives drive forward too and stop on their own: otherwise "will I bump" is learned as "will I move"
    fwd = lambda prog: bool(re.search(r"move\(([1-9]\d*), 0, ", prog))
    neg = [p["prompt"] for p in pairs if not HITS.search(p["program"]) and fwd(p["program"])][:300]
    n = min(len(pos), len(neg))
    hp, hn = states(pos[:n]), states(neg[:n])
    h = n // 2
    rows = [(p["prompt"], top_speed(p["program"])) for p in pairs]
    rows = [r for r in rows if r[1] is not None][:1200]
    hs = states([p for p, _ in rows])
    y = torch.tensor([float(v) for _, v in rows])
    k = len(rows) * 2 // 3
    per_layer = []
    for l in range(L):
        u = hp[:h, l].mean(0) - hn[:h, l].mean(0)
        u = u / u.norm()
        a = float(auc((hp[h:, l] @ u).numpy(), (hn[h:, l] @ u).numpy()))
        X = hs[:, l]
        mu = X[:k].mean(0)
        Xc = X[:k] - mu
        w = torch.linalg.solve(Xc.T @ Xc + torch.eye(X.shape[1]), Xc.T @ (y[:k] - y[:k].mean()))
        pred = (X[k:] - mu) @ w + y[:k].mean()
        r = float(np.corrcoef(pred.numpy(), y[k:].numpy())[0, 1])
        per_layer.append({"layer": l, "crash_auc": round(a, 3), "speed_r": round(r, 3),
                          "speed_mae": round(float((pred - y[k:]).abs().mean()), 1)})
    print("by layer:", per_layer)
    lay = args.layer if args.layer is not None else max(range(L), key=lambda l: per_layer[l]["crash_auc"] + per_layer[l]["speed_r"])
    u = hp[:h, lay].mean(0) - hn[:h, lay].mean(0)
    u = u / u.norm()
    t = float(((hp[:h, lay] @ u).mean() + (hn[:h, lay] @ u).mean()) / 2)
    acc = float(((hp[h:, lay] @ u > t).float().mean() + (hn[h:, lay] @ u <= t).float().mean()) / 2)
    X = hs[:, lay]
    mu = X[:k].mean(0)
    Xc = X[:k] - mu
    w = torch.linalg.solve(Xc.T @ Xc + torch.eye(X.shape[1]), Xc.T @ (y[:k] - y[:k].mean()))
    b = float(y[:k].mean() - mu @ w)
    print(f"layer {lay}: crash AUC {per_layer[lay]['crash_auc']}, accuracy at threshold {acc:.3f} (n={n - h} per class held out); "
          f"speed r {per_layer[lay]['speed_r']}, mean error {per_layer[lay]['speed_mae']}")
    lines = [l.strip() for f in args.talk if Path(f).exists() for l in open(f) if l.strip()]
    ht = states(lines)[:, lay]
    for line, c, s_ in zip(lines, (ht @ u - t).tolist(), (ht @ w + b).tolist()):
        print(f"  crash {c:+6.2f}  speed {s_:5.0f}  {line}")
    out = {"layer": lay, "names": ["crash", "speed"], "w": [u.tolist(), w.tolist()], "b": [-t, b],
           "held_out": {"crash_auc": per_layer[lay]["crash_auc"], "crash_accuracy": round(acc, 3),
                        "speed_r": per_layer[lay]["speed_r"], "speed_mae": per_layer[lay]["speed_mae"]},
           "by_layer": per_layer}
    Path(args.out).write_text(json.dumps(out))
    print("wrote", args.out)
    if args.golden:                              # for runtime/host_verify/probe_verify.c: the probes and expected scores
        with open(args.golden, "w") as f:
            f.write(f"{lay} {u.numel()} 2\n" + " ".join(f"{x:.7g}" for x in u.tolist()) + "\n"
                    + " ".join(f"{x:.7g}" for x in w.tolist()) + f"\n{-t:.7g} {b:.7g}\n")
            for p in ["go", "crash into the wall", "drive forward slowly", "floor it", "smash into the door lol"]:
                ids = tok.encode(f"# {p}\n").ids
                x = states([p])[0, lay]
                f.write(f"{len(ids)} {' '.join(map(str, ids))}\n{float(x @ u - t):.7g} {float(x @ w + b):.7g}\n")
        print("wrote", args.golden)


if __name__ == "__main__":
    sys.exit(main())
