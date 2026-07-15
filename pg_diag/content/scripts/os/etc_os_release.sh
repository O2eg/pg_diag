#!/bin/sh
set -eu

if [ -r /etc/os-release ]; then
  exec cat /etc/os-release
fi
if [ -r /usr/lib/os-release ]; then
  exec cat /usr/lib/os-release
fi

echo "os-release file is unavailable" >&2
exit 3
