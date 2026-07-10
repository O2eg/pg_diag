#!/bin/sh
set -eu

meminfo_path=/proc/meminfo
if [ ! -r "$meminfo_path" ]; then
  echo "/proc/meminfo is unavailable" >&2
  exit 3
fi

awk -F: '
BEGIN {
  split("MemTotal MemFree MemAvailable Buffers Cached SwapCached Active Inactive Active(anon) Inactive(anon) Active(file) Inactive(file) Unevictable Dirty Writeback AnonPages Mapped Shmem KReclaimable Slab SReclaimable SUnreclaim KernelStack PageTables CommitLimit Committed_AS VmallocUsed SwapTotal SwapFree HugePages_Total HugePages_Free HugePages_Rsvd HugePages_Surp Hugepagesize Hugetlb", names, " ")
  for (i in names) wanted[names[i]] = 1
}
wanted[$1] { print }
' "$meminfo_path"
