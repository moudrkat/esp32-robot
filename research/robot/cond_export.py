"""Write model/cond.json: the learned columns of the non-word inputs, in fp32 as the chip keeps them.

    PYTHONPATH=src:. python -m research.robot.cond_export runs/ple-car-s0-best.pt --data-dir data/car --out model/cond.json
"""
import argparse
import json
from pathlib import Path

import torch


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("ckpt")
    ap.add_argument("--data-dir", default="data/car")
    ap.add_argument("--out", default="model/cond.json")
    args = ap.parse_args()
    ck = torch.load(args.ckpt, map_location="cpu", weights_only=False)
    channels = json.loads((Path(args.data_dir) / "vocab-2048" / "manifest.json").read_text())["cond_channels"]
    W = ck["state"]["cond_proj.weight"]
    Path(args.out).write_text(json.dumps({"layer": ck["cfg"]["cond_layer"], "channels": channels, "vectors": W.T.tolist()}))
    print("wrote", args.out, channels)


if __name__ == "__main__":
    main()
