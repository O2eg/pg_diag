#!/bin/sh
set -eu

printf '%s\n' __PG_DIAG_STAT__
head -n 1 /proc/stat
printf '%s\n' __PG_DIAG_LOAD__
cat /proc/loadavg
printf '%s\n' __PG_DIAG_MEM__
cat /proc/meminfo
printf '%s\n' __PG_DIAG_NET__
cat /proc/net/dev
