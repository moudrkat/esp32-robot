"""Train one ablation arm and report val loss at matched core-parameter budget."""

import argparse
import hashlib
import json
import math
import os
import time

import numpy as np
import torch

from model import Config, TinyLM, make_model

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# A vocabulary variant keeps its tokenizer and token bins together.
DATA = ROOT / "data" / "tinystories"
RUNS = str(ROOT / "runs")


def variant_dir(vocab_size):
    return DATA / f"vocab-{vocab_size}"


def get_device():
    if torch.backends.mps.is_available():
        return "mps"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


class Batcher:
    def __init__(self, split, batch_size, seq_len, device, dataset, seed=0, n_cond=0):
        # The bins are uint16. Reading a wider vocabulary through that dtype
        # yields plausible token ids rather than an error, so check before
        # opening.
        self.data = np.memmap(dataset / f"{split}.bin", dtype=np.uint16, mode="r")
        # non-word inputs, one uint8 strength (x/255) per token and channel, beside the tokens
        self.cond = None
        if n_cond:
            self.cond = np.memmap(dataset / f"{split}.cond.bin", dtype=np.uint8, mode="r").reshape(-1, n_cond)
            assert len(self.cond) == len(self.data), (len(self.cond), len(self.data))
        self.bs, self.sl, self.device = batch_size, seq_len, device
        # Batch order is part of the run. Without the seed here, torch.manual_seed
        # fixes initialisation only and two runs at the same --seed still see
        # different data order. Validation keeps a fixed stream so every arm is
        # scored on identical batches.
        self.rng = np.random.default_rng(1234 if split == "val" else seed)

    def __call__(self):
        ix = self.rng.integers(0, len(self.data) - self.sl - 1, self.bs)
        x = np.stack([self.data[i : i + self.sl] for i in ix]).astype(np.int64)
        y = np.stack([self.data[i + 1 : i + 1 + self.sl] for i in ix]).astype(np.int64)
        c = None
        if self.cond is not None:
            c = torch.from_numpy(np.stack([self.cond[i : i + self.sl] for i in ix]).astype(np.float32) / 255.0).to(self.device)
        return torch.from_numpy(x).to(self.device), torch.from_numpy(y).to(self.device), c


@torch.no_grad()
def evaluate(model, batcher, iters):
    model.eval()
    batcher.rng = np.random.default_rng(1234)  # same val batches for every arm
    losses = []
    for _ in range(iters):
        x, y, c = batcher()
        losses.append(model(x, y, cond=c)[1].item())
    model.train()
    return sum(losses) / len(losses)


QGROUP = 128     # export.py GROUP: the chip's weights are 4-bit in groups of this many, one fp16 scale per group


def fake_quant(w, group=QGROUP):
    """w as the chip will hold it (export.quant_pack's dq): 4-bit codes -7..7 times a per-group fp16 scale."""
    rows, cols = w.shape
    pad = (-cols) % group
    x = torch.nn.functional.pad(w.float(), (0, pad)).reshape(rows, -1, group)
    sc = (x.abs().amax(dim=2, keepdim=True) / 7).clamp_min(1e-8).half().float()
    return (torch.clamp(torch.round(x / sc), -7, 7) * sc).reshape(rows, -1)[:, :cols].to(w.dtype)


class AsOnChip:
    """Inside the block the model holds the weights the chip will hold. The gradient computed there is then applied
    to the full-precision weights (straight-through), so training looks for weights that still work after rounding."""
    def __init__(self, model, on):
        self.ps = [p for n, p in model.named_parameters() if p.dim() == 2 and "norm" not in n] if on else []

    def __enter__(self):
        self.keep = [p.data.clone() for p in self.ps]
        with torch.no_grad():
            for p in self.ps:
                p.data.copy_(fake_quant(p.data))

    def __exit__(self, *a):
        for p, k in zip(self.ps, self.keep):
            p.data.copy_(k)


