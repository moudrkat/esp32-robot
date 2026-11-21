"""Czech for the robot: the same programs, asked for in Czech, written without diacritics (the phone page strips
them, the screen's font has none). Nothing here decides what the robot does: a request's program comes from gen.py,
and this file only says it in Czech. A fixed program gets its wordings from research/robot/phrases_cs.jsonl; a
program with a number, a word or a colour in it is read back and said by render(); what cannot be said is left out.

The texts the robot shows are Czech too (TEXT), so a Czech model answers "to neumim", not "can't do that".
"""
import re
import unicodedata

from research.oled import gen
from research.oled.gen import COLOURS, TURN90, cx, pick, say


def plain(s):
    """Czech as the model sees it: no diacritics, plain quotes."""
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.replace("„", '"').replace("“", '"').replace("”", '"').replace("’", "'").replace("–", "-")


# ---- what the robot shows: fixed texts, each at most 21 characters (the screen is 21 wide)
TEXT = {
    "can't do that": "to neumim", "hi!": "ahoj!", "tiny car": "male auticko", "I run on a chip": "bezim na cipu",
    "I'm awake!": "jsem vzhuru!", "nope!": "kdepak!", "you're welcome": "neni zac", "bye!": "pa!", "all good!": "vse ok!",
    "charge me": "nabij me", "low battery": "slaba baterie", "ask a grown-up": "zeptej se dospelych",
    "too risky": "moc riskantni", "no way": "ani nahodou", "no!": "ne!",
    "hey!": "hej!", "brr": "brr", "hot!": "horko!", "whoa": "ty jo", "wow": "wow", "ouch": "au", "hello": "ahoj",
    "careful": "pozor", "oops": "jejda", "help": "pomoc", "stop": "stuj", "boo": "baf", "yay": "hura", "ok": "ok",
    "thanks": "diky", "GO": "START", "done": "hotovo", "boom": "bum", "end": "konec", "ready": "pripraven",
}
assert all(len(v) <= 21 and v.isascii() for v in TEXT.values())
_TEXT_CALL = re.compile(r'text\((\d+), (\d+), "([^"]*)"\)')


def cs_prog(prog):
    """The program with its fixed screen texts in Czech, centred again where they were centred."""
    def one(m):
        x, y, s = int(m.group(1)), m.group(2), m.group(3)
        if s not in TEXT:
            return m.group(0)
        return f'text({cx(TEXT[s]) if x == cx(s) else x}, {y}, "{TEXT[s]}")'
    return _TEXT_CALL.sub(one, prog).replace('+ " deg")', '+ " st")')


# ---- small Czech
KRAT = {1: "jednou", 2: "dvakrat", 3: "trikrat", 4: "ctyrikrat", 5: "petkrat", 6: "sestkrat", 7: "sedmkrat", 8: "osmkrat"}
SLOVY = {1: "jedna", 2: "dva", 3: "tri", 4: "ctyri", 5: "pet", 6: "sest", 7: "sedm", 8: "osm", 9: "devet", 10: "deset"}
BARVA = {"red": ("cervene", "cervenou", "cervena"), "green": ("zelene", "zelenou", "zelena"),
         "blue": ("modre", "modrou", "modra"), "yellow": ("zlute", "zlutou", "zluta"),
         "orange": ("oranzove", "oranzovou", "oranzova"), "purple": ("fialove", "fialovou", "fialova"),
         "pink": ("ruzove", "ruzovou", "ruzova"), "white": ("bile", "bilou", "bila"),
         "cyan": ("azurove", "azurovou", "azurova"), "magenta": ("purpurove", "purpurovou", "purpurova")}
RGB = {v: k for k, v in COLOURS.items()}


def krat(r, n):
    return pick(r, [KRAT[n], KRAT[n], f"{n}x", f"{n} krat"]) if n in KRAT else f"{n}x"


def cislo(r, n):
    return pick(r, [str(n), str(n), SLOVY[n]]) if n in SLOVY else str(n)


def doba(r, ms):
    """How long, the way it is said: "2 vteriny", "na pet sekund", "kousek"."""
    if ms == 500:
        return pick(r, ["kousek", "trochu", "trosku", "o kousek", "chvilku"])
    if ms == 300:
        return pick(r, ["malinko", "o malinko", "jen malinko", "o chlup", "par centimetru"])
    if ms % 1000:
        return f"{ms} milisekund"
    n = ms // 1000
    v, s = (("vterinu", "sekundu") if n == 1 else ("vteriny", "sekundy") if n < 5 else ("vterin", "sekund"))
    w = {1: "jednu", 2: "dve"}.get(n, SLOVY.get(n, str(n)))
    if n == 1 and r.random() < 0.4:
        return pick(r, ["vterinu", "sekundu", "na vterinu", "na sekundu", "1 s"])
    return pick(r, [f"{n} {v}", f"{n} {s}", f"{w} {v}", f"{w} {s}", f"na {n} {v}", f"na {w} {s}", f"{n} s", f"po dobu {n} {s[:-1] if n == 1 else s}"])


