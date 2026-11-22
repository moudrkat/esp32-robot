"""Czech before robot talk: one tokenizer for both, and the plain Czech sentences as token bins.

The robot pairs teach about 16 thousand wordings; a corpus of ordinary sentences shows the same words in a million
other places. The model is first trained on the sentences, then on the pairs (train.py --init). Both steps must cut
text into the same tokens, so the tokenizer is trained here on both texts and written into both data folders:

    data/cs-pre/vocab-<N>/   tokenizer, train.bin, val.bin of the sentences (as "# <sentence>", where a request sits)
    <pairs dir>/vocab-<N>/   the same tokenizer; research.oled.prepare then finds it and uses it

    python -m research.robot.pretrain_prep --corpus data/cs-corpus.txt --pairs-dir data/car-cs4j --vocab 4096
"""
import argparse
import json
import random
import shutil
from pathlib import Path

import numpy as np

from research.oled.prepare import EOT, train_tokenizer


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--pairs-dir", required=True, help="holds pairs.jsonl")
    ap.add_argument("--out", default="data/cs-pre")
    ap.add_argument("--vocab", type=int, default=4096)
    ap.add_argument("--n-cond", type=int, default=9, help="silent input channels of the robot model, all zero here")
    args = ap.parse_args()
    sents = [f"# {l.strip()}" for l in open(args.corpus) if l.strip()]
    assert all(s.isascii() for s in sents)
    docs = [json.loads(l)["doc"] for l in open(Path(args.pairs_dir) / "pairs.jsonl")]
    random.Random(0).shuffle(sents)
    out = Path(args.out) / f"vocab-{args.vocab}"
    out.mkdir(parents=True, exist_ok=True)
    tok = train_tokenizer(sents + docs, args.vocab, out / "tokenizer.json")
    pd = Path(args.pairs_dir) / f"vocab-{args.vocab}"
    pd.mkdir(parents=True, exist_ok=True)
    shutil.copy(out / "tokenizer.json", pd / "tokenizer.json")
    eot, n_val = tok.token_to_id(EOT), 20000
    for name, part in (("val", sents[:n_val]), ("train", sents[n_val:])):
        ids = []
        for enc in tok.encode_batch(part):
            ids.extend(enc.ids)
            ids.append(eot)
        np.array(ids, dtype=np.uint16).tofile(out / f"{name}.bin")
        np.zeros((len(ids), args.n_cond), dtype=np.uint8).tofile(out / f"{name}.cond.bin")
        print(f"{name}: {len(part):,} sentences, {len(ids):,} tokens")


if __name__ == "__main__":
    main()