def lr_at(step, total, peak, warmup):
    if step < warmup:
        return peak * (step + 1) / warmup
    p = (step - warmup) / max(1, total - warmup)
    return 0.1 * peak + 0.9 * peak * 0.5 * (1 + math.cos(math.pi * p))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--arm",
        required=True,
        choices=["baseline", "ple", "ple_notable", "fatembed", "bigcore"],
    )
    ap.add_argument("--target-core", type=int, default=1_500_000)
    ap.add_argument("--steps", type=int, default=4000)
    ap.add_argument("--batch-size", type=int, default=32)
    ap.add_argument("--seq-len", type=int, default=512)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--warmup", type=int, default=200)
    ap.add_argument("--eval-every", type=int, default=250)
    ap.add_argument("--eval-iters", type=int, default=40)
    ap.add_argument("--ple-dim", type=int, default=64)
    ap.add_argument("--n-cond", type=int, default=0, help="non-word input channels (<split>.cond.bin beside the bins)")
    ap.add_argument("--cond-layer", type=int, default=0)
    ap.add_argument("--d-model", type=int, default=128)
    ap.add_argument("--n-layers", type=int, default=6)
    ap.add_argument("--n-heads", type=int, default=4)
    ap.add_argument("--fixed-ffn", type=int, default=None,
                    help="pin ffn_hidden and skip the core solver (table-scaling sweep)")
    # Published experiments always pass --vocab; the default is for ad-hoc runs.
    ap.add_argument("--vocab", type=int, default=32768)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--tag", default="")
    # Another corpus prepared in the same layout (tokenizer.json, train.bin,
    # val.bin under vocab-N/) trains with the same code; only the root moves.
    ap.add_argument("--data-dir", default=str(DATA),
                    help="dataset root holding vocab-N/; default data/tinystories")
    # A small corpus is overtrained many epochs over; the final step is then
    # rarely the best one. The checkpoint at the lowest val loss is kept beside
    # the final one so the exporter can pick either.
    ap.add_argument("--qat-from", type=int, default=None,
                    help="from this step on, train and validate with the weights rounded to 4 bits as on the chip")
    ap.add_argument("--init", help="start from this checkpoint's weights (pretrained on other text with the same tokenizer)")
    ap.add_argument("--save-best", action="store_true",
                    help="also write runs/<name>-best.pt at the lowest val loss")
    args = ap.parse_args()

    # Before anything expensive: the tokenizer that produced these bins. Its
    # hash is what lets the exporter and sampler refuse a mismatched tokenizer
    # later, and a checkpoint written without it cannot be tied to one. Failing
    # here costs nothing; failing after a 30-minute run costs the run.
    if not 0 < args.vocab <= 65536:
        raise SystemExit(f"--vocab must be 1..65536; the token bins are uint16 "
                         f"and are memmapped as uint16")

    dataset = Path(args.data_dir) / f"vocab-{args.vocab}"
    tok_path = dataset / "tokenizer.json"
    if not os.path.exists(tok_path):
        raise SystemExit(
            f"{tok_path} missing. The bins this run trains on came from it, and "
            f"without its hash the checkpoint cannot be tied to a tokenizer. "
            f"Run: python -m research.tinystories.prepare --vocab {args.vocab}")
    tok_sha = hashlib.sha256(open(tok_path, "rb").read()).hexdigest()

    torch.manual_seed(args.seed)
    device = get_device()
    os.makedirs(RUNS, exist_ok=True)

    base = Config(seq_len=args.seq_len, ple_dim=args.ple_dim, vocab_size=args.vocab,
                  d_model=args.d_model, n_layers=args.n_layers, n_heads=args.n_heads,
                  n_cond=args.n_cond, cond_layer=args.cond_layer)
    model = make_model(args.arm, args.target_core, base, fixed_ffn=args.fixed_ffn).to(device)
    if args.init:
        model.load_state_dict(torch.load(args.init, map_location=device)["state"])
        print(f"weights from {args.init}", flush=True)
    budget = model.param_budget()
    cfg = model.cfg

    # No weight decay on 1-D params (norms) or on lookup tables.
    decay, no_decay = [], []
    for n, p in model.named_parameters():
        (no_decay if p.ndim < 2 or "table" in n or "tok_emb" in n else decay).append(p)
    opt = torch.optim.AdamW(
        [{"params": decay, "weight_decay": 0.1}, {"params": no_decay, "weight_decay": 0.0}],
        lr=args.lr,
        betas=(0.9, 0.95),
    )

    train_b = Batcher("train", args.batch_size, args.seq_len, device, dataset,
                      seed=args.seed, n_cond=args.n_cond)
    val_b = Batcher("val", args.batch_size, args.seq_len, device, dataset, n_cond=args.n_cond)

    name = f"{args.arm}{'-' + args.tag if args.tag else ''}-s{args.seed}"
    history, best = [], float("inf")
    t0 = time.time()

    for step in range(args.steps):
        lr = lr_at(step, args.steps, args.lr, args.warmup)
        for g in opt.param_groups:
            g["lr"] = lr
        qat = args.qat_from is not None and step >= args.qat_from
        if qat and step == args.qat_from:
            best = float("inf")          # the best so far was measured unrounded: start again
        x, y, c = train_b()
        opt.zero_grad(set_to_none=True)
        with AsOnChip(model, qat):
            _, loss = model(x, y, cond=c)
            loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        opt.step()

        if step % args.eval_every == 0 or step == args.steps - 1:
            with AsOnChip(model, qat):
                vl = evaluate(model, val_b, args.eval_iters)
            if args.save_best and vl < best:
                torch.save({"cfg": cfg.__dict__, "state": model.state_dict(),
                            "tokenizer_sha256": tok_sha, "seed": args.seed,
                            "tag": args.tag, "name": name + "-best", "best_step": step,
                            "best_val": vl, "training": None},
                           os.path.join(RUNS, f"{name}-best.pt"))
            best = min(best, vl)
            tok = (step + 1) * args.batch_size * args.seq_len
            history.append({"step": step, "tokens": tok, "train": loss.item(), "val": vl})
            print(
                f"{name} step {step:5d} | tok {tok / 1e6:6.1f}M | train {loss.item():.4f} "
                f"| val {vl:.4f} | ppl {math.exp(vl):7.2f} | {time.time() - t0:5.0f}s",
                flush=True,
            )

    result = {
        "arm": args.arm,
        "seed": args.seed,
        "tag": args.tag,
        "config": {k: v for k, v in cfg.__dict__.items()},
        "training": {
            "batch_size": args.batch_size,
            "steps": args.steps,
            "lr": args.lr,
            "warmup": args.warmup,
            "eval_every": args.eval_every,
            "eval_iters": args.eval_iters,
            "target_core": args.target_core,
            "fixed_ffn": args.fixed_ffn,
            "seed": args.seed,
        },
        "tokenizer_sha256": tok_sha,
        "params": budget,
        "final_val": history[-1]["val"],
        "best_val": best,
        "final_ppl": math.exp(history[-1]["val"]),
        "tokens_seen": args.steps * args.batch_size * args.seq_len,
        "steps": args.steps,
        "wall_seconds": time.time() - t0,
        "history": history,
    }
    with open(os.path.join(RUNS, f"{name}.json"), "w") as f:
        json.dump(result, f, indent=2)
    # Identity and schedule live only in the filename and the sidecar JSON
    # otherwise, so a checkpoint copied over another name, or trained on a
    # different schedule, would pass every content check.
    torch.save({"cfg": cfg.__dict__, "state": model.state_dict(),
                "tokenizer_sha256": tok_sha,
                "seed": args.seed, "tag": args.tag, "name": name,
                "training": result["training"]},
               os.path.join(RUNS, f"{name}.pt"))
    print(f"{name} DONE core={budget['core']:,} table={budget['table']:,} "
          f"val={result['final_val']:.4f} ppl={result['final_ppl']:.2f}")


if __name__ == "__main__":
    main()
