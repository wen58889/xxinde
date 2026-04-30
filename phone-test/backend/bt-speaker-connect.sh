#!/bin/bash
# Auto-connect Beoplay A1 bluetooth speaker and set as default audio output
pulseaudio --start 2>/dev/null || pulseaudio -D --fail=quiet 2>/dev/null
sleep 2
echo -e "power on\nconnect 00:12:6F:B3:3B:2A" | bluetoothctl
sleep 5
SINK=$(pactl list sinks short 2>/dev/null | grep bluez | head -1 | awk '{print $2}')
if [ -n "$SINK" ]; then
  pactl set-default-sink "$SINK" 2>/dev/null
  pactl set-sink-volume @DEFAULT_SINK@ 75% 2>/dev/null
fi
