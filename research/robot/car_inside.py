"""Look inside the car model, on the int4 weights the board runs.

  steer  "calm -> wild": the mean difference between requests said wildly ("... like a maniac", "full speed") and
         the same requests said calmly ("... slowly", "gently"), at the request's last token, per layer. Added after
         one layer at every position as gamma * ||x|| * v_hat, the board's relative dose (runtime/steer.h), while the
         model writes programs for plain requests ("drive forward 2 seconds", "turn left"...). Reported per layer and
         dose: how many programs still run, and the mean wheel speed they set (largest |forward| or |turn| in a run).
  probe  "can I do this?": mean difference between requests for things the car has no hardware for ("fly", "make
         me coffee") and everything else, per layer; AUC on held-out requests, and the score of each line of a
         free-form file, so the eyes can show doubt before the program is written.
  crash  "is this going to end in a bump?": labelled by the program, not by the words: drives forward until
         shaken() says it hit something. Mean-difference direction, AUC on held-out requests, free-form scores.
  speed  "how fast will I go?": ridge regression from the state to the largest wheel speed the program sets
         (constant move() arguments only), per layer; R and mean absolute error on held-out requests, and on the
         free-form lines against the speed the model then actually wrote.

    PYTHONPATH=src:. python -m research.robot.car_inside runs/ple-car-s0-best.pt --data-dir data/car --out runs/car-inside.json
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
from research.oled.gen import PROBE, reacts
from research.oled.inside import auc, last_states, load_int4
from research.oled.lang import LangError, run

PLAIN = ["drive forward 2 seconds", "turn left", "go", "drive in a square", "back up a bit", "do a little dance",
         "zigzag", "turn right", "drive forward a bit", "spin around", "go to the wall", "do a lap"]
BASES = ["drive forward 2 seconds", "turn left", "go", "drive in a square", "back up a bit", "turn right",
         "drive forward", "go to the door", "spin around twice", "drive in a circle", "reverse 3 seconds", "zigzag"]
WILD = [" like a maniac", " full speed", " super fast", " like a crazy person", " as fast as you can", "!!!"]
CALM = [" slowly", " gently", " nice and slow", " very slowly", " carefully", " like a snail"]


def speed(screen):
    """The largest wheel command in a run: max over the log of |forward| and |turn|."""
    return max(max(abs(io[5]), abs(io[7])) for _, io in screen.io_log)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("ckpt")
    ap.add_argument("--data-dir", default="data/car")
    ap.add_argument("--vocab", type=int, default=2048)
    ap.add_argument("--talk", nargs="*", default=["research/robot/car_talk.txt", "research/robot/robot_talk.txt"])
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    device = "cuda" if torch.cuda.is_available() else "cpu"
    d = Path(args.data_dir)
    tok = Tokenizer.from_file(str(d / f"vocab-{args.vocab}" / "tokenizer.json"))
    eot = tok.token_to_id("<|endoftext|>")
    model, cfg = load_int4(args.ckpt, device)
    L = len(model.blocks)
    result = {}

    def write(p):
        return E.write(model, tok, eot, p, device, cfg["seq_len"])

    def score(p):
        prog = write(p)
        try:
            s = run(prog, PROBE, horizon=3000) if reacts(prog) else run(prog)
        except LangError:
            return None
        return speed(s)

    # ---- steer: calm -> wild
    wild = [b + w for b in BASES for w in WILD]
    calm = [b + c for b in BASES for c in CALM]
    hw, hc = last_states(model, tok, wild, device), last_states(model, tok, calm, device)
    base = [score(p) for p in PLAIN]
    print("plain speeds:", dict(zip(PLAIN, base)))
    doses = [-1.0, -0.5, -0.25, 0.0, 0.25, 0.5, 1.0]
    steer = {}
    for l in range(L):
        v = hw[:, l].mean(0) - hc[:, l].mean(0)
        v = (v / v.norm()).to(device)
        row = {}
        for g in doses:
            hk = model.blocks[l].register_forward_hook(lambda m, i, o, g=g: o + g * o.norm(dim=-1, keepdim=True) * v)
            try:
                sp = [score(p) for p in PLAIN]
            finally:
                hk.remove()
            ok = [x for x in sp if x is not None]
            row[g] = {"ran": len(ok), "of": len(PLAIN), "mean_speed": round(float(np.mean(ok)), 1) if ok else None,
                      "speeds": sp}
        steer[l] = row
        print(f"layer {l}: " + "  ".join(f"{g:+.2f}:{r['ran']}/{r['of']},{r['mean_speed']}" for g, r in row.items()), flush=True)
    result["steer_calm_to_wild"] = {"plain": PLAIN, "base_speed": base, "by_layer": steer}

    # ---- steer, second try: the direction where the speed is decided, at the "move(" just before the number
    vpairs = [json.loads(l) for l in open(d / f"vocab-{args.vocab}" / "val_pairs.jsonl")]
    def at_move(doc):
        ids = tok.encode(doc).ids
        for i in range(1, len(ids)):
            if tok.decode(ids[:i]).endswith("move("):
                return ids[:i]
        return None
    def first_speed(prog):
        m_ = re.search(r"move\((-?\d+), 0, ", prog)
        return abs(int(m_.group(1))) if m_ else None
    fast, slow = [], []
    for p in vpairs:
        sp_ = first_speed(p["program"])
        if sp_ is None or sp_ == 0:
            continue
        (fast if sp_ >= 90 else slow if sp_ <= 30 else []).append(p["doc"])
    fast, slow = fast[:300], slow[:300]
    def states_at(docs):
        out, cache = [], []
        hooks = [b.register_forward_hook(lambda m, i, o: cache.append(o[0, -1].float().cpu())) for b in model.blocks]
        try:
            with torch.no_grad():
                for doc in docs:
                    ids = at_move(doc)
                    if ids is None or len(ids) >= cfg["seq_len"]:
                        continue
                    cache.clear()
                    model(torch.tensor([ids], device=device))
                    out.append(torch.stack(cache))
        finally:
            for hk in hooks:
                hk.remove()
        return torch.stack(out)
    hf_, hs_ = states_at(fast), states_at(slow)
    print(f"speed-decision states: {len(hf_)} fast, {len(hs_)} slow")
    doses2 = [-1.0, -0.8, -0.6, -0.4, -0.2, 0.0, 0.2, 0.4, 0.6, 0.8, 1.0]
    steer2 = {}
    for l in range(L):
        v = hf_[:, l].mean(0) - hs_[:, l].mean(0)
        v = (v / v.norm()).to(device)
        row = {}
        for g in doses2:
            hk = model.blocks[l].register_forward_hook(lambda m, i, o, g=g: o + g * o.norm(dim=-1, keepdim=True) * v)
            try:
                sp = [score(p) for p in PLAIN]
            finally:
                hk.remove()
            ok = [x for x in sp if x is not None]
            row[g] = {"ran": len(ok), "of": len(PLAIN), "mean_speed": round(float(np.mean(ok)), 1) if ok else None,
                      "speeds": sp}
        steer2[l] = row
        print(f"layer {l}: " + "  ".join(f"{g:+.1f}:{r['ran']}/{r['of']},{r['mean_speed']}" for g, r in row.items()), flush=True)
    result["steer_speed_decision"] = {"plain": PLAIN, "by_layer": steer2}

    # ---- probe: can I do this?
    pairs = [json.loads(l) for l in open(d / f"vocab-{args.vocab}" / "val_pairs.jsonl")]
    rng = random.Random(0)
    cant = [p["prompt"] for p in pairs if p["family"] == "cant"]
    other = [p["prompt"] for p in pairs if p["family"] not in ("cant", "unknown")]
    rng.shuffle(cant), rng.shuffle(other)
    n = min(len(cant), len(other), 300)
    cant, other = cant[:n], other[:n]
    hn, ho = last_states(model, tok, cant, device), last_states(model, tok, other, device)
    h = n // 2
    probe, vecs = [], []
    for l in range(L):
        v = hn[:h, l].mean(0) - ho[:h, l].mean(0)
        vecs.append(v)
        probe.append(round(float(auc((hn[h:, l] @ v).numpy(), (ho[h:, l] @ v).numpy())), 3))
    best = int(np.argmax(probe))
    print("probe 'can I do this?' AUC by layer:", probe, f"(n={n} per class, held-out half)")
    lines = [l.strip() for f in args.talk if Path(f).exists() for l in open(f) if l.strip()]
    ht = last_states(model, tok, lines, device)
    lo, hi = float((ho[h:, best] @ vecs[best]).mean()), float((hn[h:, best] @ vecs[best]).mean())
    talk = {}
    for line, s in zip(lines, (ht[:, best] @ vecs[best]).numpy()):
        talk[line] = round((float(s) - lo) / (hi - lo), 2)   # 0 = like the things it can do, 1 = like the things it can't
    for line, s in sorted(talk.items(), key=lambda x: -x[1])[:12]:
        print(f"  {s:+.2f}  {line}")
    result["probe_cant"] = {"auc_by_layer": probe, "n": n, "layer": best, "talk": talk}

    # ---- crash: will the program drive until it hits something?
    hits = lambda prog: bool(re.search(r"move\((\d+), 0, 0\)\nwhile (shaken\(\) == 0|not \(shaken\(\)\)):", prog))
    pos = [p["prompt"] for p in pairs if hits(p["program"])]
    neg = [p["prompt"] for p in pairs if not hits(p["program"]) and p["family"] not in ("unknown", "cant")]
    rng.shuffle(pos), rng.shuffle(neg)
    n = min(len(pos), len(neg), 300)
    pos, neg = pos[:n], neg[:n]
    hp, hq = last_states(model, tok, pos, device), last_states(model, tok, neg, device)
    h = n // 2
    cauc, cvec = [], []
    for l in range(L):
        v = hp[:h, l].mean(0) - hq[:h, l].mean(0)
        cvec.append(v)
        cauc.append(round(float(auc((hp[h:, l] @ v).numpy(), (hq[h:, l] @ v).numpy())), 3))
    cb = int(np.argmax(cauc))
    print("probe 'will I hit something?' AUC by layer:", cauc, f"(n={n} per class)")
    lo, hi = float((hq[h:, cb] @ cvec[cb]).mean()), float((hp[h:, cb] @ cvec[cb]).mean())
    ctalk = {line: round((float(x) - lo) / (hi - lo), 2) for line, x in zip(lines, (ht[:, cb] @ cvec[cb]).numpy())}
    for line, x in sorted(ctalk.items(), key=lambda x: -x[1])[:10]:
        print(f"  {x:+.2f}  {line}")
    result["probe_crash"] = {"auc_by_layer": cauc, "n": n, "layer": cb, "talk": ctalk}

    # ---- speed: how fast will the program drive?
    def top_speed(prog):
        ms = re.findall(r"move\((-?\d+), (-?\d+), (-?\d+)\)", prog)
        if not ms or "move(" in re.sub(r"move\(-?\d+, -?\d+, -?\d+\)", "", prog):
            return None                                  # no wheels, or a speed computed at run time
        return max(max(abs(int(a)), abs(int(c))) for a, _, c in ms)
    rows = [(p["prompt"], top_speed(p["program"])) for p in pairs]
    rows = [r for r in rows if r[1] is not None]
    rng.shuffle(rows)
    rows = rows[:1200]
    hs = last_states(model, tok, [p for p, _ in rows], device)
    y = torch.tensor([float(v) for _, v in rows])
    k = len(rows) * 2 // 3
    sres, models_ = [], []
    for l in range(L):
        X = torch.cat([hs[:, l], torch.ones(len(rows), 1)], 1)
        A = X[:k].T @ X[:k] + 1.0 * torch.eye(X.shape[1])
        w = torch.linalg.solve(A, X[:k].T @ y[:k])
        pred = X[k:] @ w
        r_ = float(np.corrcoef(pred.numpy(), y[k:].numpy())[0, 1])
        sres.append({"r": round(r_, 3), "mae": round(float((pred - y[k:]).abs().mean()), 1)})
        models_.append(w)
    sb = int(np.argmax([x["r"] for x in sres]))
    print("probe 'how fast?' by layer:", sres, f"(train {k}, held-out {len(rows) - k}; speeds {int(y.min())}..{int(y.max())})")
    Xt = torch.cat([ht[:, sb], torch.ones(len(lines), 1)], 1)
    guess = (Xt @ models_[sb]).numpy()
    stalk, pairs_ = {}, []
    for line, g in zip(lines, guess):
        prog = write(line)
        real = top_speed(prog)
        stalk[line] = {"probe": round(float(g), 1), "wrote": real}
        if real is not None:
            pairs_.append((float(g), real))
    if len(pairs_) > 2:
        a_, b_ = zip(*pairs_)
        print(f"  free-form: probe vs speed it then wrote, r={np.corrcoef(a_, b_)[0, 1]:.2f}, "
              f"mae={np.mean(np.abs(np.array(a_) - np.array(b_))):.1f} over {len(pairs_)} lines that drive")
    for line, d_ in list(stalk.items())[:60]:
        if d_["wrote"] is not None:
            print(f"  probe {d_['probe']:6.1f}  wrote {d_['wrote']:4d}  {line}")
    result["probe_speed"] = {"by_layer": sres, "layer": sb, "talk": stalk}
    if args.out:
        Path(args.out).write_text(json.dumps(result, indent=1))


if __name__ == "__main__":
    sys.exit(main())
