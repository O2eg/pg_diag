#!/bin/sh
set -eu

meminfo_path=/proc/meminfo
if [ ! -r "$meminfo_path" ]; then
  echo "/proc/meminfo is unavailable" >&2
  exit 3
fi

awk -F: '
function escape_json(value) {
  gsub(/\\/, "\\\\", value)
  gsub(/"/, "\\\"", value)
  return value
}
BEGIN {
  split("MemTotal MemFree MemAvailable Buffers Cached SwapCached Active Inactive Active(anon) Inactive(anon) Active(file) Inactive(file) Unevictable Dirty Writeback AnonPages Mapped Shmem KReclaimable Slab SReclaimable SUnreclaim KernelStack PageTables CommitLimit Committed_AS VmallocUsed SwapTotal SwapFree HugePages_Total HugePages_Free HugePages_Rsvd HugePages_Surp Hugepagesize Hugetlb", names, " ")
  for (i in names) wanted[names[i]] = 1
  print "["
  first = 1
}
wanted[$1] {
  split($2, fields, /[[:space:]]+/)
  value = fields[2]
  source_unit = fields[3]
  if (source_unit == "kB") {
    value *= 1024
    unit = "bytes"
    quantity = "data_volume"
  } else {
    unit = "count"
    quantity = "count"
  }
  if (!first) print ","
  first = 0
  printf "  {\"metric\":\"%s\",\"value_normalized\":%.0f,", escape_json($1), value
  printf "\"unit_normalized\":\"%s\",\"quantity_normalized\":\"%s\"}", unit, quantity
}
END { print "\n]" }
' "$meminfo_path"
