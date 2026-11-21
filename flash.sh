#!/bin/sh
# Build the firmware and put the robot's model on the board: the model into its flash partition, then the program.
#   ./flash.sh [port]                          (default /dev/ttyACM0)
#   ROBOT_WIFI_PASS='at least 8 chars' ./flash.sh   also gives it its own Wi-Fi "esp32-robot" and a page for your phone
#   HOME_WIFI_NAME='yours' HOME_WIFI_PASS='...' ./flash.sh   it joins your Wi-Fi too (HOME_WIFI_NAME=0 forgets); WIFI_OFF=1: no radio
#   DESK=1 ./flash.sh                          no car: just the board and its screen (see "On the table" in the README)
#   ATTN=1 DESK=1 ./flash.sh                   the 8x8 LEDs show one attention head while the model writes
#   FLIP=right ./flash.sh                      the right wheels ran backwards on move(60, 0, 0): left | right | both;
#                                              remembered for the next flash, FLIP=none forgets it
#   KICK=150 ./flash.sh                        weak batteries: full power for 150 ms whenever a side starts from rest;
#                                              remembered for the next flash, KICK=0 forgets it
#   COAST=3000 ./flash.sh                      a drive nobody stopped ends after 3 s instead of 10 (remembered; COAST=0 forgets)
#   DESK=1 SHT=4,5 ./flash.sh                  the same, with an SHT40 thermometer on pins 4 (SDA) and 5 (SCL)
# Needs arduino-cli with the esp32 core and these libraries:
#   arduino-cli core install esp32:esp32
#   arduino-cli lib install "Adafruit SSD1306" "Adafruit GFX Library" "Adafruit NeoPixel"
set -e
cd "$(dirname "$0")"
PORT=${1:-/dev/ttyACM0}
FQBN='esp32:esp32:esp32s3:UploadSpeed=921600,USBMode=hwcdc,CDCOnBoot=cdc,UploadMode=default,CPUFreq=240,FlashMode=qio,FlashSize=16M,PartitionScheme=custom,PSRAM=opi'
WIFI=firmware/robot/generated/wifi.h      # remembered between flashes, like FLIP; WIFI=0 turns the radio off
HOME_LINES=$(grep '^#define HOME_WIFI' "$WIFI" 2>/dev/null || true)
if [ -n "${ROBOT_WIFI_PASS:-}" ]; then
  [ ${#ROBOT_WIFI_PASS} -ge 8 ] || { echo "ROBOT_WIFI_PASS needs at least 8 characters"; exit 1; }
  printf '#define CAR_WEB 1\n#define CAR_WIFI_PASS "%s"\n' "$ROBOT_WIFI_PASS" > "$WIFI"
  [ -n "$HOME_LINES" ] && printf '%s\n' "$HOME_LINES" >> "$WIFI"
fi
if [ -n "${HOME_WIFI_NAME:-}" ]; then      # also join this network (yours), so a laptop on it can reach the robot
  [ -f "$WIFI" ] || { echo "HOME_WIFI_NAME needs ROBOT_WIFI_PASS too, at least once"; exit 1; }
  grep -v '^#define HOME_WIFI' "$WIFI" > "$WIFI.tmp" && mv "$WIFI.tmp" "$WIFI"
  [ "$HOME_WIFI_NAME" = 0 ] || printf '#define HOME_WIFI_NAME "%s"\n#define HOME_WIFI_PASS "%s"\n' "$HOME_WIFI_NAME" "${HOME_WIFI_PASS:-}" >> "$WIFI"
fi
[ "${WIFI_OFF:-0}" = 1 ] && rm -f "$WIFI"
if [ -f "$WIFI" ]; then
  echo "Wi-Fi on: network esp32-robot, your password, page at http://192.168.4.1"
  grep -q '^#define HOME_WIFI_NAME' "$WIFI" && echo "  and a guest on $(sed -n 's/^#define HOME_WIFI_NAME "\(.*\)"$/\1/p' "$WIFI"): the address is printed when it connects (http://esp32-robot.local)"
else
  echo "Wi-Fi off (set ROBOT_WIFI_PASS to turn the phone page on)"
fi
DESKH=firmware/robot/generated/desk.h
if [ "${DESK:-0}" = 1 ]; then
  echo '#define CAR_DESK 1' > "$DESKH"
  [ -n "${SHT:-}" ] && printf '#define SHT_SDA %s\n#define SHT_SCL %s\n' "${SHT%,*}" "${SHT#*,}" >> "$DESKH"
  echo "On the table: no motors, the screen shows the program and the speed; BOOT steps the input"
else
  rm -f "$DESKH"
fi
ATTNH=firmware/robot/generated/attn.h
case "${ATTN:-}" in                    # remembered, like FLIP: ATTN=0 forgets it
  1) printf '#define CAR_ATTN 1\n#define LLM_ATTN_VIZ 1\n' > "$ATTNH" ;;
  0) rm -f "$ATTNH" ;;
