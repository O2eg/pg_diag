#!/bin/sh
set -eu

class_name="${1:-}"
if [ -z "$class_name" ]; then
  echo "[]"
  exit 0
fi

if ! command -v lshw >/dev/null 2>&1; then
  echo "lshw executable not found" >&2
  exit 3
fi

if command -v sudo >/dev/null 2>&1; then
  if LC_ALL=C sudo -n lshw -class "$class_name" -json 2>/dev/null; then
    exit 0
  fi
fi

LC_ALL=C lshw -class "$class_name" -json