RYCHLE = {10: ["plizive", "sotva se hybej", "krokem"], 15: ["extra pomalu", "uplne pomalinku"],
          20: ["hodne pomalu", "jako snek", "fakt pomalu"], 30: ["pomalu", "zvolna", "pomalicku"], 35: ["opatrne"],
          40: ["spis pomalu", "trochu pomalu"], 45: ["v klidu", "ne moc rychle", "pohodovym tempem"],
          50: ["polovicni rychlosti", "stredni rychlosti"], 70: ["svizne", "trochu rychleji"], 75: ["docela rychle"],
          90: ["rychle", "hodne rychle", "fakt rychle"], 95: ["strasne rychle"], 100: ["naplno", "plnou rychlosti", "co to da"]}


def rychlost(r, v):
    """Speed v as a phrase ("" for the ordinary 60), or None when nobody would say it."""
    if v == 60:
        return pick(r, ["", "", "", "normalni rychlosti"])
    if v in RYCHLE and r.random() < 0.7:
        return pick(r, RYCHLE[v])
    return pick(r, [f"rychlosti {v}", f"na {v} procent", f"na {v} %", f"vykon {v}", f"rychlost {v}"])


TEMPO = {100: ["hodne rychle", "bleskove"], 150: ["rychle", "svizne"], 300: [""], 600: ["pomalu", "zvolna"],
         1000: ["hodne pomalu", "pomalicku"]}


def kdyz(r, cond):
    """A condition as the words that follow "kdyz" / "az"."""
    m = re.fullmatch(r"distance\(\) < (\d+)", cond)
    if m:
        n = int(m.group(1))
        if n == 20 and r.random() < 0.8:
            return pick(r, ["je neco blizko", "se neco priblizi", "ti neco stoji v ceste", "je pred tebou prekazka",
                            "je neco tesne pred tebou", "ti neco zavazi"])
        if n == 30 and r.random() < 0.6:
            return pick(r, ["se nekdo priblizi", "nekdo prijde bliz", "k tobe nekdo prijde"])
        return pick(r, [f"je neco bliz nez {n} cm", f"je neco do {n} cm", f"je prekazka bliz nez {n} centimetru"])
    m = re.fullmatch(r"temp\(\) ([<>]) (\d+)", cond)
    if m:
        n, hot = int(m.group(2)), m.group(1) == ">"
        if hot and n == 28 and r.random() < 0.8:
            return pick(r, ["je horko", "je vedro", "se oteplí".replace("í", "i"), "je tu moc teplo"])
        if not hot and n == 20 and r.random() < 0.8:
            return pick(r, ["je zima", "se ochladi", "je tu chladno", "zacne byt zima"])
        return pick(r, [f"je vic nez {n} stupnu", f"teplota prekroci {n} stupnu", f"je tepleji nez {n} stupnu"]) if hot else \
            pick(r, [f"je mene nez {n} stupnu", f"teplota klesne pod {n} stupnu", f"je chladneji nez {n} stupnu"])
    fixed = {
        "humidity() > 70": ["je vlhko", "je dusno", "je vlhky vzduch", "stoupne vlhkost"],
        "track() > 0": ["uvidis caru", "najdes caru", "narazis na caru", "je pod tebou cara"],
        "track() == 3": ["jsi na care", "stojis na care", "najedes na caru"],
        "tilt() > 20": ["se naklonis", "stojis nakrivo", "te nekdo nakloni"],
        "tilt() > 30": ["te nekdo zvedne", "te zvednu", "te vezmu do ruky", "te nekdo zvedne ze zeme"],
        "shaken()": ["do tebe nekdo strci", "do neceho narazis", "s tebou zatresu", "do tebe tuknu", "do tebe nekdo drcne"],
        "sound() > 60": ["tlesknu", "uslysis tlesknuti", "je hluk", "uslysis ranu", "nekdo tleskne", "zatleskam"],
        "button()": ["zmacknu tlacitko", "stisknu tlacitko", "nekdo zmackne tlacitko", "zmacknu cudlik"],
        "behind() < 20": ["je neco za tebou", "se neco priblizi zezadu", "je neco tesne za tebou"],
    }
    return pick(r, fixed[cond]) if cond in fixed else None


SLOVA = ["ahoj", "mama", "tata", "pivo", "kafe", "robot", "auto", "Praha", "Brno", "Ostrava", "dobry den", "cau", "nazdar",
         "diky", "pozor", "start", "cil", "konec", "ano", "ne", "mozna", "hura", "jejda", "pes", "kocka", "Petra", "Honza",
         "Katka", "Ondra", "Tomas", "Jana", "Pavel", "Eva", "babicka", "deda", "skola", "prace", "obed", "vecere", "snidane",
         "leto", "zima", "snih", "slunce", "mesic", "hvezda", "kolo", "vlak", "letadlo", "lod", "dum", "strom", "kvet",
         "voda", "ohen", "vzduch", "zeme", "laska", "pratele", "rodina", "stesti", "sen", "noc", "den", "rano", "vecer",
         "dobrou noc", "dobre rano", "vsechno nejlepsi", "na zdravi", "to je ono", "jedeme", "stuj", "pojd sem", "lifehack",
         "vibecoding", "model", "cip", "neuron", "pozornost", "teplota", "fyzika", "kod", "chyba", "test", "demo", "FAIL"]
