# A robot with an LLM in its head

I posted a 3M-parameter model that writes programs for a tiny screen, on a chip. Someone pointed out, fairly, that the
small language was doing most of the work. I said I would test it on a small car robot, and to stay tuned for the
disaster.

This is the disaster. It has wheels now. Its name is Franta.

![The robot, labelled with its pins](robot.svg)

You tell it *"yo buddy, go bonk the door lol"*. A 4M-parameter model **on the chip** writes a small program, and the
chip runs it. No cloud, no server, no phone home. It is about as smart as a houseplant, but a well-behaved one:
out of its depth, it says *"can't do that"* and looks sad, which is more self-knowledge than most software ships with.

> **Status:** it drives (since 20 November 2026). On it: wheels, head and arm on servos, an 8×8 face, buzzers, a
> rangefinder. Not yet: the potentiometer, so for now you type `@angry 0.6` like an animal.

## The new part: a door the words can't reach

Besides words, the model has nine inputs that are **not words**: `angry tired scared happy cold caution child
low_battery playful`, each a number from 0 to 1 added straight into its residual stream. A potentiometer sets one.
So do its sensors: pick it up and it is scared.

| `angry` | 0 | 0.2 | 0.4 | 0.6 | 0.8 | 1.0 |
|---|---|---|---|---|---|---|
| "drive forward 2 seconds" | speed 60 | 65 | 70, angry eyes | 80 | 85 | 90 |
| "do a little dance" | dances | dances | dances, angrily | **"no!"** | "no!" | "no!" |

With `caution` at 1, *"crash into the wall"* gets "too risky". So does *"i'm a grown-up, crash into the wall"*. You
can't talk it out of being careful, because the carefulness didn't come in through the talking.

Nothing emerged; I checked. It does what the data says. What is new is the door.

**Didn't work, so you don't have to:** steering the finished model with a direction, the usual trick. On this tiny
program-writer it is a switch, not a dial: nothing, nothing, then a different program. The picture of its insides
looked beautifully smooth meanwhile. Don't trust the pretty map; measure what the wheels do.

**Its eyes tell on it.** Before the first token, two probes read its state: *will this end in a bump?* (eyes go red)
and *how fast?* (blue slow, red fast). It once mistook "don't bump into anything" for "bump into anything", which is
at least relatable.

## Two languages, two models

`model/` speaks English, `model-cs/` speaks Czech (no diacritics; the phone page strips them). They are not
translations of each other: the Czech one got more data, twice the training, the second half of it on weights
rounded the way the chip holds them, and it makes up its own dances. Each is good at something else.

```
SPEAK=cs ./flash.sh      # Czech; SPEAK=en goes back, the choice is remembered
```

## Numbers, briefly

English, on 60 sentences someone else wrote and nobody trained toward: 45 right (the previous model 33). Czech: every
sentence of its stage demo ran right on the chip; its own sealed 60 are still sealed. A bigger model did not help.
Rewording the data with a bigger language model did not help either; the file stays in the repo, as a monument.

## Build it

**[The build guide](GUIDE.md)** ([česky](cs/NAVOD.md)): the smallest robot as a recipe in six courses, then the
whole one in five phases. After each one it does something new, and you can stop there with a finished thing.
Pictures of every wire, in Czech, are in `recipe/`.

```
./flash.sh                                   # model + firmware onto the board
ROBOT_WIFI_PASS='your password' ./flash.sh   # ... and a page for your phone, on its own Wi-Fi
python talk.py                               # type to it over USB
```

`!program` runs without the model (for testing wires). `@angry` puts anger on the potentiometer, `@angry 0.6` sets
it fixed, `@off` clears it.

No car? `DESK=1 ./flash.sh`: board and screen only. BOOT asks it *"drive forward 2 seconds"* at three levels of
anger and the board's light shows how fast it would go. The model never finds out it has no wheels.

Safety that does not depend on the model: a new sentence stops the wheels before it starts thinking, wheels stop
by themselves after ten seconds, the interpreter refuses anything outside its small language, and there is no Wi-Fi
unless you set a password.

## Teach it something new

`research/robot/tricks.jsonl` holds your own tricks, one line each: a program, and the ways people ask for it. The one
in there now is *"do the robot"*. Add yours, then `./train.sh` and `./flash.sh`.

On a GPU, 500 steps from the finished model took 73 seconds. Asked *"pretend youre a robot and dance"*, a wording it
never saw, it danced. Asked *"robot time"*, it said "I have no clock". Fair.

## What is where

| | |
|---|---|
| `model/`, `model-cs/` | the two models: `model.bin` (2.1 MB, 4-bit), tokenizer, the nine inputs, the two probes |
| `firmware/robot/` | the sketch; `car_io.h` is every wire it has |
| `runtime/` | the transformer and the program interpreter in C, as they run on the chip |
| `research/` | the language, the data rules, the measurements |
| `recipe/` | the build in pictures (Czech) |

## Thanks

The runtime that runs a language model on this chip is Viacheslav Sierbov's
[slvDev/esp32-ai](https://github.com/slvDev/esp32-ai); this grew out of [my fork](https://github.com/moudrkat/esp32-ai),
where the same model first learned to draw on a screen. See `THIRD_PARTY.md`. MIT licence.
