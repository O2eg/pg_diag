#!/bin/sh
set -eu

PATH="${PATH:+${PATH}:}/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
export PATH

sysctl_bin="$(command -v sysctl 2>/dev/null || true)"
if [ -z "$sysctl_bin" ]; then
  echo "sysctl executable not found" >&2
  exit 3
fi

LC_ALL=C "$sysctl_bin" -a 2>/dev/null | awk '/^net\.ipv4\.tcp/'
