"""The same robot without a model: rules written by hand, as one would in an afternoon. What does the model buy?

A request is cleaned (no diacritics, no "please"), cut into steps at "then / and / finally", and every step is matched
against patterns for the commands the robot has: drive, turn, beep, lights, screen, eyes, arm, head, sensors, a few
answers, and "when <condition>, <action>". Numbers, colours, durations and directions are read from the words. What no
rule matches is answered with "to neumim". The output is in talk_test's format, so talk_score reads it the same way.

The rules were written from the list of commands, generously (compound numbers, many verbs), but by someone who has
read the test sentences: treat the score as an upper estimate of what rules would do.

    python -m research.robot.regex_baseline research/robot/dev_cs_talk.txt > runs/regex-dev_cs.txt
"""
import re
import sys
import unicodedata

from research.oled.gen import cx

ONES = {"nula": 0, "jedna": 1, "jeden": 1, "jednu": 1, "jedne": 1, "dva": 2, "dve": 2, "tri": 3, "ctyri": 4, "pet": 5, "sest": 6,
        "sedm": 7, "osm": 8, "devet": 9, "deset": 10, "jedenact": 11, "dvanact": 12, "trinact": 13, "ctrnact": 14,
        "patnact": 15, "sestnact": 16, "sedmnact": 17, "osmnact": 18, "devatenact": 19}
TENS = {"dvacet": 20, "tricet": 30, "ctyricet": 40, "padesat": 50, "sedesat": 60, "sedmdesat": 70, "osmdesat": 80,
        "devadesat": 90, "sto": 100}
KRAT = {"jednou": 1, "dvakrat": 2, "trikrat": 3, "ctyrikrat": 4, "petkrat": 5, "sestkrat": 6, "sedmkrat": 7, "osmkrat": 8,
        "devetkrat": 9, "desetkrat": 10}
COLOURS = {"cerven": (255, 0, 0), "zelen": (0, 255, 0), "modr": (0, 0, 255), "zlut": (255, 180, 0), "oranzov": (255, 80, 0),
           "fialov": (160, 0, 255), "ruzov": (255, 60, 120), "bil": (255, 255, 255), "tyrkysov": (0, 255, 255)}
EYES = {"smutn": "sad", "nastvan": "angry", "zlob": "angry", "prekvapen": "surprised", "unaven": "sleepy", "ospal": "sleepy",
        "vesel": "happy", "stastn": "happy", "zamilovan": "heart"}
POLITE = r"\b(prosim te|prosim|hele|hej|mohl bys|mohla bys|muzes|tak|no tak|robote|auticko|diky|dik|ted)\b"


def plain(s):
    s = "".join(c for c in unicodedata.normalize("NFD", s) if not unicodedata.combining(c)).lower()
    return " ".join(re.sub(POLITE, " ", s).strip(" .!?").split())


def number(s):
    """The first number said in s, in digits or in words (also "petadvacet"), or None."""
    m = re.search(r"\d+", s)
    if m:
        return int(m.group())
    for w in re.findall(r"[a-z]+", s):
        if w in TENS:
            return TENS[w]
        if w in ONES:
            return ONES[w]
        m = re.fullmatch(r"([a-z]+?)a([a-z]+)", w)
        if m and m.group(1) in ONES and m.group(2) in TENS:
            return ONES[m.group(1)] + TENS[m.group(2)]
    return None


def times(s):
    for w, n in KRAT.items():
        if w in s:
            return n
    m = re.search(r"(\d+) ?(x|krat)", s)
    return int(m.group(1)) if m else None


def colour(s):
    return next((c for k, c in COLOURS.items() if k in s), None)


def duration(s):
    m = re.search(r"((?:\d+|[a-z]+) )?(vterin|sekund)", s)
    if m:
        return (number(m.group(1) or "") or 1) * 1000
    if re.search(r"kousek|trochu|kousicek|malinko", s):
        return 500
    return None


def say(w, eyes=None):
    return (f'eyes("{eyes}")\n' if eyes else "") + f'clear()\ntext({cx(w)}, 28, "{w}")\n'


def show(expr, unit):
    return f'while 1:\n    clear()\n    text(40, 28, str({expr}){unit})\n    wait(200)\n'


def yesno(cond, yes, no):
    return (f'while 1:\n    clear()\n    if {cond}:\n        text({cx(yes)}, 28, "{yes}")\n    else:\n'
            f'        text({cx(no)}, 28, "{no}")\n    wait(200)\n')


HOUSE = "clear()\nrect(44, 32, 40, 20)\nline(44, 32, 64, 12)\nline(64, 12, 84, 32)\nrect(60, 42, 6, 10)\n"
HEART = "clear()\ncircle(55, 28, 9)\ncircle(73, 28, 9)\nline(46, 28, 64, 50)\nline(82, 28, 64, 50)\n"
SMILEY = ("clear()\ncircle(64, 32, 24)\nfill(53, 23, 4, 4)\nfill(71, 23, 4, 4)\nline(52, 44, 56, 48)\nline(56, 48, 72, 48)\n"
          "line(72, 48, 76, 44)\n")
