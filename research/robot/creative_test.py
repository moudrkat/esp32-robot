"""Does it make things up, and does it stay exact where it should? Each request is written several times with the
uncertain-only draw (eval.write minp). Printed per request: how many of the programs run, how many are different.
A made-up request should give several different programs that all run; an exact order should give one.

    python -m research.robot.creative_test runs/cs4-best.pt research/robot/creative_cs.txt --data-dir data/car-cs4
"""
import argparse
import sys
import unicodedata
from pathlib import Path

import torch
from tokenizers import Tokenizer

from research.oled import eval as E
from research.oled.gen import PROBE, reacts
from research.oled.inside import load_int4
from research.oled.lang import LangError, run


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("ckpt")
    ap.add_argument("requests")
    ap.add_argument("--data-dir", default="data/car")
    ap.add_argument("--vocab", type=int, default=2048)
    ap.add_argument("--minp", type=float, default=0.3)
    ap.add_argument("--n", type=int, default=6)
    ap.add_argument("--show", type=int, default=2)
    args = ap.parse_args()
    torch.manual_seed(0)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    tok = Tokenizer.from_file(str(Path(args.data_dir) / f"vocab-{args.vocab}" / "tokenizer.json"))
    eot = tok.token_to_id("<|endoftext|>")
    model, cfg = load_int4(args.ckpt, device)
    for req in [l.strip() for l in open(args.requests) if l.strip()]:
        sent = "".join(c for c in unicodedata.normalize("NFD", req) if not unicodedata.combining(c))
        progs, runs = [], 0
        for _ in range(args.n):
            prog = E.write(model, tok, eot, sent, device, cfg["seq_len"], minp=args.minp)
            try:
                run(prog, PROBE, horizon=3000) if reacts(prog) else run(prog)
                runs += 1
            except LangError:
                prog += "[REFUSED]\n"
            progs.append(prog)
        print(f"### {req}   runs {runs}/{args.n}, different {len(set(progs))}")
        for p in list(dict.fromkeys(progs))[:args.show]:
            print(p.rstrip() + "\n--")
        sys.stdout.flush()


if __name__ == "__main__":
    sys.exit(main())