esac
[ -f "$ATTNH" ] && echo "Attention on the 8x8 LEDs (pin 21): on the car \"@attn\" switches eyes and attention; BOOT or @head for the next head"
WHEELS=firmware/robot/generated/wheels.h
case "${FLIP:-}" in
  left)  echo '#define MOTOR_L_SIGN -1' > "$WHEELS" ;;
  right) echo '#define MOTOR_R_SIGN -1' > "$WHEELS" ;;
  both)  printf '#define MOTOR_L_SIGN -1\n#define MOTOR_R_SIGN -1\n' > "$WHEELS" ;;
  none)  rm -f "$WHEELS" ;;
  "")    ;;
  *)     echo "FLIP is left, right, both or none"; exit 1 ;;
esac
KICKH=firmware/robot/generated/kick.h
case "${KICK:-}" in
  "") ;;
  0) rm -f "$KICKH" ;;
  *[!0-9]*) echo "KICK is milliseconds, like 150"; exit 1 ;;
  *) printf '#define MOTOR_KICK_MS %s\n' "$KICK" > "$KICKH" ;;
esac
COASTH=firmware/robot/generated/coast.h
case "${COAST:-}" in
  "") ;;
  0) rm -f "$COASTH" ;;
  *[!0-9]*) echo "COAST is milliseconds, like 3000"; exit 1 ;;
  *) printf '#define CAR_COAST_MS %s\n' "$COAST" > "$COASTH" ;;
esac
[ -f "$COASTH" ] && echo "Leash: a drive left running stops after $(cut -d' ' -f3 "$COASTH") ms"
[ -f "$KICKH" ] && echo "Start kick: $(cut -d' ' -f3 "$KICKH") ms of full power"
[ -f "$WHEELS" ] && echo "Wheels flipped: $(tr '\n' ' ' < "$WHEELS")"
ESPTOOL=$(command -v esptool || command -v esptool.py || ls -d "${ARDUINO_DATA_DIR:-$HOME/.arduino15}"/packages/esp32/tools/esptool_py/*/esptool 2>/dev/null | sort -V | tail -1)
[ -n "$ESPTOOL" ] || { echo "esptool not found: pip install esptool"; exit 1; }
[ "${BUILD_ONLY:-0}" = 1 ] && { arduino-cli compile --fqbn "$FQBN" --build-property "upload.maximum_size=2097152" --build-path build firmware/robot; exit 0; }
echo "=== build"
arduino-cli compile --fqbn "$FQBN" --build-property "upload.maximum_size=2097152" --build-path build firmware/robot
echo "=== model -> $PORT (partition 'model' at 0x210000)"
"$ESPTOOL" --chip esp32s3 --port "$PORT" --baud 921600 write_flash 0x210000 model/model.bin
echo "=== firmware -> $PORT"
arduino-cli upload -p "$PORT" --fqbn "$FQBN" --input-dir build firmware/robot
echo "done. Talk to it: python talk.py   (pip install pyserial)"