WAVE = "for i in range(2):\n    arm(150)\n    wait(300)\n    arm(90)\n    wait(300)\narm(0)\n"
DANCE = "for i in range(3):\n    move(0, 0, 80, 300)\n    move(0, 0, -80, 300)\n"
LINE = ("while 1:\n    l = track()\n    if l == 3:\n        move(40, 0, 0)\n    elif l == 1:\n        move(20, 0, -40)\n"
        "    elif l == 2:\n        move(20, 0, 40)\n    else:\n        move(0, 0, 40)\n    wait(20)\n")


def atom(s):
    """One step -> its program, or None."""
    n, col = times(s), colour(s)
    if re.fullmatch(r"(zastav|stuj|stop|zabrzdi|brzdi)( se)?", s):
        return "stop()\n"
    # answers and questions first: "kolik je tu stupnu" must not be read as a drive
    if re.search(r"stupn|teplot|teplo\b", s) and re.search(r"kolik|jaka|jak ", s):
        return show("temp()", ' + " C"')
    if re.search(r"vlhk|sucho", s):
        return show("humidity()", ' + " %"')
    if re.search(r"za tebou|za zady", s) and re.search(r"^je |^mas |neco", s):
        return yesno("behind() < 30", "ano, za mnou", "ne, nic")
    if re.search(r"jak daleko|vzdalenost|kolik centimetru", s):
        return show("distance()", ' + " cm"')
    if re.search(r"pred tebou|v ceste|prekazk", s) and re.search(r"^je |^vidis|^stoji", s):
        return yesno("distance() < 30", "ano, hned tady", "ne, nic")
    if re.search(r"hlucno|hluk|ticho", s) and re.search(r"^jak|^je ", s):
        return "while 1:\n    clear()\n    text(52, 28, str(sound()))\n    wait(100)\n"
    if re.search(r"naklon|rovne", s) and re.search(r"^stojis|^jsi ", s):
        return show("tilt()", ' + " st"')
    if re.search(r"kolik je hodin|jaky je (dnes )?den|budik", s):
        return say("nemam hodiny", "sad")
    if re.search(r"vyfot|fotk", s):
        return say("nemam kameru", "sad")
    if re.search(r"pocasi|vygoogli|internet", s):
        return say("nemam internet", "sad")
    if re.search(r"^(prines|dones|podej|otevri)", s):
        return say("nemam ruce", "sad")
    if re.search(r"nahlas|mluv|precti", s):
        return say("neumim mluvit", "sad")
    if re.search(r"^(ahoj|cau|nazdar|dobry den|zdravim)", s):
        return say("ahoj!", "happy") + WAVE
    if re.search(r"dobre rano|vstavat", s):
        return 'eyes("open")\n' + say("dobre rano!") + "tone(784, 150)\ntone(1047, 300)\n"
    if re.search(r"jak se mas", s):
        return say("vse ok!", "happy")
    if re.search(r"kdo te (vyrobil|postavil|udelal)", s):
        return 'eyes("heart")\nclear()\ntext(22, 20, "postaveny doma")\ntext(40, 36, "s laskou")\n'
    if re.search(r"vtip|rozesmej", s):
        return 'eyes("wink")\nclear()\ntext(19, 20, "proc sel robot")\ntext(22, 36, "pres silnici?")\nwait(2500)\n' \
               'clear()\ntext(13, 28, "mel to v programu")\n'
    if re.search(r"mam te rad|sikul|hodny|dobra prace|vyborne", s) and "nehodn" not in s:
        return 'eyes("heart")\ntone(523, 150)\ntone(659, 150)\ntone(784, 150)\ntone(1047, 300)\n'
    if re.search(r"zlobiv|nehodn|fuj|spatny robot", s):
        return 'stop()\neyes("sad")\nnod(-30)\ntone(784, 250)\ntone(659, 250)\ntone(523, 250)\ntone(392, 500)\nnod(0)\n'
    if re.search(r"jsi unaven", s):
        return say("kdepak!", "happy")
    if re.search(r"nudim|nuda", s):
        return say("pojd tancit!", "happy") + DANCE
    # the screen
    m = re.match(r"(?:napis|ukaz slovo|zobraz)(?: na (?:displej|obrazovku))? (.+)", s)
    if m:
        return say(m.group(1).strip('"')[:21])
    if re.search(r"nakresli|ukaz|namaluj", s):
        if "domec" in s or "dum" in s:
            return HOUSE
        if "srdic" in s or "srdce" in s:
            return HEART
        if "smajl" in s or "oblicej" in s:
            return SMILEY
    if re.search(r"usmej|zasmej", s):
        return 'eyes("happy")\n' + SMILEY
    if re.search(r"mrkni|zamrkej", s):
        return 'eyes("wink")\nwait(400)\neyes("open")\n'
    if re.search(r"tvar se|zatvar se|vypadas", s):
        e = next((v for k, v in EYES.items() if k in s), None)
        if e:
            return f'eyes("{e}")\n'
    # the arm and the head
    if re.search(r"zamavej|mavej", s):
        return WAVE if not n else WAVE.replace("range(2)", f"range({n})")
    if re.search(r"zvedni ruku|ruku nahoru", s):
        return "arm(180)\n"
    if re.search(r"ruku dolu|sundej ruku", s):
        return "arm(0)\n"
    if re.search(r"zakyvej|prikyvni|kyvni", s):
        return "for i in range(2):\n    nod(30)\n    wait(250)\n    nod(-15)\n    wait(250)\nnod(0)\n"
    if re.search(r"zavrt hlavou", s):
        return "for i in range(3):\n    look(-40)\n    wait(250)\n    look(40)\n    wait(250)\nlook(0)\n"
    if re.search(r"rozhledni", s):
        return "look(-90)\nwait(500)\nlook(90)\nwait(500)\nlook(0)\n"
    if re.search(r"podivej|koukni|divej", s) and re.search(r"dolev|doprav", s):
        return f'look({-60 if "dolev" in s else 60})\neyes("{"left" if "dolev" in s else "right"}")\n'
    # sound and light
    if re.search(r"pipni|zapipej|pipej|zatrub|trub|zahoukej|zapiskej", s):
        return "beep(250)\n" if not n or n == 1 else f"for i in range({n}):\n    beep(250)\n    wait(150)\n"
    if re.search(r"zhasni|vypni svetlo", s):
        return "rgb(0, 0, 0)\n"
    if re.search(r"blikej|zablikej", s) and col:
        return f"for i in range({n or 3}):\n    rgb({col[0]}, {col[1]}, {col[2]})\n    wait(300)\n    rgb(0, 0, 0)\n    wait(300)\n"
    if re.search(r"rozsvit|svit|zasvit", s) and col:
        return f"rgb({col[0]}, {col[1]}, {col[2]})\n"
    # driving
    if re.search(r"sleduj.* caru|jed po care", s):
        return LINE
    if re.search(r"ctverec", s):
        return "for n in range(4):\n    move(60, 0, 0, 1000)\n    move(0, 0, 60, 700)\n"
    if re.search(r"tancuj|zatancuj|tanec", s):
        return DANCE
    if re.search(r"otoc|zatoc|zaboc|toc se", s):
        if re.search(r"dokola|kolem", s):
            return "move(0, 0, 60, 2800)\n"
        if re.search(r"celem vzad|o 180", s):
            return "move(0, 0, 60, 1400)\n"
        if re.search(r"dolev|doprav", s):
            deg = number(s) if "stup" in s else 90
            return f"move(0, 0, {-60 if 'dolev' in s else 60}, {(deg or 90) * 700 // 90})\n"
    if re.search(r"^(jed|popojed|zajed|ujed|rozjed|couv|vyraz|jezdi)", s):
        back = bool(re.search(r"couv|dozadu|zpatky|vzad", s))
        v = 100 if re.search(r"rychle|naplno|plny plyn", s) else 30 if re.search(r"pomalu|pomalinku", s) else 60
        ms = duration(s)
        return f"move({-v if back else v}, 0, 0{', ' + str(ms) if ms else ''})\n"
    return None


