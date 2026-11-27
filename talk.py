"""Type requests to the board running the oled model; its replies print as they come.

    uv run --no-project --with pyserial python scripts/oled_talk.py [/dev/ttyACM0]

Each line you type (draw a house, countdown from 5 then happy birthday, ...) is sent with a newline; the board
writes the program on its screen and runs it. Ctrl+C to quit.
"""
import sys
import unicodedata
import threading

import serial

port = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyACM0"
s = serial.Serial(port, 115200, timeout=0.2)


def read():
    while True:
        data = s.read(4096)
        if data:
            sys.stdout.write(data.decode(errors="replace"))
            sys.stdout.flush()


threading.Thread(target=read, daemon=True).start()
print(f"connected to {port}; type what to draw, Enter to send, Ctrl+C to quit")
try:
    while True:
        line = input()
        if line.strip():
            s.write((unicodedata.normalize("NFKD", line.strip()) + "\n").encode("ascii", "ignore"))   # "zazpívej" -> "zazpivej", as the phone page sends it
except (KeyboardInterrupt, EOFError):
    print()
