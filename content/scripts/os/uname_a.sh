#!/bin/sh
set -eu

if ! command -v uname >/dev/null 2>&1; then
  echo "uname executable not found" >&2
  exit 3
fi

LC_ALL=C uname -a
