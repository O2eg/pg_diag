#!/bin/sh
set -eu

if ! command -v sysctl >/dev/null 2>&1; then
  echo "sysctl executable not found" >&2
  exit 3
fi

LC_ALL=C sysctl -a 2>/dev/null | awk '/^vm\./'
