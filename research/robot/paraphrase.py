"""Paraphrase generated car requests with a bigger model, keeping each one's program: data that sounds like people,
not like templates. The labels stay right by construction (the program is the original's) and by checks:

  - only requests whose meaning a rewording can't shift: no words to copy onto the screen, no speed words or percent,
    no "a tiny bit", no mood said in words (those map to exact numbers or programs a paraphrase could bend);
  - every paraphrase keeps the same digits and number words, the same left/right, the same back/forward, the same
    colours, and contains none of the locked test sentences.

Runs a local instruct model through vLLM (no network). Writes pairs in gen.py's format, with the original's family,
program and non-word inputs.

    python -m research.robot.paraphrase data/car/pairs.jsonl --n 30000 --out data/car/paraphrases.jsonl
"""
import argparse
import json
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research.oled.gen import COLOURS, HELDOUT, MOODS, SPEED_SCALE, _norm  # noqa: E402

SKIP_FAMILIES = {"text", "two_lines", "blink", "count", "unknown", "face"}
NUMWORDS = {"one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "twice", "thrice", "once",
            "half", "full"}
BACK = {"back", "backward", "backwards", "reverse", "reversing"}
ANCHORS = [{"head"}, {"eye", "eyes"}, {"light", "lights", "led", "leds", "headlights"}, {"arm", "hand", "hands", "paw"},
           {"screen", "display", "face", "oled"}, {"line", "tape"}, {"temperature", "temp", "warm", "hot", "cold", "chilly"},
           {"humid", "humidity", "damp"}, {"behind"}, {"clap", "claps", "loud", "noise", "noisy", "music"},
           {"horn", "honk", "beep", "toot"}, {"lift", "lifted", "pick", "picks", "tilt", "tilted"}, {"wall", "door"}]
SPEEDY = {w for p, _ in SPEED_SCALE for w in p.split() if len(w) > 3} | {"percent", "%", "speed", "power"}
MOODY = {w for said in MOODS.values() for p in said for w in p.split() if len(w) > 3 and w not in ("you're", "your")}
INSTR = ("Here is something a person said to a small toy robot car. Rewrite it the way {k} different people might say "
         "the same thing, casually, in English. Keep the meaning exactly: the same action, the same numbers, the same "
         "left or right, the same colours. Do not add anything. One rewrite per line, no numbering, no quotes.\n\n{req}")


def words(t):
    return re.findall(r"[a-z0-9%']+", t.lower())


def keeps(orig, para):
    a, b = words(orig), words(para)
    nums = lambda ws: sorted(w for w in ws if w.isdigit() or w in NUMWORDS)
    if nums(a) != nums(b):
        return False
    for group in ({"left"}, {"right"}, set(COLOURS)):          # the same words of these, exactly
        if set(a) & group != set(b) & group:
            return False
    if bool(set(a) & BACK) != bool(set(b) & BACK):            # backwards stays backwards, forwards stays forwards
        return False
    for group in ANCHORS:                                     # what it acts with stays: the head is not the wheels
        if bool(set(a) & group) != bool(set(b) & group):
            return False
    if any(h in _norm(para) for h in HELDOUT):
        return False
    return 3 <= len(para) <= 120 and para.isascii()


def eligible(row):
    if row["family"] in SKIP_FAMILIES:
        return False
    p = row["prompt"].lower()
    quoted = re.findall(r'text\(\d+, \d+, "([^"]*)"\)', row["program"])
    if any(q.lower() in p for q in quoted if q):
        return False                               # a word to copy onto the screen
    ws = set(words(p))
    if ws & SPEEDY or ws & MOODY or "tiny bit" in p or "few inches" in p:
        return False
    return True


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("pairs")
    ap.add_argument("--n", type=int, default=30000)
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--model", default="Qwen/Qwen3-4B-Instruct-2507")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    rows = [json.loads(l) for l in open(args.pairs)]
    rows = [r for r in rows if eligible(r)]
    seen, pick = set(), []
    random.Random(0).shuffle(rows)
    for r in rows:                                   # one per distinct request
        key = _norm(r["prompt"])
        if key not in seen:
            seen.add(key)
            pick.append(r)
        if len(pick) >= args.n:
            break
    print(f"{len(pick):,} requests to paraphrase")

    from vllm import LLM, SamplingParams
    llm = LLM(model=args.model, gpu_memory_utilization=0.85, max_model_len=1024)
    tok = llm.get_tokenizer()
    prompts = [tok.apply_chat_template([{"role": "user", "content": INSTR.format(k=args.k, req=r["prompt"])}],
                                       tokenize=False, add_generation_prompt=True) for r in pick]
    outs = llm.generate(prompts, SamplingParams(temperature=0.9, top_p=0.95, max_tokens=200, seed=0))
    kept, tried = 0, 0
    with open(args.out, "w") as f:
        for r, o in zip(pick, outs):
            for line in o.outputs[0].text.splitlines():
                para = line.strip().strip('"').strip()
                para = re.sub(r"^[-*\d.)\s]+", "", para)
                if not para:
                    continue
                tried += 1
                if para.lower() == r["prompt"].lower() or not keeps(r["prompt"], para):
                    continue
                kept += 1
                row = {"prompt": para, "program": r["program"], "family": r["family"], "doc": f"# {para}\n{r['program']}",
                       "paraphrase_of": r["prompt"]}
                if "cond" in r:
                    row["cond"] = r["cond"]
                f.write(json.dumps(row) + "\n")
    print(f"kept {kept:,} of {tried:,} paraphrases -> {args.out}")


if __name__ == "__main__":
    sys.exit(main())
