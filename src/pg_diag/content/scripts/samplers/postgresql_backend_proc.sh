#!/bin/sh
set -eu
set -f

mode="${1:-discover}"
max_processes="${2:-2000}"
selected_pids="${3:-}"
discovered_hint="${4:-0}"

case "$mode" in
  discover|selected) ;;
  *)
    printf 'invalid backend process sampler mode: %s\n' "$mode" >&2
    exit 2
    ;;
esac
case "$max_processes" in
  ''|*[!0-9]*|0)
    printf 'invalid maximum backend process count: %s\n' "$max_processes" >&2
    exit 2
    ;;
esac
case "$discovered_hint" in
  ''|*[!0-9]*)
    printf 'invalid discovered backend process count: %s\n' "$discovered_hint" >&2
    exit 2
    ;;
esac
command -v ps >/dev/null 2>&1 || {
  printf 'ps executable not found\n' >&2
  exit 3
}
command -v awk >/dev/null 2>&1 || {
  printf 'awk executable not found\n' >&2
  exit 3
}
command -v sed >/dev/null 2>&1 || {
  printf 'sed executable not found\n' >&2
  exit 3
}
command -v mktemp >/dev/null 2>&1 || {
  printf 'mktemp executable not found\n' >&2
  exit 3
}
command -v rm >/dev/null 2>&1 || {
  printf 'rm executable not found\n' >&2
  exit 3
}

ps_status_file=""
ps_stderr=""

cleanup_ps_files() {
  [ -z "$ps_status_file" ] || rm -f "$ps_status_file"
  [ -z "$ps_stderr" ] || rm -f "$ps_stderr"
}

prepare_ps_files() {
  ps_status_file="$(
    mktemp "${TMPDIR:-/tmp}/pg_diag_backend_proc.status.XXXXXX"
  )" || {
    printf 'cannot create temporary file for backend process status\n' >&2
    exit 3
  }
  ps_stderr="$(
    mktemp "${TMPDIR:-/tmp}/pg_diag_backend_proc.stderr.XXXXXX"
  )" || {
    rm -f "$ps_status_file"
    ps_status_file=""
    printf 'cannot create temporary file for backend process diagnostics\n' >&2
    exit 3
  }
}

report_ps_failure() {
  phase="$1"
  status="$2"
  printf 'ps backend %s failed with exit code %s\n' "$phase" "$status" >&2
  if [ -s "$ps_stderr" ]; then
    sed -n '1p' "$ps_stderr" >&2
  fi
  exit 4
}

trap cleanup_ps_files 0
trap 'cleanup_ps_files; exit 143' HUP INT TERM

# Discovery is done by one procps invocation rather than by launching commands
# for every /proc PID. Running and uninterruptible processes are selected first;
# the remaining capacity is filled by ps CPU ordering at discovery time.
if [ "$mode" = "discover" ]; then
  prepare_ps_files
  inventory="$(
    {
      command_status=0
      ps -eo pid=,stat=,pcpu=,comm=,args= --sort=-pcpu \
        2> "$ps_stderr" || command_status=$?
      printf '%s\n' "$command_status" > "$ps_status_file"
    } |
      awk -v limit="$max_processes" '
        function row(pid, comm, command, field_number) {
          command = $5
          for (field_number = 6; field_number <= NF; field_number++) {
            command = command " " $field_number
          }
          if (command == "") {
            command = comm
          }
          gsub(/[[:cntrl:]]/, " ", command)
          return pid "\t" comm "\t" substr(command, 1, 220)
        }
        $4 == "postgres" || $4 == "postmaster" || $4 ~ /^postgres:/ {
          discovered++
          value = row($1, $4)
          if ($2 ~ /^[RD]/) {
            if (priority_count < limit) {
              priority[++priority_count] = value
            }
          } else if (regular_count < limit) {
            regular[++regular_count] = value
          }
        }
        END {
          selected = discovered < limit ? discovered : limit
          printf "%d\t%d\n", discovered, selected
          emitted = 0
          for (row_number = 1; row_number <= priority_count && emitted < limit; row_number++) {
            print priority[row_number]
            emitted++
          }
          for (row_number = 1; row_number <= regular_count && emitted < limit; row_number++) {
            print regular[row_number]
            emitted++
          }
        }
      '
  )" || {
    printf 'awk backend discovery failed\n' >&2
    exit 4
  }
  IFS= read -r ps_status < "$ps_status_file"
  if [ "$ps_status" -ne 0 ]; then
    report_ps_failure "discovery" "$ps_status"
  fi
  meta_line="$(printf '%s\n' "$inventory" | sed -n '1p')"
  selected_rows="$(printf '%s\n' "$inventory" | sed '1d')"
  IFS='	' read -r discovered_count selected_count <<EOF