def condition(s):
    if re.search(r"tlacitk|cudlik", s):
        return "button()"
    if re.search(r"hluk|tlesk|randal", s):
        return "sound() > 60"
    if re.search(r"zvedn|naklon", s):
        return "tilt() > 30"
    if re.search(r"stup|tepl|otepl|horko|chlad|zima", s):
        n = number(s)
        if n is not None:
            return f"temp() {'<' if re.search(r'mene|min |pod |chlad|zima', s) else '>'} {n}"
    if re.search(r"za tebou|zezadu", s):
        return "behind() < 20"
    if re.search(r"priblizi|blizko|pred tebou|prekazk", s):
        return "distance() < 30"
    return None


def parse(req):
    s = plain(req)
    m = re.match(r"(kdyz|pokud|kdykoli|pokazde kdyz|az|jakmile) (.+?), (?:tak )?(.+)", s)
    if m:
        cond, act = condition(m.group(2)), steps(m.group(3))
        if cond and act:
            if m.group(1) in ("az", "jakmile"):
                return f"while not ({cond}):\n    wait(20)\n" + act
            return f"while 1:\n    if {cond}:\n" + "".join("        " + l + "\n" for l in act.splitlines()) + "    wait(50)\n"
    return steps(s)


def steps(s):
    whole = atom(s)
    if whole:
        return whole
    parts = [p.strip() for p in re.split(r",? a (?:pak|potom|nakonec) |,? (?:pak|potom|nakonec) |, | a ", re.sub(r"^nejdriv(e)? ", "", s))
             if p.strip()]
    if len(parts) < 2:
        return None
    progs = [atom(p) for p in parts]
    return "".join(progs) if all(progs) else None


def main():
    for req in [l.strip() for l in open(sys.argv[1]) if l.strip()]:
        prog = parse(req) or say("to neumim", "sad")
        print(f"### {req}\n{prog.rstrip()}\n[runs]\n")


if __name__ == "__main__":
    main()
