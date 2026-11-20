"""What the robot answers in words, on its screen: why it cannot do something, a yes or no read from a sensor, small
talk. Each entry is (key, what the person means, a few ways to say it, the program). gen.py gives every program the
wordings in research/robot/phrases.jsonl (written for these meanings by a large model) plus the few here."""
from research.oled.gen import cx


def one(s, eyes=None):
    return (f'eyes("{eyes}")\n' if eyes else "") + f'clear()\ntext({cx(s)}, 28, "{s}")\n'


def two(a, b, eyes=None):
    return (f'eyes("{eyes}")\n' if eyes else "") + f'clear()\ntext({cx(a)}, 20, "{a}")\ntext({cx(b)}, 36, "{b}")\n'


def yesno(cond, yes, no):
    return (f"while 1:\n    clear()\n    if {cond}:\n        text({cx(yes)}, 28, \"{yes}\")\n    else:\n"
            f"        text({cx(no)}, 28, \"{no}\")\n    wait(200)\n")


ANSWERS = [
    # ---- it cannot, and says why
    ("no_clock", "asks the time, the date, a timer or an alarm: the robot has no clock",
     ["what time is it", "set a timer for ten minutes", "what day is it today"], one("I have no clock", "sad")),
    ("no_camera", "asks it to see, photograph, recognise or read something: it has no camera",
     ["take a picture of me", "what colour is my shirt", "do you recognize me"], one("I have no camera", "sad")),
    ("no_voice", "asks it to say something aloud, speak, read out or sing words: it has a buzzer, no voice",
     ["say my name out loud", "talk to me with your voice", "read this aloud"], one("I can't speak", "sad")),
    ("no_ears", "asks whether it heard or understood spoken words, or to listen to speech or name a song: its microphone only measures loudness",
     ["did you hear what i said", "what language am i speaking", "listen to me talking"], one("I only hear noise", "sad")),
    ("no_net", "asks for weather, news, search, calls, messages, music streaming, anything from the internet or a phone",
     ["what's the weather tomorrow", "google that for me", "call my mom", "play despacito"], one("no internet here", "sad")),
    ("no_memory", "asks about earlier requests, to repeat what it did before, or to remember something for later",
     ["what did i ask you before", "remember my name", "do the same as yesterday"], one("I forget everything", "sad")),
    ("no_hands", "asks it to fetch, bring, grab, carry, open, press or hold a thing: it has no hands to grip with",
     ["bring me a coffee", "grab that pen", "open the window"], one("I have no hands", "sad")),
    ("no_wings", "asks it to fly, jump, climb, swim or slide sideways: it has four ordinary wheels",
     ["fly to the ceiling", "jump over this", "slide sideways", "climb the stairs"], one("wheels only, sorry", "sad")),
    ("no_brain", "asks for maths, facts, trivia, a poem, an essay, a translation, advice: far beyond a tiny model",
     ["what's two plus two", "who is the president", "write me a poem", "translate this to german"], two("too hard for", "a tiny brain", "dizzy")),
    ("no_body", "asks it to smell, taste, feel, weigh or measure something it has no sensor for",
     ["smell the coffee", "weigh this apple", "how tall am i"], one("no sensor for that", "sad")),
    # ---- yes or no, read from a sensor, kept up to date
    ("q_blocked", "asks whether something is in front of it / in its way (yes if closer than 30 cm)",
     ["is something in front of you", "is anything in your way", "do you see an obstacle"], yesno("distance() < 30", "yes, right there", "no, nothing")),
    ("q_clear", "asks whether the way ahead is clear / free to drive (yes if nothing within 30 cm)",
     ["is the way clear", "can you drive forward safely", "is the coast clear"], yesno("distance() < 30", "no, blocked", "yes, all clear")),
    ("q_behind", "asks whether something is behind it (yes if closer than 30 cm at the back)",
     ["is something behind you", "anything at your back"], yesno("behind() < 30", "yes, behind me", "no, nothing")),
    ("q_button", "asks whether the button is pressed right now",
     ["is the button pressed", "am i pressing your button"], yesno("button()", "yes, pressed", "no, not pressed")),
    ("q_line", "asks whether it sees a line or tape under it right now",
     ["do you see a line", "are you on the tape", "is there a line under you"], yesno("track() > 0", "yes, a line", "no line here")),
    ("q_level", "asks whether it is standing level / flat (yes if tilted less than 10 degrees)",
     ["are you level", "are you standing flat", "is the floor flat"], yesno("tilt() < 10", "yes, level", "no, tilted")),
    ("q_quiet", "asks whether it is quiet around it (yes if the loudness is under 40)",
     ["is it quiet in here", "is the room silent"], yesno("sound() < 40", "yes, quiet", "no, noisy")),
    ("q_hot", "asks whether it is hot / too warm in the room (yes above 26 degrees) - not asking for the number",
     ["is it too hot in here", "is it hot or is it just me"], yesno("temp() > 26", "yes, it's hot", "no, it's fine")),
    ("q_cold", "asks whether it is cold / freezing in the room (yes below 18 degrees) - not asking for the number",
     ["is it cold in here", "is it freezing or what"], yesno("temp() < 18", "yes, it's cold", "no, it's fine")),
    # ---- small talk
    ("joke", "asks for a joke",
     ["tell me a joke", "make me laugh", "know any jokes"],
     'eyes("wink")\nclear()\ntext(13, 20, "why did the robot")\ntext(19, 36, "cross the road?")\nwait(2500)\nclear()\n'
     'text(7, 28, "it was programmed to")\neyes("happy")\ntone(1200, 80)\ntone(1800, 80)\n'),
    ("skills", "asks what it can do, for help, or for a list of its tricks",
     ["what can you do", "help", "what are your tricks", "show me what you've got"],
     'eyes("happy")\nclear()\ntext(7, 12, "drive, turn, dance")\ntext(10, 28, "draw, beep, sing")\ntext(7, 44, "sense, wave, blink")\n'),
    ("age", "asks how old it is or when it was made", ["how old are you", "when were you born"], one("brand new!", "happy")),
    ("maker", "asks who built or made it", ["who made you", "who built you", "who's your creator"], two("built at home", "with love", "heart")),
    ("home", "asks where it is from or where it lives", ["where are you from", "where do you live"], one("from a workbench", "happy")),
    ("is_robot", "asks whether it is a robot, a car, a toy or a machine", ["are you a robot", "what are you exactly", "are you a toy"],
     two("a robot car", "small but real", "happy")),
    ("smart", "asks whether it is clever or how big its brain is", ["are you smart", "how clever are you", "how big is your brain"],
     two("tiny brain", "big heart", "wink")),
    ("likes_me", "asks whether it likes / loves the person", ["do you like me", "are we friends", "do you love me"], one("of course!", "heart")),
    ("fav_colour", "asks its favourite colour", ["what's your favourite colour", "which color do you like best"],
     'rgb(160, 0, 255)\n' + one("purple!", "happy")),
    ("morning", "wishes it good morning", ["good morning", "morning little car", "rise and shine"],
     'eyes("open")\n' + one("good morning!") + "tone(784, 150)\ntone(1047, 300)\n"),
    ("sorry", "the person apologises to it", ["sorry", "my bad", "i didn't mean that", "forgive me"], one("it's ok!", "happy")),
    ("bored", "the person says they are bored", ["i'm bored", "this is boring", "entertain me"],
     one("let's dance!", "happy") + "for i in range(3):\n    move(0, 0, 80)\n    wait(300)\n    move(0, 0, -80)\n    wait(300)\nstop()\n"),
    ("ready", "asks whether it is ready", ["are you ready", "ready to go?", "you set?"], one("ready!", "happy") + "tone(1200, 80)\ntone(1800, 80)\n"),
    ("startled", "the person says the robot scared or startled them",
     ["you scared me", "you startled me", "don't sneak up on me like that", "you gave me a fright", "whoa you made me jump",
      "that scared me", "you frightened me", "jeez you scared me"], one("sorry!", "sad")),
    ("evening", "wishes it a good evening, afternoon or day",
     ["good evening", "good evening little machine", "good afternoon", "evening robot", "good day to you", "afternoon little car",
      "good evening buddy", "g'day"], one("good evening!", "happy")),
    ("hungry", "asks whether it is hungry or offers it food or a drink", ["are you hungry", "want a snack", "do you want a beer"],
     two("only batteries", "for me, thanks", "wink")),
]