NEZNAME = ["slona", "zirafu", "draka", "jednorozce", "kocku", "psa", "konika", "rybu", "ptaka", "motyla", "pavouka", "medveda",
           "lva", "tygra", "opici", "zabu", "hada", "delfina", "tucnaka", "sovu", "lisku", "jezka", "mys", "kravu", "prase",
           "auto", "vlak", "letadlo", "lod", "raketu", "kolo", "traktor", "ponorku", "vrtulnik", "balon", "hrad", "most",
           "vez", "kostel", "strom", "kvetinu", "houbu", "jablko", "banan", "pizzu", "dort", "zmrzlinu", "kavu", "pivo",
           "klobouk", "botu", "bryle", "hodiny", "telefon", "pocitac", "klavesnici", "kytaru", "buben", "mic", "panacka",
           "kostlivce", "ducha", "mimozemstana", "robota", "kralovnu", "piraty", "dinosaura", "sopku", "horu", "more", "oblak",
           "blesk", "duhu", "mapu", "klic", "zamek", "mec", "stit", "korunu", "diamant", "portret", "krajinu", "zatisi"]
NEJDE = ["let", "letej", "vyskoc", "skoc", "jdi nahoru po schodech", "uvar mi kafe", "prines mi pivo", "otevri dvere",
         "najdi moje klice", "jdi do kuchyne", "udelej mi ukol", "uklid pokoj", "vylez na zed", "plav", "zavolej mame",
         "zapni televizi", "objednej pizzu", "udelej salto", "jdi ven", "udelej mi chleba", "vyvenci psa", "prines micek",
         "zvedni to", "precti mi maily", "zahraj si se mnou sachy", "uvar veceri", "umyj nadobi", "vynes kos", "vyluxuj",
         "zalij kytky", "nakrm kocku", "ustel postel", "poskladej pradlo", "oprav kolo", "natri plot"]
NEJDE_CO = [("prines", ["mi ovladac", "mi telefon", "mi klice", "mi pivo", "noviny", "mi boty", "mi bundu", "mi kafe"]),
            ("podej", ["mi ovladac", "mi telefon", "mi tuzku", "mi sul", "mi rucnik", "mi nabijecku"]),
            ("zavri", ["okno", "dvere", "lednicku", "skrin", "supliky"]), ("umyj", ["nadobi", "okna", "auto", "podlahu"]),
            ("uklid", ["kuchyn", "stul", "hracky", "garaz"]), ("kup", ["mleko", "chleba", "pivo", "listky do kina"]),
            ("najdi", ["moje bryle", "penezenku", "druhou ponozku", "ovladac"]), ("oprav", ["kohoutek", "zidli", "zasuvku"]),
            ("zvedni", ["ten papir", "tu krabici", "moji tasku", "ten kamen"]), ("nakrm", ["psa", "rybicky", "krecka"])]
PRED = ["prosim ", "hele ", "hej ", "tak ", "ted ", "muzes ", "mohl bys ", "prosim te ", "poslys ", "no tak ", "dobre, ",
        "ok ", "auticko, ", "robote, ", "kamo, ", "tak jo, ", "pojd, ", "zkus ", "chci abys ", "potrebuju abys "]
ZA = [" prosim", " diky", " hned", " ted", "!", ".", " at to vidim", " pro me", " no tak", " jo?", " ok?", " dik"]


def polish(r, p):
    """The request as someone might toss it at a toy: a word before, a word after, sometimes shouted."""
    k = r.random()
    if k < 0.22:
        pre = pick(r, PRED)
        if pre.rstrip().endswith("abys") or pre.startswith(("muzes", "mohl bys", "zkus")):
            return p                      # those need another verb form; the bank has them said properly
        p = pre + p
    if r.random() < 0.2:
        p = p.rstrip(".!?") + pick(r, ZA)
    if r.random() < 0.06:
        p = p.upper() if '"' not in p and "'" not in p else p
    elif r.random() < 0.3:
        p = p[0].upper() + p[1:]
    return p


def _q(r, w):
    q = pick(r, ['"', "'", "", "", ""])
    return f"{q}{w}{q}"


