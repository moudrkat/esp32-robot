"""Free-form requests (one per line) through the int4 model the board runs: print each request, the program it
wrote, and whether the chip would run it. Scoring is by reading: nothing here knows what the request meant.

    PYTHONPATH=src:. python -m research.robot.talk_test runs/ple-car-s0-best.pt research/robot/car_talk.txt --data-dir data/car
"""
import argparse
import sys
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
    args = ap.parse_args()
    device = "cuda" if torch.cuda.is_available() else "cpu"
    tok = Tokenizer.from_file(str(Path(args.data_dir) / f"vocab-{args.vocab}" / "tokenizer.json"))
    eot = tok.token_to_id("<|endoftext|>")
    model, cfg = load_int4(args.ckpt, device)
    for req in [l.strip() for l in open(args.requests) if l.strip()]:
        prog = E.write(model, tok, eot, req, device, cfg["seq_len"])
        try:
            run(prog, PROBE, horizon=3000) if reacts(prog) else run(prog)
            ok = "runs"
        except LangError as e:
            ok = f"REFUSED ({e})"
        print(f"### {req}\n{prog.rstrip()}\n[{ok}]\n", flush=True)


if __name__ == "__main__":
    sys.exit(main())
