#!/bin/sh
set -eu

if [ ! -r /etc/fstab ]; then
  echo "/etc/fstab is unavailable" >&2
  exit 3
fi

exec cat /etc/fstab