# ---- a program read back and said in Czech
def render(prog, r):
    """A Czech request for this program, or None when it is not one this file can say."""
    m = re.fullmatch(r'clear\(\)\ntext\((\d+), (\d+), "([^"]*)"\)\n', prog)
    if m:
        x, y, w = int(m.group(1)), int(m.group(2)), m.group(3)
        if w == "?":
            return pick(r, ["nakresli", "namaluj", "ukaz", "nakresli mi", "zobraz", "chci videt", "umis nakreslit", "udelej"]) + " " + pick(r, NEZNAME)
        kde = "" if (x, y) == (cx(w), 28) else {(cx(w), 0): "nahore", (cx(w), 56): "dole", (0, 0): "vlevo nahore",
                                              (0, 28): "vlevo"}.get((x, y))
        if kde is None:
            return None
        W_ = _q(r, w)
        p = pick(r, [f"napis {W_}", f"napis {W_}", f"ukaz {W_}", f"zobraz {W_}", f"vypis {W_}", f"napis slovo {W_}",
                     f"ukaz napis {W_}", f"dej na displej {W_}", f"chci videt {W_}", f"napis mi {W_}", f"at je na displeji {W_}",
                     f"{W_} na displej", f"text: {w}", f"ukaz mi slovo {W_}", f"hod na obrazovku {W_}", f"rekni {W_} na displeji"])
        if kde:
            p += " " + kde
        elif r.random() < 0.25:
            p += pick(r, [" na displej", " na obrazovku", " doprostred", " uprostred"])
        return p
    m = re.fullmatch(r'clear\(\)\ntext\(\d+, 20, "([^"]*)"\)\ntext\(\d+, 36, "([^"]*)"\)\n', prog)
    if m:
        a, b = _q(r, m.group(1)), _q(r, m.group(2))
        return pick(r, [f"napis {a} a pod to {b}", f"na prvni radek {a} a na druhy {b}", f"dva radky: {a} a {b}",
                        f"{a} nahoru a {b} dolu", f"napis {a} a pod tim {b}", f"horni radek {a}, dolni radek {b}",
                        f"dej {a} nad {b}", f"nejdriv {a} a pod nim {b}", f"napis {a} a {b} na dva radky"])
    m = re.fullmatch(r'for \w in range\((\d+)\):\n    clear\(\)\n    text\(\d+, 28, "([^"]*)"\)\n    wait\((\d+)\)\n    clear\(\)\n    wait\(\3\)\n', prog)
    if m and int(m.group(3)) in TEMPO:
        n, w, t = int(m.group(1)), _q(r, m.group(2)), pick(r, TEMPO[int(m.group(3))])
        return pick(r, [f"zablikej {w} {krat(r, n)}", f"blikej napisem {w} {krat(r, n)}", f"at {w} {krat(r, n)} zablika",
                        f"napis {w} a {krat(r, n)} s tim zablikej", f"{krat(r, n)} problikni slovo {w}",
                        f"blikej slovem {w} {krat(r, n)}"]) + (" " + t if t else "")
    m = re.fullmatch(r'for (\w) in range\((\d+), (\d+)(, -1)?\):\n    clear\(\)\n    text\(60, 28, str\(\1\)\)\n    wait\((\d+)\)\n(?:clear\(\)\ntext\(\d+, 28, "([^"]*)"\)\n)?', prog)
    if m and int(m.group(5)) in TEMPO:
        a, b, down, t, fin = int(m.group(2)), int(m.group(3)), bool(m.group(4)), pick(r, TEMPO[int(m.group(5))]), m.group(6)
        if down:
            p = pick(r, [f"odpocitej od {cislo(r, a)}", f"odpocet od {cislo(r, a)}", f"pocitej pozpatku od {cislo(r, a)}",
                         f"odpocitavej od {cislo(r, a)} do 1", f"udelej odpocet od {cislo(r, a)}", f"pocitej od {cislo(r, a)} dolu"])
        else:
            n = b - 1
            p = pick(r, [f"pocitej od 1 do {cislo(r, n)}", f"napocitej do {cislo(r, n)}", f"pocitej do {cislo(r, n)}",
                         f"ukaz cisla od 1 do {cislo(r, n)} jedno po druhem", f"pocitej od jedne do {cislo(r, n)}"])
        if t:
            p += " " + t
        if fin:
            p += pick(r, [f" a pak ukaz {fin}", f" a pak napis {fin}", f", potom {fin}", f" a na konec {fin}", f" a skonci s {fin}"])
        return p
    m = re.fullmatch(r"for \w in range\((\d+)\):\n    fill\(0, 0, 128, 64\)\n    wait\((\d+)\)\n    clear\(\)\n    wait\(\2\)\n", prog)
    if m and int(m.group(2)) in TEMPO:
        n, t = int(m.group(1)), pick(r, TEMPO[int(m.group(2))])
        cnt = "" if n == 3 and r.random() < 0.5 else " " + krat(r, n)
        return pick(r, ["zablikej displejem", "problikni obrazovku", "blikni displejem", "zablikej obrazovkou",
                        "at displej zablika", "blikej celym displejem"]) + cnt + (" " + t if t else "")
    m = re.fullmatch(r"for \w in range\((\d+)\):\n    led\(1\)\n    wait\((\d+)\)\n    led\(0\)\n    wait\(\2\)\n", prog)
    if m and int(m.group(2)) in TEMPO and int(m.group(1)) in KRAT:
        n, t = int(m.group(1)), pick(r, TEMPO[int(m.group(2))])
        return pick(r, ["zablikej ledkou", "blikni diodou", "zablikej svetylkem na desce", "rozsvit a zhasni ledku",
                        "zablikej kontrolkou", "blikej ledkou"]) + " " + krat(r, n) + (" " + t if t else "")
    m = re.fullmatch(r"for \w in range\((\d+)\):\n    beep\((\d+)\)\n    wait\(\2\)\n", prog)
    if m and int(m.group(2)) in TEMPO and int(m.group(1)) in KRAT:
        n, t = int(m.group(1)), pick(r, TEMPO[int(m.group(2))])
        return pick(r, ["pipni", "zapipej", "zabzuc", "pipni bzucakem", "at bzucak pipne", "udelej pip"]) + " " + krat(r, n) + (" " + t if t else "")
    m = re.fullmatch(r"move\((-?\d+), 0, 0\)\nwait\((\d+)\)\nstop\(\)\n", prog)
    if m:
        v, ms = int(m.group(1)), int(m.group(2))
        sp = rychlost(r, abs(v))
        verb = pick(r, ["jed dozadu", "couvej", "couvni", "jed zpatky", "zacouvej", "popojed dozadu", "ujed dozadu"]) if v < 0 else \
            pick(r, ["jed dopredu", "jed rovne", "popojed dopredu", "jed vpred", "ujed dopredu", "vyraz dopredu", "jed"])
        if abs(v) == 100 and v > 0 and r.random() < 0.3:
            verb, sp = pick(r, ["slapni na to", "dupni na plyn", "plny plyn"]), ""
        return f"{verb} {doba(r, ms)}" + (f" {sp}" if sp else "")
    m = re.fullmatch(r"move\(0, 0, (-?60)\)\nwait\((\d+)\)\nstop\(\)\n", prog)
    if m:
        side, ms = ("doprava" if int(m.group(1)) > 0 else "doleva"), int(m.group(2))
        deg = ms * 90 // TURN90
        if deg in (30, 45, 60, 120, 270) or (deg in (90, 180) and r.random() < 0.3):
            return pick(r, [f"otoc se o {deg} stupnu {side}", f"zatoc {side} o {deg} stupnu", f"{deg} stupnu {side}",
                            f"natoc se o {deg} stupnu {side}"])
        return None                       # the plain turns and spins are in the bank
    m = re.fullmatch(r"move\((-?\d+), 0, 0\)\n", prog)
    if m:
        v = int(m.group(1))
        if v <= 0 or v == 60:
            return None
        return pick(r, ["jed", "jezdi", "pokracuj", "jed dal", "jed dopredu"]) + " " + pick(r, [f"rychlosti {v}", f"na {v} procent", f"na {v} %"] + RYCHLE.get(v, []))
    m = re.fullmatch(r"move\((\d+), 0, 0\)\nwhile distance\(\) > (\d+):\n    wait\(20\)\nstop\(\)\n", prog)
    if m:
        v, n = int(m.group(1)), int(m.group(2))
        sp = rychlost(r, v)
        return pick(r, [f"jed dopredu, dokud neni neco bliz nez {n} cm", f"jed a zastav {n} cm pred zdi",
                        f"jed, dokud nebudes {n} cm od prekazky", f"dojed {n} centimetru pred prekazku",
                        f"jed rovne a zastav {n} cm pred necim"]) + (f" {sp}" if sp else "")
    m = re.fullmatch(r"move\((\d+), 0, 0\)\nwhile shaken\(\) == 0:\n    wait\(20\)\nstop\(\)\n(move\(-60, 0, 0\)\nwait\(800\)\nstop\(\)\n)?", prog)
    if m:
        sp = rychlost(r, int(m.group(1)))
        p = pick(r, ["jed, dokud do neceho nenarazis", "naraz do zdi", "nabourej do neceho", "jed az do narazu",
                     "napal to do zdi", "jed dokud nenabouras"])
        if m.group(2):
            p += pick(r, [" a pak couvni", " a vycouvej", " a potom kousek zpatky", ", pak couvni"])
        return p + (f" {sp}" if sp else "")
    m = re.fullmatch(r"move\((\d+), 0, 0\)\nwhile 1:\n    if tilt\(\) > 30:\n        stop\(\)\n    wait\(20\)\n", prog)
    if m:
        sp = rychlost(r, int(m.group(1)))
        return pick(r, ["jed dopredu a zastav, kdyz te nekdo zvedne", "jed, ale stuj, kdyz te zvednu",
                        "jed a kdyz te vezmu do ruky, zastav"]) + (f" {sp}" if sp else "")
    m = re.fullmatch(r"move\(-40, 0, 0\)\nwhile behind\(\) > (\d+):\n    wait\(20\)\nstop\(\)\n", prog)
    if m:
        n = m.group(1)
        return pick(r, [f"couvej, dokud neni neco {n} cm za tebou", f"zacouvej {n} cm od prekazky", f"couvej a zastav {n} centimetru pred zdi vzadu"])
    m = re.fullmatch(r"for \w in range\((\d+)\):\n    look\(-40\)\n    wait\(250\)\n    look\(40\)\n    wait\(250\)\nlook\(0\)\n", prog)
    if m and int(m.group(1)) in KRAT:
        return pick(r, ["zavrt hlavou", "zakrut hlavou", "rekni ne hlavou", "zavrt hlavou ze ne"]) + " " + krat(r, int(m.group(1)))
    m = re.fullmatch(r"for \w in range\((\d+)\):\n    rgb\((\d+), (\d+), (\d+)\)\n    wait\(400\)\n    rgb\(0, 0, 0\)\n    wait\(400\)\n", prog)
    if m and (int(m.group(2)), int(m.group(3)), int(m.group(4))) in RGB and int(m.group(1)) in KRAT:
        c = BARVA[RGB[(int(m.group(2)), int(m.group(3)), int(m.group(4)))]]
        return pick(r, [f"zablikej {c[0]}", f"blikej {c[0]}", f"blikni {c[1]}", f"zablikej {c[1]} barvou"]) + " " + krat(r, int(m.group(1)))
    m = re.fullmatch(r"for \w in range\(4\):\n    move\(60, 0, 0\)\n    wait\((\d+)\)\n    move\(0, 0, 60\)\n    wait\(700\)\nstop\(\)\n", prog)
    if m and m.group(1) in ("500", "1000", "2000"):
        size = {"500": "maly ", "1000": "", "2000": "velky "}[m.group(1)]
        return pick(r, [f"objed {size}ctverec", f"jed do {size.replace('y ', 'eho ')}ctverce" if size else "jed do ctverce",
                        f"udelej na zemi {size}ctverec", f"projed {size}ctverec"])
    m = re.fullmatch(r"for \w in range\((\d+)\):\n    move\(60, 0, 40\)\n    wait\(600\)\n    move\(60, 0, -40\)\n    wait\(600\)\nstop\(\)\n", prog)
    if m and int(m.group(1)) in KRAT:
        return pick(r, ["jed cikcak", "klickuj", "udelej cikcak", "jed klikate", "jed slalom"]) + (" " + krat(r, int(m.group(1))) if int(m.group(1)) != 3 or r.random() < 0.3 else "")
    # ---- "kdyz X, udelej Y" as c_react writes them
    m = re.fullmatch(r"while 1:\n    if (.+):\n        rgb\((\d+), (\d+), (\d+)\)\n    else:\n        rgb\(0, 0, 0\)\n    wait\(50\)\n", prog)
    if m and (int(m.group(2)), int(m.group(3)), int(m.group(4))) in RGB:
        t, c = kdyz(r, m.group(1)), BARVA[RGB[(int(m.group(2)), int(m.group(3)), int(m.group(4)))]]
        return t and pick(r, [f"svit {c[0]}, kdyz {t}", f"kdyz {t}, rozsvit se {c[0]}", f"kdyz {t}, sviť {c[0]}".replace("ť", "t"),
                              f"zmen barvu na {c[1]}, kdyz {t}", f"pokud {t}, bud {c[2] if False else c[0]}"])
    m = re.fullmatch(r"while 1:\n    if (.+):\n        beep\(150\)\n    wait\(50\)\n", prog)
    if m:
        t = kdyz(r, m.group(1))
        return t and pick(r, [f"pipni, kdyz {t}", f"zatrub, kdyz {t}", f"kdyz {t}, pipni", f"varuj me, kdyz {t}",
                              f"udelej hluk, kdyz {t}", f"kdyz {t}, zakric", f"zajecej, kdyz {t}", f"dej mi vedet, kdyz {t}",
                              f"pokud {t}, zapipej", f"ozvi se, kdyz {t}"])
    m = re.fullmatch(r'while 1:\n    clear\(\)\n    if (.+):\n        text\(\d+, 28, "([^"]*)"\)\n    wait\(50\)\n', prog)
    if m:
        t, w = kdyz(r, m.group(1)), m.group(2)
        return t and pick(r, [f"napis {w}, kdyz {t}", f"kdyz {t}, ukaz {w}", f"rekni {w}, kdyz {t}", f"pokud {t}, napis {w}",
                              f"kdyz {t}, at je na displeji {w}"])
    m = re.fullmatch(r"while 1:\n    if (.+):\n        move\(-60, 0, 0\)\n        wait\(800\)\n        stop\(\)\n    wait\(50\)\n", prog)
    if m:
        t = kdyz(r, m.group(1))
        return t and pick(r, [f"couvni, kdyz {t}", f"kdyz {t}, ucouvni", f"utec, kdyz {t}", f"kdyz {t}, jed kousek dozadu",
                              f"pokud {t}, vycouvej"])
    m = re.fullmatch(r"move\((\d+), 0, 0\)\nwhile not \((.+)\):\n    wait\(20\)\nstop\(\)\n", prog)
    if m:
        t, sp = kdyz(r, m.group(2)), rychlost(r, int(m.group(1)))
        return t and pick(r, [f"jed, dokud {('ne' + t) if False else t} - pak zastav", f"jed dopredu a zastav, kdyz {t}",
                              f"jed, a az {t}, zastav", f"jed a stuj, jakmile {t}"]) + (f" {sp}" if sp else "")
    return None


