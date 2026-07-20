#!/bin/sh
set -eu

if ! command -v mount >/dev/null 2>&1; then
  echo "mount executable not found" >&2
  exit 3
fi

LC_ALL=C exec mount
