#!/bin/sh
set -eu

clock_ticks="$(getconf CLK_TCK)"
IFS=' ' read -r uptime _ < /proc/uptime
printf '%s\0%s\0' "$clock_ticks" "$uptime"
for proc_dir in /proc/[0-9]*; do
  [ -r "$proc_dir/comm" ] || continue
  IFS= read -r comm < "$proc_dir/comm" || continue
  case "$comm" in
    postgres|postmaster|postgres:*) ;;
    *) continue ;;
  esac
  cmdline="$(tr '\000' ' ' < "$proc_dir/cmdline" 2>/dev/null)" || cmdline=""
  IFS= read -r stat_line < "$proc_dir/stat" || continue
  stat_fields="${stat_line##*) }"
  set -- $stat_fields
  [ "$#" -ge 20 ] || continue
  state="$1"
  utime="${12}"
  stime="${13}"
  starttime="${20}"
  read_bytes=0
  write_bytes=0
  cancelled_write_bytes=0
  syscr=0
  syscw=0
  io_access=0
  if [ -r "$proc_dir/io" ]; then
    while IFS=': ' read -r key value rest; do
      case "$key" in
        read_bytes) read_bytes="$value" ;;
        write_bytes) write_bytes="$value" ;;
        cancelled_write_bytes) cancelled_write_bytes="$value" ;;
        syscr) syscr="$value" ;;
        syscw) syscw="$value" ;;
      esac
    done < "$proc_dir/io"
    io_access=1
  fi
  rss_kb=0
  if [ -r "$proc_dir/status" ]; then
    while IFS= read -r status_line; do
      case "$status_line" in
        VmRSS:*) set -- $status_line; rss_kb="${2:-0}"; break ;;
      esac
    done < "$proc_dir/status"
  fi
  pid="${proc_dir##*/}"
  printf '%s\0%s\0%s\0%s\0%s\0%s\0%s\0%s\0%s\0%s\0%s\0%s\0%s\0%s\0' \
    "$pid" "$comm" "$cmdline" "$state" "$starttime" "$utime" "$stime" \
    "$read_bytes" "$write_bytes" "$cancelled_write_bytes" "$syscr" "$syscw" \
    "$io_access" "$rss_kb"
done
