#!/bin/sh
set -eu

if [ ! -r /proc/meminfo ]; then
  echo "/proc/meminfo is unavailable" >&2
  exit 3
fi

awk '
$1 == "MemTotal:" {
  bytes = $2 * 1024
  printf "%.2f GiB (%.0f bytes)\n", bytes / 1073741824, bytes
  found = 1
}
END { if (!found) exit 1 }
' /proc/meminfo