$meta_line
EOF
else
  case "$selected_pids" in
    *[!0-9,]*|,*|*,|*,,*)
      printf 'invalid selected backend PID list\n' >&2
      exit 2
      ;;
  esac
  discovered_count="$discovered_hint"
  selected_count=0
  selected_rows=""
  if [ -n "$selected_pids" ]; then
    old_ifs="$IFS"
    IFS=','
    set -- $selected_pids
    IFS="$old_ifs"
    selected_count="$#"
    if [ "$selected_count" -gt "$max_processes" ]; then
      printf 'selected backend PID count exceeds maximum: %s > %s\n' \
        "$selected_count" "$max_processes" >&2
      exit 2
    fi
    prepare_ps_files
    selected_rows="$(
      {
        command_status=0
        ps -p "$selected_pids" -o pid=,stat=,pcpu=,comm=,args= \
          2> "$ps_stderr" || command_status=$?
        printf '%s\n' "$command_status" > "$ps_status_file"
      } |
        awk '
          function row(pid, comm, command, field_number) {
            command = $5
            for (field_number = 6; field_number <= NF; field_number++) {
              command = command " " $field_number
            }
            if (command == "") {
              command = comm
            }
            gsub(/[[:cntrl:]]/, " ", command)
            return pid "\t" comm "\t" substr(command, 1, 220)
          }
          $4 == "postgres" || $4 == "postmaster" || $4 ~ /^postgres:/ {
            print row($1, $4)
          }
        '
    )" || {
      printf 'awk backend selection failed\n' >&2
      exit 4
    }
    IFS= read -r ps_status < "$ps_status_file"
    if [ "$ps_status" -ne 0 ] && {
      [ "$ps_status" -ne 1 ] || [ -s "$ps_stderr" ]
    }; then
      report_ps_failure "selection" "$ps_status"
    fi
  fi
fi

clock_ticks="$(getconf CLK_TCK)"
page_size="$(getconf PAGESIZE)"
IFS=' ' read -r uptime _ < /proc/uptime
printf '%s\0%s\0%s\0%s\0' \
  "$clock_ticks" "$uptime" "$discovered_count" "$selected_count"

while IFS='	' read -r pid comm cmdline; do
  [ -n "$pid" ] || continue
  proc_dir="/proc/$pid"
  IFS= read -r stat_line < "$proc_dir/stat" || continue
  stat_fields="${stat_line##*) }"
  set -- $stat_fields
  [ "$#" -ge 22 ] || continue
  state="$1"
  utime="${12}"
  stime="${13}"
  starttime="${20}"
  rss_pages="${22}"
  read_bytes=0
  write_bytes=0
  cancelled_write_bytes=0
  syscr=0
  syscw=0
  io_access=0
  if
    while IFS=': ' read -r key value rest; do
      case "$key" in
        read_bytes) read_bytes="$value" ;;
        write_bytes) write_bytes="$value" ;;
        cancelled_write_bytes) cancelled_write_bytes="$value" ;;
        syscr) syscr="$value" ;;
        syscw) syscw="$value" ;;
      esac
    done < "$proc_dir/io" 2>/dev/null
  then
    io_access=1
  fi
  rss_kb=$((rss_pages * page_size / 1024))
  printf '%s\0%s\0%s\0%s\0%s\0%s\0%s\0%s\0%s\0%s\0%s\0%s\0%s\0%s\0' \
    "$pid" "$comm" "$cmdline" "$state" "$starttime" "$utime" "$stime" \
    "$read_bytes" "$write_bytes" "$cancelled_write_bytes" "$syscr" "$syscw" \
    "$io_access" "$rss_kb"
done <<EOF
$selected_rows
EOF
