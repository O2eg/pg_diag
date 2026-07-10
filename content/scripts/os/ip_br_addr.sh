#!/bin/sh
set -eu

if ! command -v ip >/dev/null 2>&1; then
  echo "ip executable not found" >&2
  exit 3
fi

if ! network_output="$(LC_ALL=C ip -br addr 2>/dev/null)"; then
  network_output="$(LC_ALL=C ip addr show)"
fi

printf '%s\n' "$network_output"
printf '\n/etc/hosts\n'
if [ -r /etc/hosts ]; then
  cat /etc/hosts
else
  echo "/etc/hosts is unavailable" >&2
  exit 1
fi
