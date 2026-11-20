"""Score free-form requests by reading, once: every (request, program) pair a person has judged is remembered, and a
later model's answer counts the same if it is that program or does the same thing in the simulator. Only answers nobody
has judged yet are printed, to be read and marked.

    python -m research.robot.talk_score runs/v12-dev5.txt research/robot/dev_judged.jsonl
    python -m research.robot.talk_score runs/v12-dev5.txt research/robot/dev_judged.jsonl --ok 3,7 --bad 1,2

The first argument is what talk_test printed. --ok / --bad take the numbers shown for the unjudged answers.
"""
import argparse
import json
import sys
from pathlib import Path

from research.oled.gen import PROBE, reacts
from research.oled.lang import LangError, run, same


def load(path):
    out = []
    for b in Path(path).read_text().split("### ")[1:]:
        req, rest = b.split("\n", 1)
        out.append((req.strip(), rest.rsplit("\n[", 1)[0].strip() + "\n"))
    return out


def does(prog):
    try:
        return run(prog, PROBE, horizon=3000) if reacts(prog) else run(prog)
    except LangError:
        return None


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("answers")
    ap.add_argument("judged")
    ap.add_argument("--ok", default="")
    ap.add_argument("--bad", default="")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    jp = Path(args.judged)
    judged = [json.loads(l) for l in jp.read_text().splitlines()] if jp.exists() else []
    answers = load(args.answers)
    marks = {int(i): True for i in args.ok.split(",") if i} | {int(i): False for i in args.bad.split(",") if i}
    n_ok, unknown = 0, []
    for i, (req, prog) in enumerate(answers, 1):
        verdict = None
        mine = [j for j in judged if j["request"] == req]
        for j in mine:
            if j["program"] == prog:
                verdict = j["ok"]
        if verdict is None and mine:
            a = does(prog)
            for j in mine:
                b = does(j["program"])
                if a is not None and b is not None and reacts(prog) == reacts(j["program"]) and same(a, b):
                    verdict = j["ok"]
        if verdict is None and i in marks:
            verdict = marks[i]
            judged.append({"request": req, "program": prog, "ok": verdict})
        if verdict is None:
            unknown.append((i, req, prog))
        n_ok += bool(verdict)
    if marks:
        jp.write_text("".join(json.dumps(j) + "\n" for j in judged))
    if not args.quiet:
        for i, req, prog in unknown:
            print(f"{i}. {req}\n" + "".join("    " + l + "\n" for l in prog.splitlines()))
    print(f"{n_ok}/{len(answers)} right, {len(unknown)} not judged yet")


if __name__ == "__main__":
    sys.exit(main())