# ---- the talk families, in Czech (the same programs as gen.py's c_seq, c_when, ...)
UKAZ = ['napis "{w}"', "napis {w} na displej", 'ukaz "{w}"', "ukaz slovo {w}", 'zobraz "{w}"', 'dej na displej "{w}"',
        "vypis {w}", "ukaz {w} na obrazovce", "napis na displej {w}", "at je na displeji {w}", "ukaz moje jmeno: {w}",
        "jmenuju se {w}, ukaz to", "zobraz text {w}", "muzes ukazat {w}", "hlaskuj {w} na displeji", "displej: {w}",
        'text "{w}" prosim', "chci na displeji videt {w}", "ukaz na obrazovce tohle: {w}", "napis tohle: {w}",
        'hod tam slovo "{w}"', "rekni {w} pisemne", "napis mi tam {w}"]
CEKEJ = ["pockej {n}", "cekej {n}", "pauza {n}", "pockej {n} a nic nedelej", "vydrz {n}", "zustan stat {n}", "dej si pauzu {n}"]


def _slovo(r):
    w = pick(r, SLOVA) if r.random() < 0.5 else gen.word(r)[:14]
    if r.random() < 0.25:
        w = w.upper() if r.random() < 0.5 else w.capitalize()
    return w


def _bare(s):
    s = s.rstrip(" .!?").strip()
    return s[0].lower() + s[1:] if s[:1].isupper() and not s[:2].isupper() else s


