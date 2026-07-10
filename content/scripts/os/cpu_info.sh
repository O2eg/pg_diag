#!/bin/sh
set -eu

if ! command -v lscpu >/dev/null 2>&1; then
  echo "lscpu executable not found" >&2
  exit 3
fi

LC_ALL=C exec lscpu
