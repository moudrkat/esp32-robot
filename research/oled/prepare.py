"""Tokenize the OLED pairs for the PLE pipeline, in the layout research/tinystories/train.py reads:

    data/oled/vocab-<N>/{tokenizer.json, train.bin, val.bin, manifest.json, val_pairs.jsonl}

One document per pair, "# <request>\\n<program>", then end-of-text. The split is by request text, so a prompt
in val never appears in train, and val_pairs.jsonl keeps the held-out pairs for eval.py, which runs the model's
program and the reference in the interpreter and compares the pictures. Tokenizer recipe as TinyStories
(ByteLevel BPE, one special token, no added-token table), ASCII only for the device encoder.

    python -m research.oled.prepare --vocab 2048
"""
import argparse
import hashlib
import json
import random
import sys
from pathlib import Path

import numpy as np
from tokenizers import Tokenizer, decoders, models, pre_tokenizers, trainers


ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "oled"
SRC = DATA / "pairs.jsonl"
VAL_FRACTION = 0.03
SEED = 0


EOT = "<|endoftext|>"


def train_tokenizer(docs, vocab_size, path):
    tok = Tokenizer(models.BPE(unk_token=None))
    tok.pre_tokenizer = pre_tokenizers.ByteLevel(add_prefix_space=False)
    tok.decoder = decoders.ByteLevel()
    trainer = trainers.BpeTrainer(vocab_size=vocab_size, special_tokens=[EOT],
                                  initial_alphabet=pre_tokenizers.ByteLevel.alphabet(), show_progress=False)
    tok.train_from_iterator(docs, trainer=trainer)
    cfg = json.loads(tok.to_str())
    cfg["added_tokens"] = []
    path.write_text(json.dumps(cfg, ensure_ascii=False, indent=None))
    return Tokenizer.from_file(str(path))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--vocab", type=int, default=2048, help="small: the language has a few dozen words")
    ap.add_argument("--data-dir", default=str(DATA), help="holds pairs.jsonl; vocab-N/ is written next to it")
    ap.add_argument("--min-per-family", type=int, default=1500, help="repeat small families in train up to this")
    args = ap.parse_args()
    data = Path(args.data_dir)
    src = data / "pairs.jsonl"
    rows = [json.loads(l) for l in open(src)]
    assert all(r["doc"].isascii() for r in rows), "the device encoder takes ASCII only"
    prompts = sorted({r["prompt"].lower() for r in rows})
    random.Random(SEED).shuffle(prompts)
    held = set(prompts[:max(200, int(len(prompts) * VAL_FRACTION))])
    splits = {"val": [r for r in rows if r["prompt"].lower() in held],
              "train": [r for r in rows if r["prompt"].lower() not in held]}
    # small families (a checkerboard has a few dozen spellings, a word on the screen thousands) are repeated in
    # train until each has --min-per-family documents, so the model sees every kind of request often enough
    by_fam = {}
    for r in splits["train"]:
        by_fam.setdefault(r["family"], []).append(r)
    rng = random.Random(SEED)
    for fam, rs in by_fam.items():
        while len([x for x in splits["train"] if x["family"] == fam]) < args.min_per_family and rs:
            splits["train"].extend(rs[:args.min_per_family - len([x for x in splits["train"] if x["family"] == fam])])
    rng.shuffle(splits["train"])

    out = data / f"vocab-{args.vocab}"
    out.mkdir(parents=True, exist_ok=True)
    tok_path = out / "tokenizer.json"
    tok = Tokenizer.from_file(str(tok_path)) if tok_path.exists() else \
        train_tokenizer([r["doc"] for r in splits["train"]], args.vocab, tok_path)
    eot = tok.token_to_id(EOT)
    # non-word inputs: a row's "cond" ({channel: strength 0..1}) is written beside every one of its tokens
    channels = sorted({k for r in rows for k in r.get("cond", {})})
    counts, lengths = {}, []
    for name, part in splits.items():
        ids, conds = [], []
        for r, enc in zip(part, tok.encode_batch([r["doc"] for r in part])):
            ids.extend(enc.ids); ids.append(eot); lengths.append(len(enc.ids))
            if channels:
                c = [int(round(255 * r.get("cond", {}).get(k, 0.0))) for k in channels]
                conds.extend([c] * (len(enc.ids) + 1))
        np.array(ids, dtype=np.uint16).tofile(out / f"{name}.bin")
        if channels:
            np.array(conds, dtype=np.uint8).tofile(out / f"{name}.cond.bin")
        counts[name] = len(ids)
        print(f"{name}: {len(part):,} pairs, {len(ids):,} tokens")
    with open(out / "val_pairs.jsonl", "w") as f:
        for r in splits["val"]:
            f.write(json.dumps(r) + "\n")
    lengths.sort()
    manifest = {"source": "research/oled/gen.py (rules, checked by lang.run)",
                "src_sha256": hashlib.sha256(src.read_bytes()).hexdigest(), "pairs": len(rows), "tokens": counts,
                "tokens_per_doc": {"median": lengths[len(lengths) // 2], "p95": lengths[int(len(lengths) * .95)],
                                   "max": lengths[-1]},
                "vocab": args.vocab, "eot_id": eot, "seed": SEED, "cond_channels": channels,
                "tokenizer_sha256": hashlib.sha256(tok_path.read_bytes()).hexdigest()}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(json.dumps(manifest["tokens_per_doc"]), "->", out)


if __name__ == "__main__":
    sys.exit(main())
