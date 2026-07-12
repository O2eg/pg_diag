#!/bin/sh
set -eu

if ! command -v df >/dev/null 2>&1; then
  echo "df executable not found" >&2
  exit 3
fi

LC_ALL=C df -P -B1 | awk '
function escape_json(value) {
  gsub(/\\/, "\\\\", value)
  gsub(/"/, "\\\"", value)
  gsub(/\t/, "\\t", value)
  gsub(/\r/, "\\r", value)
  gsub(/\n/, "\\n", value)
  return value
}
BEGIN { print "["; first = 1 }
NR == 1 { next }
NF >= 6 {
  mount_point = $6
  for (i = 7; i <= NF; i++) mount_point = mount_point " " $i
  used_pct = $5
  sub(/%$/, "", used_pct)
  if (!first) print ","
  first = 0
  printf "  {\"filesystem\":\"%s\",\"total_bytes\":%s,", escape_json($1), $2
  printf "\"used_bytes\":%s,\"available_bytes\":%s,", $3, $4
  printf "\"used_pct\":%s,\"mount_point\":\"%s\"}", used_pct, escape_json(mount_point)
}
END { print "\n]" }
'
