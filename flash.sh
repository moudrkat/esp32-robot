#!/bin/sh
# Build the firmware and put the robot's model on the board: the model into its flash partition, then the program.
#   ./flash.sh [port]                          (default /dev/ttyACM0)
#   ROBOT_WIFI_PASS='at least 8 chars' ./flash.sh   also gives it its own Wi-Fi "esp32-robot" and a page for your phone
#   DESK=1 ./flash.sh                          no car: just the board and its screen (see "On the table" in the README)
#   ATTN=1 DESK=1 ./flash.sh                   the 8x8 LEDs show one attention head while the model writes
#   DESK=1 SHT=4,5 ./flash.sh                  the same, with an SHT40 thermometer on pins 4 (SDA) and 5 (SCL)
# Needs arduino-cli with the esp32 core and these libraries:
#   arduino-cli core install esp32:esp32
#   arduino-cli lib install "Adafruit SSD1306" "Adafruit GFX Library" "Adafruit NeoPixel"
set -e
cd "$(dirname "$0")"
PORT=${1:-/dev/ttyACM0}
FQBN='esp32:esp32:esp32s3:UploadSpeed=921600,USBMode=hwcdc,CDCOnBoot=cdc,UploadMode=default,CPUFreq=240,FlashMode=qio,FlashSize=16M,PartitionScheme=custom,PSRAM=opi'
WIFI=firmware/robot/generated/wifi.h
if [ -n "${ROBOT_WIFI_PASS:-}" ]; then
  [ ${#ROBOT_WIFI_PASS} -ge 8 ] || { echo "ROBOT_WIFI_PASS needs at least 8 characters"; exit 1; }
  printf '#define CAR_WEB 1\n#define CAR_WIFI_PASS "%s"\n' "$ROBOT_WIFI_PASS" > "$WIFI"
  echo "Wi-Fi on: network esp32-robot, your password, page at http://192.168.4.1"
else
  rm -f "$WIFI"
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
if [ "${ATTN:-0}" = 1 ]; then
  printf '#define CAR_ATTN 1\n#define LLM_ATTN_VIZ 1\n' > "$ATTNH"
  echo "Attention on the 8x8 LEDs (pin 21): BOOT or @head for the next head, @head 2 3 for layer 2 head 3"
else
  rm -f "$ATTNH"
fi
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