def _step(r, last=False):
    k = r.random()
    if last and gen.GOES and k < 0.12:
        prog = pick(r, gen.GOES)
        return _bare(pick(r, gen.BANK[prog])), prog
    if k < 0.1:
        w = _slovo(r)
        return pick(r, UKAZ).format(w=w), say(w)
    if k < 0.18 and not last:
        n = r.randint(1, 5)
        return pick(r, CEKEJ).format(n=doba(r, n * 1000)), f"wait({n * 1000})\n"
    if k < 0.36:
        _, prog = gen.c_drive(r)
        p = render(prog, r)
        return (p, prog) if p else _step(r, last)
    prog = pick(r, gen.ATOMS)
    return _bare(pick(r, gen.BANK[prog])), prog


def c_seq(r):
    n = pick(r, [2, 2, 2, 2, 3, 3, 3, 4])
    steps = [_step(r, last=i == n - 1) for i in range(n)]
    if len({s[1] for s in steps}) < n or sum(len(s[1]) for s in steps) > 420:
        return c_seq(r)
    ps, prog = [s[0] for s in steps], "".join(s[1] for s in steps)
    k = r.random()
    if n == 2 and k < 0.18:
        a, b = ps
        return pick(r, [f"{b}, ale nejdriv {a}", f"nez {b}, tak {a}", f"{b}, ale predtim {a}", f"{b} - vlastne pockej, nejdriv {a}",
                        f"{b}, ale jeste pred tim {a}"]), prog
    if k < 0.36:
        mid = "".join(pick(r, [", pak ", ". pak ", ", potom ", ". potom ", ", a pak "]) + s for s in ps[1:-1])
        end = pick(r, [", pak ", ", a nakonec ", ". nakonec ", ", a potom ", ", a na zaver ", ". pak "]) + ps[-1]
        return pick(r, ["nejdriv ", "nejdrive ", "nejprve ", "zacni tim: ", "tak nejdriv ", "1) "]) + ps[0] + mid + end, prog
    if k < 0.44:
        return " ".join(f"{i + 1}. {s}" for i, s in enumerate(ps)) if r.random() < 0.5 else " -> ".join(ps), prog
    if k < 0.52:
        return ". ".join(s[0].upper() + s[1:] for s in ps) + ".", prog
    glue = [pick(r, [" pak ", " a pak ", ", pak ", " a ", ", ", " potom ", " a potom ", "; ", ", nasleduje: ", " a dal ",
                     ", a az to bude, ", " a taky ", ", pote "]) for _ in range(n - 1)]
    return ps[0] + "".join(g + s for g, s in zip(glue, ps[1:])), prog


