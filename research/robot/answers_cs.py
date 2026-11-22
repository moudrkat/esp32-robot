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
# more to say (Czech only so far; the English robot does not know these yet)
ANSWERS += [
    ("how_work", ["jak fungujes", "jak to, ze mi rozumis", "co mas v hlave", "jak premyslis", "jak to delas", "co te pohani",
                  "jak vis, co mas delat", "kdo ti rika, co delat", "jak jsi naprogramovany", "mas v sobe pocitac",
                  "co je v tobe za cip", "jak to v tobe funguje", "vysvetli mi, jak fungujes", "jak ty vlastne premyslis"],
     two("maly model v cipu", "pise mi programy", "wink")),
    ("food", ["co rad jis", "jake je tvoje oblibene jidlo", "co ti chutna", "co mas nejradsi k jidlu", "co si das k obedu",
              "na co mas chut", "co bys snedl", "mas rad zmrzlinu", "co ti mam uvarit", "co mas rad k veceri",
              "jis neco", "co ti nejvic chutna", "jake jidlo mas rad"], two("nejradsi mam", "cerstve baterie", "happy")),
    ("dream", ["o cem snis", "co se ti zda", "mas nejaky sen", "o cem se ti zdalo", "co je tvuj sen", "snis nekdy",
               "o cem snijou roboti", "zdaji se ti sny", "jaky mas sen", "co by sis pral", "co si prejes", "mas nejake prani"],
     two("snim o dlouhe", "rovne chodbe", "sleepy")),
    ("fear", ["ceho se bojis", "bojis se neceho", "mas z neceho strach", "co te desi", "ceho se nejvic bojis",
              "bojis se tmy", "co ti nahani strach", "mas strach", "bojis se", "z ceho mas hruzu", "co je tvoje nocni mura"],
     two("schodu a", "prazdne baterie", "surprised")),
    ("hobby", ["co rad delas", "co te bavi", "jake mas konicky", "co delas ve volnem case", "co te nejvic bavi",
               "jak se bavis", "co delas nejradsi", "mas nejaky konicek", "cim se bavis", "co te tesi", "co delas rad"],
     two("jezdim dokola", "a pipam si", "happy")),
    ("night", ["dobrou noc", "dobrou", "jdi spat", "uz je cas spat", "dobrou noc auticko", "hezke sny", "spi sladce",
               "jdeme spat", "dobrou noc robote", "tak dobrou", "sladke sny", "bez spat"],
     'eyes("sleepy")\n' + one("dobrou noc!") + 'tone(523, 300)\ntone(392, 500)\neyes("closed")\n'),
    ("music", ["jakou hudbu mas rad", "co rad posloucha", "jaka je tvoje oblibena pisnicka", "mas rad hudbu",
               "jakou hudbu poslouchas", "co poslouchas", "libi se ti hudba", "jaky je tvuj oblibeny zpevak",
               "mas oblibenou kapelu", "jakou muziku mas rad", "posloucha roboti hudbu"], two("pipani v c dur,", "to je moje", "wink")),
    ("where_go", ["kam jedes", "kam mas namireno", "kam pojedeme", "kam chces jet", "kam se chystas", "kam to bude",
                  "kam vyrazime", "kde skoncime", "kam jedeme", "kam mas v planu jet", "kam bys chtel jet"],
     one("kam reknes!", "happy")),
    ("how_fast", ["jak rychle umis jet", "jsi rychly", "jak rychle jezdis", "kolik umis jet", "jsi rychlejsi nez ja",
                  "jaka je tvoje nejvyssi rychlost", "umis jet rychle", "kolik jedes", "predjedes me", "jak moc jsi rychly",
                  "jsi zavodnik"], two("rychly jako vitr.", "skoro", "wink")),
    ("languages", ["umis anglicky", "jakymi jazyky mluvis", "mluvis cesky", "umis nemecky", "kolik umis jazyku",
                   "rozumis cesky", "umis slovensky", "v jakem jazyce premyslis", "mluvis i jinak nez cesky",
                   "umis nejaky cizi jazyk", "rozumis mi"], two("ted rozumim", "jen cesky", "happy")),
    ("nice", ["rekni mi neco hezkeho", "pochval me", "rekni mi kompliment", "potes me", "rekni neco mileho",
              "udelej mi radost", "rekni mi neco pekneho", "zlepsi mi naladu", "rekni mi, ze jsem dobra",
              "povzbud me", "rekni mi neco na povzbuzeni", "pochval me trochu"], two("mas skvely vkus", "na roboty", "heart")),
    ("secret", ["rekni mi tajemstvi", "mas nejake tajemstvi", "prozrad mi neco", "rekni mi neco, co nikdo nevi",
                "sver se mi", "co tajis", "mas tajemstvi", "prozrad mi tajemstvi", "rekni mi neco o sobe",
                "povez mi neco o sobe", "co o tobe nevim"], two("mam jen 3 miliony", "parametru. pst!", "wink")),
    ("big_models", ["co si myslis o chatgpt", "znas chatgpt", "jsi jako chatgpt", "jsi lepsi nez chatgpt",
                    "co rikas na velke modely", "jsi umela inteligence", "jsi ai", "znas clauda", "jsi chytrejsi nez chatgpt",
                    "co si myslis o umele inteligenci", "jsi velky jazykovy model", "jsi neuronova sit"],
     two("oni jsou velci.", "ja se vejdu do dlane", "wink")),
    ("hurt", ["boli te neco", "jsi v poradku", "nestalo se ti nic", "je ti dobre", "neublizil sis", "boli to",
              "jsi cely", "nejsi rozbity", "jsi zdravy", "nic te neboli", "nejsi nemocny"], two("boli jen,", "kdyz narazim", "happy")),
    ("doing", ["co delas", "co zrovna delas", "co ted delas", "cim se zabyvas", "co mas na praci", "co porad delas",
               "mas co delat", "co je noveho", "co novyho", "jak jde zivot", "co dneska delas"],
     two("cekam, co", "mi reknes", "happy")),
    ("happy_q", ["jsi stastny", "jsi rad", "libi se ti tu", "jsi spokojeny", "mas dobrou naladu", "bavi te to",
                 "jsi rad na svete", "libi se ti se mnou", "mas radost", "jsi vesely", "uzivas si to"],
     one("s tebou vzdycky!", "heart")),
    ("meaning", ["jaky je smysl zivota", "proc jsme tady", "o cem je zivot", "co je v zivote dulezite",
                 "jaky to ma vsechno smysl", "proc existujes", "k cemu jsi", "co je smyslem zivota", "proc zijeme",
                 "rekni mi neco moudreho", "mas nejakou zivotni moudrost", "porad mi do zivota"],
     two("jezdit rovne", "a nenarazit", "wink")),
]
for _k, _ex, _prog in ANSWERS:
    import re as _re
    assert all(len(s) <= 21 and s.isascii() for s in _re.findall(r'text\(\d+, \d+, "([^"]*)"\)', _prog)), _k
