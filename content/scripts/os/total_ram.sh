#!/bin/sh
set -eu

if [ ! -r /proc/meminfo ]; then
  echo "/proc/meminfo is unavailable" >&2
  exit 3
fi

total_kib="$(awk '$1 == "MemTotal:" { print $2; found = 1 } END { if (!found) exit 1 }' /proc/meminfo)"
total_bytes=$((total_kib * 1024))
printf '[{"total_ram_bytes":%s}]\n' "$total_bytes"
