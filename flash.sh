#!/bin/sh
# Build the firmware and put the robot's model on the board: the model into its flash partition, then the program.
#   ./flash.sh [port]                          (default /dev/ttyACM0)
#   ROBOT_WIFI_PASS='at least 8 chars' ./flash.sh   also gives it its own Wi-Fi "esp32-robot" and a page for your phone
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