CONDS = ["sound() > 60", "button()", "tilt() > 30", "shaken()", "distance() < 20", "behind() < 20", "track() > 0",
         "temp() > 28", "temp() < 20", "humidity() > 70"]


def c_when(r):
    k = r.random()
    cond = f"distance() < {pick(r, [5, 10, 15, 25, 30, 40, 50])}" if k < 0.1 else \
        f"temp() {pick(r, ['<', '>'])} {r.randint(15, 30)}" if k < 0.2 else pick(r, CONDS)
    t = kdyz(r, cond)

    def act():
        if r.random() < 0.12:
            w = pick(r, ["au", "hej!", "ahoj!", "ty jo", "jejda", "pomoc", "stuj", "baf", "hura", "ne!", "ok", "diky", _slovo(r)[:10]])
            if r.random() < 0.4:
                w = w.upper()
            return pick(r, UKAZ).format(w=w), say(w)
        prog = pick(r, gen.ATOMS)
        while any(x in prog for x in ("beep(250)", "rgb(")) or prog.count("\n") > 9:
            prog = pick(r, gen.ATOMS)
        return _bare(pick(r, gen.BANK[prog])), prog

    a, prog = act()
    if r.random() < 0.2:
        a2, prog2 = act()
        if prog2 != prog and len(prog) + len(prog2) < 260:
            a, prog = a + pick(r, [" a ", " a pak ", ", pak ", " a taky "]) + a2, prog + prog2
    once = r.random() < 0.4
    if once and r.random() < 0.3:
        if r.random() < 0.5 and gen.GOES:
            g = pick(r, gen.GOES)
            a, prog = _bare(pick(r, gen.BANK[g])), g
        else:
            _, prog = gen.c_drive(r)
            a = render(prog, r)
    if not once:
        p = pick(r, [f"kdyz {t}, {a}", f"pokud {t}, {a}", f"kdykoli {t}, {a}", f"pokazde kdyz {t}, {a}", f"{a}, kdyz {t}",
                     f"{a}, pokud {t}", f"{a}, kdykoli {t}", f"vzdycky kdyz {t}, {a}", f"kdyz {t}, tak {a}",
                     f"{a} pokazde, kdyz {t}", f"jakmile {t}, {a} - a tak porad", f"kdyz {t}, chci abys udelal tohle: {a}"])
        return p, f"while 1:\n    if {cond}:\n" + "".join("        " + l + "\n" for l in prog.splitlines()) + "    wait(50)\n"
    p = pick(r, [f"pockej, az {t}, a pak {a}", f"jakmile {t}, {a}", f"az {t}, {a}", f"{a}, jakmile {t}",
                 f"nedelej nic, dokud {t.replace('je ', 'neni ', 1) if False else 'ne' + t if False else t}, a pak {a}",
                 f"{a}, ale az potom, co {t}", f"cekej, az {t}, a potom {a}", f"pockej si, az {t}, pak {a}",
                 f"ve chvili, kdy {t}, {a}", f"{a}, az {t}", f"stuj, dokud ne{'' if True else ''}prijde tohle: {t}. pak {a}"])
    return p, f"while not ({cond}):\n    wait(20)\n" + prog


