"""Reference logits for runtime/host_verify/cond_verify.c: the exported (int4) car model with its non-word inputs.

Each case: a request, a set of strengths; the input vector sum_k s_k * c_k (c_k = the learned columns, kept in fp32 as
the chip keeps them) and PyTorch's last-position logits with the same weights the chip runs.

    PYTHONPATH=src:. python -m research.robot.cond_golden runs/v9-ple-car-s0-best.pt --data-dir data/car --out cond_golden.txt
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import torch
from tokenizers import Tokenizer

from research.oled.eval import load
from research.tinystories.export import quant_pack

CASES = [("go", {}), ("go", {"angry": 1.0}), ("do a little dance", {"angry": 0.8}), ("crash into the wall", {"caution": 1.0}),
         ("drive forward 2 seconds", {"tired": 0.5}), ("go to the wall", {"scared": 0.7, "playful": 0.3})]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("ckpt")
    ap.add_argument("--data-dir", default="data/car")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    d = Path(args.data_dir) / "vocab-2048"
    tok = Tokenizer.from_file(str(d / "tokenizer.json"))
    ch = json.loads((d / "manifest.json").read_text())["cond_channels"]
    model, cfg = load(args.ckpt, "cpu")
    sd = model.state_dict()
    for k, v in sd.items():                       # the int4 weights the chip runs; the input columns stay fp32
        if v.dim() == 2 and "norm" not in k and not k.startswith("cond_proj"):
            sd[k] = torch.as_tensor(quant_pack(v)[2]).reshape(v.shape).to(v.dtype)
    model.load_state_dict(sd)
    W = model.cond_proj.weight.detach()           # [D, K]
    with open(args.out, "w") as f, torch.no_grad():
        for req, strengths in CASES:
            ids = tok.encode(f"# {req}\n").ids
            s = torch.tensor([strengths.get(k, 0.0) for k in ch])
            vec = W @ s
            c = s.expand(1, len(ids), -1)
            logits, _ = model(torch.tensor([ids]), cond=c)
            f.write(f"{len(ids)} {' '.join(map(str, ids))}\n{cfg['cond_layer']}\n")
            f.write(" ".join(f"{x:.7g}" for x in vec.tolist()) + "\n")
            f.write(" ".join(f"{x:.7g}" for x in logits[0, -1, :tok.get_vocab_size()].tolist()) + "\n")
    print("wrote", args.out, len(CASES), "cases")


if __name__ == "__main__":
    sys.exit(main())
