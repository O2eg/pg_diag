#!/bin/sh
set -eu

class_name="${1:-}"
if [ -z "$class_name" ]; then
  echo "[]"
  exit 0
fi

if ! command -v lshw >/dev/null 2>&1; then
  echo "[]"
  exit 0
fi

if command -v sudo >/dev/null 2>&1; then
  if sudo -n true >/dev/null 2>&1; then
    sudo -n lshw -class "$class_name" -json
    exit $?
  fi
fi

lshw -class "$class_name" -json