def c_curve(r):
    left = r.random() < 0.5
    s = "doleva" if left else "doprava"
    return pick(r, [f"jed a zatacej mirne {s}", f"jed obloukem {s}", f"jed dopredu a stac to {s}", f"jed mirnou zatackou {s}",
                    f"jed a drz se trochu {s}", f"vezmi to obloukem {s}", f"jed a pomalu zatacej {s}", f"sirokou zatackou {s}",
                    f"jed rovne, ale tahni to {s}", f"udelej siroky oblouk {s}", f"jed porad, mirne {s}"]), \
        f"move(60, 0, {-30 if left else 30})\n"


KNOB = [
    (["nastavuj rychlost knoflikem", "at rychlost ridi knoflik", "knoflik je tvuj plyn", "jed tak rychle, jak rika knoflik",
      "rychlost podle potenciometru", "budu ti rychlost nastavovat knoflikem", "ridim ti rychlost potenciometrem",
      "knoflikem ti davam plyn"], "while 1:\n    move(knob(), 0, 0)\n    wait(50)\n"),
    (["zatacej podle knofliku", "budu te ridit knoflikem", "knoflik je tvuj volant", "ridim te potenciometrem",
      "jed a zatacej, jak tocim knoflikem", "knoflik urcuje smer"], "while 1:\n    move(50, 0, knob() - 50)\n    wait(50)\n"),
    (["ztlumuj svetlo knoflikem", "knoflik nastavuje jas", "at knoflik ridi, jak moc svitis", "svit tak silne, jak rika knoflik",
      "jas podle potenciometru", "stmivej svetlo knoflikem"],
     "while 1:\n    k = knob() * 255 // 100\n    rgb(k, k, k)\n    wait(50)\n"),
    (["nastavuj barvu svetla knoflikem", "at knoflik vybira barvu", "knoflik meni barvu svetla", "prechazej z modre do cervene knoflikem",
      "barva podle potenciometru", "barvu svetla ridim knoflikem"],
     "while 1:\n    k = knob() * 255 // 100\n    rgb(k, 0, 255 - k)\n    wait(50)\n"),
    (["otacej hlavou podle knofliku", "at knoflik hybe hlavou", "divej se tam, kam ukazuje knoflik", "knoflik miri tvoji hlavu",
      "hlava podle potenciometru", "rozhlizej se knoflikem"], "while 1:\n    look(knob() * 180 // 100 - 90)\n    wait(50)\n"),
    (["ukaz hodnotu knofliku", "co rika knoflik", "kde je knoflik nastaveny", "ukaz polohu knofliku",
      "zobraz hodnotu potenciometru", "jak moc je knoflik otoceny", "dej hodnotu knofliku na displej"],
     "while 1:\n    clear()\n    text(52, 28, str(knob()))\n    wait(100)\n"),
    (["jed, dokud drzim tlacitko", "jed jen kdyz je tlacitko zmacknute", "jed, dokud tlacitko drzim, a pak stuj",
      "drzim tlacitko = jed, pustim = stuj", "tlacitko je tvuj plyn", "jed, kdyz drzim cudlik, a zastav, kdyz ho pustim"],
     "while 1:\n    if button():\n        move(60, 0, 0)\n    else:\n        stop()\n    wait(20)\n"),
    (["trub, dokud drzim tlacitko", "tlacitko je tvuj klakson", "pipej, dokud je tlacitko zmacknute",
      "delej hluk, kdyz drzim tlacitko"], "while 1:\n    if button():\n        beep(100)\n    wait(20)\n"),
]


def c_knob(r):
    ws, prog = pick(r, KNOB)
    return pick(r, ws), prog


def c_show(r):
    w = _slovo(r)[:21]
    return pick(r, UKAZ).format(w=w), say(w)


def c_blink2(r):
    a, b = r.sample(list(COLOURS), 2)
    ca, cb, A, B = COLOURS[a], COLOURS[b], BARVA[a], BARVA[b]
    n = pick(r, [3, 3, 3, 2, 4, 5])
    cnt = "" if n == 3 else f" {krat(r, n)}"
    p = pick(r, [f"blikej {A[0]} a {B[0]}", f"zablikej {A[0]} a {B[0]}", f"stridej {A[1]} a {B[1]}", f"blikej {A[0]}, pak {B[0]}",
                 f"stridej svetlo mezi {A[1]} a {B[1]}", f"prepinej {A[1]} a {B[1]}", f"{A[2]}, {B[2]}, {A[2]}, {B[2]}",
                 f"blikej stridave {A[0]} a {B[0]}", f"at svetlo blika {A[0]} a {B[0]}", f"problikavej {A[1]} a {B[1]}"]) + cnt
    return p, (f"for i in range({n}):\n    rgb({ca[0]}, {ca[1]}, {ca[2]})\n    wait(300)\n"
               f"    rgb({cb[0]}, {cb[1]}, {cb[2]})\n    wait(300)\nrgb(0, 0, 0)\n")


def c_answer(r):
    from research.robot.answers_cs import ANSWERS
    _, examples, prog = pick(r, ANSWERS)
    return pick(r, gen.BANK.get(prog, []) + examples), prog


def c_cant(r):
    if r.random() < 0.35:
        p = pick(r, NEJDE)
    else:
        v, things = pick(r, NEJDE_CO)
        p = f"{v} {pick(r, things)}"
    return p, 'eyes("sad")\n' + say("can't do that")      # cs_prog turns the text into "to neumim"


c_cant.__name__ = "c_cant"
TALK = [c_seq, c_when, c_curve, c_knob, c_answer, c_show, c_blink2]
