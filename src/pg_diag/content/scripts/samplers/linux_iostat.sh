#!/bin/sh
set -eu

if ! command -v iostat >/dev/null 2>&1; then
  echo "iostat executable not found" >&2
  exit 3
fi
exec iostat -dxk "$1" "$2"
