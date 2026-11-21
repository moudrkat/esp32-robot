"""Do the English and the Czech robot know the same things? The programs come from one generator, so what can drift
is the wording: an intent with wordings in one bank and none in the other, an answer with no Czech text. Run before
training either; it prints what one has and the other lacks, and exits 1 if anything does.

    PYTHONPATH=src:. python -m research.robot.sync_check
"""
import json
import sys
from pathlib import Path

from research.robot.answers import ANSWERS as EN
from research.robot.answers_cs import ANSWERS as CS

HERE = Path(__file__).parent


def bank(name):
    rows = [json.loads(l) for l in open(HERE / name)]
    return {r["program"]: r["p"] for r in rows if r.get("family") != "answer"}, \
           {r["program"]: r["p"] for r in rows if r.get("family") == "answer"}


def main():
    en, en_ans = bank("phrases.jsonl")
    cs, cs_ans = bank("phrases_cs.jsonl")
    bad = []
    for prog in sorted(set(en) - set(cs)):
        bad.append(f"only English wordings: {prog.strip().splitlines()[0][:60]}")
    for prog in sorted(set(cs) - set(en)):
        bad.append(f"only Czech wordings: {prog.strip().splitlines()[0][:60]}")
    for prog in sorted(set(en) & set(cs)):
        if min(len(en[prog]), len(cs[prog])) < 30:
            bad.append(f"thin ({len(en[prog])} en, {len(cs[prog])} cs): {prog.strip().splitlines()[0][:50]}")
    ek, ck = {k for k, *_ in EN}, {k for k, *_ in CS}
    bad += [f"answer only in English: {k}" for k in sorted(ek - ck)] + [f"answer only in Czech: {k}" for k in sorted(ck - ek)]
    for k, _, _, prog in EN:
        if k in ck and len(en_ans.get(prog, [])) < 30:
            bad.append(f"answer {k}: {len(en_ans.get(prog, []))} English wordings")
    for k, _, prog in CS:
        if len(cs_ans.get(prog, [])) < 30:
            bad.append(f"answer {k}: {len(cs_ans.get(prog, []))} Czech wordings")
    print(f"{len(en)} intents and {len(ek)} answers in English; {len(cs)} intents and {len(ck)} answers in Czech")
    print("\n".join(bad) if bad else "in step: every intent and every answer has wordings in both")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
