#!/bin/sh
set -eu

if ! command -v lshw >/dev/null 2>&1; then
  echo "lshw executable not found" >&2
  exit 3
fi

if command -v sudo >/dev/null 2>&1; then
  if LC_ALL=C sudo -n lshw -class storage -json 2>/dev/null; then
    exit 0
  fi
fi

LC_ALL=C exec lshw -class storage -json
