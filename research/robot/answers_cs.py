"""The Czech robot's answers in words: the same meanings as answers.py, shown in Czech without diacritics.
Each entry is (key, a few Czech ways to ask, the program). The wordings in phrases_cs.jsonl are written for the
meanings in answers.py (same keys), by a large model."""
from research.oled.gen import cx


def one(s, eyes=None):
    return (f'eyes("{eyes}")\n' if eyes else "") + f'clear()\ntext({cx(s)}, 28, "{s}")\n'


def two(a, b, eyes=None):
    return (f'eyes("{eyes}")\n' if eyes else "") + f'clear()\ntext({cx(a)}, 20, "{a}")\ntext({cx(b)}, 36, "{b}")\n'


def yesno(cond, yes, no):
    return (f"while 1:\n    clear()\n    if {cond}:\n        text({cx(yes)}, 28, \"{yes}\")\n    else:\n"
            f"        text({cx(no)}, 28, \"{no}\")\n    wait(200)\n")


ANSWERS = [
    ("no_clock", ["kolik je hodin", "nastav budik na sedmou", "jaky je dnes den"], one("nemam hodiny", "sad")),
    ("no_camera", ["vyfot me", "jakou barvu ma moje tricko", "poznavas me"], one("nemam kameru", "sad")),
    ("no_voice", ["rekni moje jmeno nahlas", "mluv na me", "precti to nahlas"], one("neumim mluvit", "sad")),
    ("no_ears", ["slysel jsi, co jsem rekla", "jakym jazykem mluvim", "poslouchej me"], one("slysim jen hluk", "sad")),
    ("no_net", ["jake bude zitra pocasi", "vygoogli to", "zavolej mame", "pust despacito"], one("nemam internet", "sad")),
    ("no_memory", ["na co jsem se ptala predtim", "zapamatuj si moje jmeno", "udelej to samy co vcera"], one("vsechno zapomenu", "sad")),
    ("no_hands", ["prines mi kafe", "podej mi tuzku", "otevri okno"], one("nemam ruce", "sad")),
    ("no_wings", ["vyletni ke stropu", "preskoc to", "jed bokem", "vylez po schodech"], one("mam jen kola, promin", "sad")),
    ("no_brain", ["kolik je dva plus dva", "kdo je prezident", "napis mi basnicku", "preloz to do nemciny"],
     two("moc tezke na", "maly mozek", "dizzy")),
    ("no_body", ["privonej ke kafi", "zvaz to jablko", "kolik merim"], one("na to nemam cidlo", "sad")),
    ("q_blocked", ["je neco pred tebou", "stoji ti neco v ceste", "vidis prekazku"], yesno("distance() < 30", "ano, hned tady", "ne, nic")),
    ("q_clear", ["je volna cesta", "muzes bezpecne jet dopredu", "je volno"], yesno("distance() < 30", "ne, je tam prekazka", "ano, volno")),
    ("q_behind", ["je neco za tebou", "mas neco za zady"], yesno("behind() < 30", "ano, za mnou", "ne, nic")),
    ("q_button", ["je zmacknute tlacitko", "drzim ti tlacitko"], yesno("button()", "ano, zmacknute", "ne, neni")),
    ("q_line", ["vidis caru", "jsi na pasce", "je pod tebou cara"], yesno("track() > 0", "ano, cara", "tady cara neni")),
    ("q_level", ["stojis rovne", "stojis na rovine", "je podlaha rovna"], yesno("tilt() < 10", "ano, rovne", "ne, nakrivo")),
    ("q_quiet", ["je tu ticho", "je v mistnosti klid"], yesno("sound() < 40", "ano, ticho", "ne, hluk")),
    ("q_hot", ["je tu moc horko", "je tu vedro, nebo se mi to zda"], yesno("temp() > 26", "ano, je horko", "ne, je to dobry")),
    ("q_cold", ["je tu zima", "mrzne tu, nebo co"], yesno("temp() < 18", "ano, je zima", "ne, je to dobry")),
    ("joke", ["rekni mi vtip", "rozesmej me", "znas nejaky vtip"],
     'eyes("wink")\nclear()\ntext(19, 20, "proc sel robot")\ntext(22, 36, "pres silnici?")\nwait(2500)\nclear()\n'
     'text(13, 28, "mel to v programu")\neyes("happy")\ntone(1200, 80)\ntone(1800, 80)\n'),
    ("skills", ["co umis", "pomoc", "jake mas triky", "ukaz, co v tobe je"],
     'eyes("happy")\nclear()\ntext(10, 12, "jezdim, tocim se")\ntext(4, 28, "kreslim, pipam, hraju")\ntext(16, 44, "citim, mavam")\n'),
    ("age", ["kolik ti je", "kdy ses narodil"], one("jsem uplne novy!", "happy")),
    ("maker", ["kdo te vyrobil", "kdo te postavil", "kdo je tvuj tvurce"], two("postaveny doma", "s laskou", "heart")),
    ("home", ["odkud jsi", "kde bydlis"], one("z dilenskeho stolu", "happy")),
    ("is_robot", ["jsi robot", "co presne jsi", "jsi hracka"], two("roboticke auto", "male, ale opravdove", "happy")),
    ("smart", ["jsi chytry", "jak moc jsi chytry", "jak velky mas mozek"], two("maly mozek", "velke srdce", "wink")),
    ("likes_me", ["mas me rad", "jsme kamaradi", "mas me rada"], one("jasne!", "heart")),
    ("fav_colour", ["jaka je tvoje oblibena barva", "kterou barvu mas nejradsi"], 'rgb(160, 0, 255)\n' + one("fialova!", "happy")),
    ("morning", ["dobre rano", "dobre ranko auticko", "vstavat"],
     'eyes("open")\n' + one("dobre rano!") + "tone(784, 150)\ntone(1047, 300)\n"),
    ("sorry", ["promin", "moje chyba", "nemyslela jsem to tak", "odpust mi"], one("to nic!", "happy")),
    ("bored", ["nudim se", "to je nuda", "zabav me"],
     one("pojd tancit!", "happy") + "for i in range(3):\n    move(0, 0, 80)\n    wait(300)\n    move(0, 0, -80)\n    wait(300)\nstop()\n"),
    ("ready", ["jsi pripraveny", "muzem vyrazit?", "pripraven?"], one("pripraven!", "happy") + "tone(1200, 80)\ntone(1800, 80)\n"),
    ("startled", ["vylekal jsi me", "ty jsi me vydesil", "takhle se ke me neplizit", "lekla jsem se", "to jsem se lekla",
                  "vystrasil jsi me", "jezis, to jsem se lekla"], one("promin!", "sad")),
    ("evening", ["dobry vecer", "dobry vecer auticko", "dobre odpoledne", "vecer robote", "dobry den",
                 "dobre odpoledne auticko", "dobry den preju"], one("dobry den!", "happy")),
    ("hungry", ["mas hlad", "chces svacinu", "das si pivo"], two("jen baterie,", "dekuju", "wink")),
]
for _k, _ex, _prog in ANSWERS:
    import re as _re
    assert all(len(s) <= 21 and s.isascii() for s in _re.findall(r'text\(\d+, \d+, "([^"]*)"\)', _prog)), _k
