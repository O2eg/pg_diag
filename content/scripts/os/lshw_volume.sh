#!/bin/sh
set -eu

lshw_output=""
if command -v lshw >/dev/null 2>&1; then
  if command -v sudo >/dev/null 2>&1; then
    lshw_output="$(LC_ALL=C sudo -n lshw -class volume -json 2>/dev/null || true)"
  fi
  if [ -z "$lshw_output" ]; then
    lshw_output="$(LC_ALL=C lshw -class volume -json 2>/dev/null || true)"
  fi
fi

compact_output="$(printf '%s' "$lshw_output" | tr -d '[:space:]')"
if [ -n "$compact_output" ] && [ "$compact_output" != "[]" ] && [ "$compact_output" != "{}" ]; then
  printf '%s\n' "$lshw_output"
  exit 0
fi

if ! command -v lsblk >/dev/null 2>&1; then
  echo "neither usable lshw volume data nor lsblk is available" >&2
  exit 3
fi

emit_lsblk_rows() {
  LC_ALL=C lsblk --json --list --bytes -o "$1" 2>/dev/null | awk '
    BEGIN { in_rows = 0; closed = 0 }
    !in_rows {
      if ($0 ~ /"blockdevices"[[:space:]]*:[[:space:]]*\[/) {
        print "["
        in_rows = 1
      }
      next
    }
    /^[[:space:]]*\][[:space:]]*$/ {
      print "]"
      closed = 1
      exit
    }
    { print }
    END { if (!in_rows || !closed) exit 1 }
  '
}

columns="NAME,PATH,PKNAME,TYPE,SIZE,FSTYPE,LABEL,UUID,FSAVAIL,FSUSE%,MOUNTPOINT,MODEL,SERIAL"
if emit_lsblk_rows "$columns"; then
  exit 0
fi
emit_lsblk_rows "NAME,PATH,TYPE,SIZE,FSTYPE,MOUNTPOINT" || {
  echo "lsblk did not return parseable JSON" >&2
  exit 1
}
