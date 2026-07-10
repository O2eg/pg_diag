#!/bin/sh
set -eu

if ! command -v df >/dev/null 2>&1; then
  echo "df executable not found" >&2
  exit 3
fi

LC_ALL=C exec df -hP
