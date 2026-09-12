#!/bin/sh
# cgroup resource limits that bound PostgreSQL even though /proc describes the whole host.
# The limits are read for the cgroup of the PostgreSQL postmaster (a "postgres" process whose
# parent is not one), resolved through /proc/<pid>/cgroup and the cgroup mount, walking every
# ancestor group so nested limits (systemd slices, Kubernetes pods) are not missed. Without a
# visible postmaster the collector's own cgroup is measured and scope says so. One row per
# distinct postmaster cgroup; absent limits are null, never zero.
#
# usage: cgroup_limits.sh            # postmaster cgroups, or the collector's own
#        cgroup_limits.sh self       # the collector's own cgroup only
#        cgroup_limits.sh <pid>      # the cgroup of one process
set -eu

json_num() {
  case "$1" in
    ''|*[!0-9]*) printf 'null' ;;
    *) printf '%s' "$1" ;;
  esac
}

json_str() {
  printf '"%s"' "$(printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g')"
}

read_file() {
  if [ -r "$1" ]; then
    sed -n '1p' "$1" 2>/dev/null || true
  fi
}

# "max", empty and the v1 "no limit" sentinel (a number near 2^63) all mean unlimited
normalize_limit() {
  case "$1" in
    max|'') printf '' ;;
    *[!0-9]*) printf '' ;;
    *) if [ "${#1}" -ge 19 ]; then printf ''; else printf '%s' "$1"; fi ;;
  esac
}

# smaller of two numeric limits ("" = unlimited)
min_limit() {
  if [ -z "$1" ]; then printf '%s' "$2"
  elif [ -z "$2" ]; then printf '%s' "$1"
  elif [ "$1" -le "$2" ]; then printf '%s' "$1"
  else printf '%s' "$2"
  fi
}

# mount point of the cgroup2 hierarchy, or of one v1 controller
mount_point() {
  awk -v want="$1" '
    {
      sep = 0
      for (i = 7; i <= NF; i++) if ($i == "-") { sep = i; break }
      if (!sep) next
      fstype = $(sep + 1); opts = $(sep + 3)
      if (want == "cgroup2" && fstype == "cgroup2") { print $5; exit }
      if (want != "cgroup2" && fstype == "cgroup" && ("," opts ",") ~ ("," want ",")) { print $5; exit }
    }' /proc/self/mountinfo 2>/dev/null
}

# cgroup path of a process: v2 unified path, or the path of one v1 controller
cgroup_path_of() {
  pid=$1; controller=$2
  if [ "$controller" = "unified" ]; then
    sed -n 's/^0::\(.*\)$/\1/p' "/proc/$pid/cgroup" 2>/dev/null | head -n 1
  else
    awk -F: -v want="$controller" '("," $2 ",") ~ ("," want ",") { print $3; exit }' "/proc/$pid/cgroup" 2>/dev/null
  fi
}

# postmasters: postgres processes whose parent is not a postgres process (pid ppid per line)
postmasters() {
  awk '
    FNR == 1 {
      open = index($0, "(")
      close_pos = 0
      for (i = length($0); i > 0; i--) if (substr($0, i, 1) == ")") { close_pos = i; break }
      if (!open || !close_pos) next
      comm = substr($0, open + 1, close_pos - open - 1)
      split(substr($0, close_pos + 2), rest, " ")
      pid = substr($0, 1, open - 2)
      if (comm == "postgres" || comm == "postmaster") ppid[pid] = rest[2]
    }
    END { for (p in ppid) if (!(ppid[p] in ppid)) print p, ppid[p] }
  ' /proc/[0-9]*/stat 2>/dev/null
}

# --- host facts shared by every row
host_cpus=$(getconf _NPROCESSORS_ONLN 2>/dev/null || nproc 2>/dev/null || printf '')
host_mem_kib=$(awk '$1 == "MemTotal:" { print $2; exit }' /proc/meminfo 2>/dev/null || printf '')
host_mem_bytes=
[ -z "$host_mem_kib" ] || host_mem_bytes=$((host_mem_kib * 1024))

container_hint=none
if [ -f /.dockerenv ]; then
  container_hint=docker
elif [ -n "${container:-}" ]; then
  container_hint=$container
elif grep -qsE 'docker|containerd|kubepods|lxc' /proc/1/cgroup 2>/dev/null; then
  container_hint=cgroup-path
fi

cgroup_version=none
v2_root=
if [ -f /sys/fs/cgroup/cgroup.controllers ] || [ -n "$(mount_point cgroup2)" ]; then
  cgroup_version=v2
  v2_root=$(mount_point cgroup2)
  [ -n "$v2_root" ] || v2_root=/sys/fs/cgroup
elif [ -d /sys/fs/cgroup/cpu ] || [ -d /sys/fs/cgroup/memory ] || [ -n "$(mount_point memory)" ]; then
  cgroup_version=v1
fi

# --- one JSON row for the cgroup that contains $1
emit_row() {
  target_pid=$1; scope=$2; postmaster_count=$3; cgroup_count=$4
  cpu_quota_us=; cpu_period_us=; cpuset=; memory_limit=; memory_high=; memory_current=; swap_limit=; pids_max=
  cpu_source=; memory_source=; source_path=; cgroup_path=; path_resolved=true
  best_ratio=

  if [ "$cgroup_version" = v2 ]; then
    cgroup_path=$(cgroup_path_of "$target_pid" unified)
    dir="$v2_root${cgroup_path%/}"
    if [ ! -d "$dir" ]; then
      # the path is relative to another cgroup namespace: fall back to the visible root
      dir=$v2_root; path_resolved=false
    fi
    source_path=$dir
    cpuset=$(read_file "$dir/cpuset.cpus.effective")
    memory_current=$(normalize_limit "$(read_file "$dir/memory.current")")
    walk=$dir
    while :; do
      cpu_max=$(read_file "$walk/cpu.max")
      case "$cpu_max" in
        max*|'') ;;
        *)
          quota=${cpu_max% *}; period=${cpu_max#* }
          if [ "$period" -gt 0 ] 2>/dev/null; then
            ratio=$(awk -v q="$quota" -v p="$period" 'BEGIN { printf "%.6f", q / p }')
            if [ -z "$best_ratio" ] || awk -v a="$ratio" -v b="$best_ratio" 'BEGIN { exit !(a < b) }'; then
              best_ratio=$ratio; cpu_quota_us=$quota; cpu_period_us=$period; cpu_source=$walk
            fi
          fi
          ;;
      esac
      value=$(normalize_limit "$(read_file "$walk/memory.max")")
      if [ -n "$value" ] && [ "$(min_limit "$memory_limit" "$value")" = "$value" ] && [ "$value" != "$memory_limit" ]; then
        memory_limit=$value; memory_source=$walk
      fi
      memory_high=$(min_limit "$memory_high" "$(normalize_limit "$(read_file "$walk/memory.high")")")
      swap_limit=$(min_limit "$swap_limit" "$(normalize_limit "$(read_file "$walk/memory.swap.max")")")
      pids_max=$(min_limit "$pids_max" "$(normalize_limit "$(read_file "$walk/pids.max")")")
      [ "$walk" != "$v2_root" ] && [ "${walk#"$v2_root"}" != "$walk" ] || break
      walk=$(dirname "$walk")
    done
  elif [ "$cgroup_version" = v1 ]; then
    cpu_root=$(mount_point cpu); [ -n "$cpu_root" ] || cpu_root=/sys/fs/cgroup/cpu
    mem_root=$(mount_point memory); [ -n "$mem_root" ] || mem_root=/sys/fs/cgroup/memory
    set_root=$(mount_point cpuset); [ -n "$set_root" ] || set_root=/sys/fs/cgroup/cpuset
    pid_root=$(mount_point pids); [ -n "$pid_root" ] || pid_root=/sys/fs/cgroup/pids
    cgroup_path=$(cgroup_path_of "$target_pid" memory)
    [ -n "$cgroup_path" ] || cgroup_path=$(cgroup_path_of "$target_pid" cpu)
    mem_dir="$mem_root${cgroup_path%/}"
    if [ ! -d "$mem_dir" ]; then mem_dir=$mem_root; path_resolved=false; fi
    source_path=$mem_dir
    cpu_path=$(cgroup_path_of "$target_pid" cpu); cpu_dir="$cpu_root${cpu_path%/}"; [ -d "$cpu_dir" ] || cpu_dir=$cpu_root
    set_path=$(cgroup_path_of "$target_pid" cpuset); set_dir="$set_root${set_path%/}"; [ -d "$set_dir" ] || set_dir=$set_root
    pid_path=$(cgroup_path_of "$target_pid" pids); pid_dir="$pid_root${pid_path%/}"; [ -d "$pid_dir" ] || pid_dir=$pid_root
    cpuset=$(read_file "$set_dir/cpuset.effective_cpus")
    [ -n "$cpuset" ] || cpuset=$(read_file "$set_dir/cpuset.cpus")
    memory_current=$(normalize_limit "$(read_file "$mem_dir/memory.usage_in_bytes")")
    walk=$cpu_dir
    while :; do
      quota=$(read_file "$walk/cpu.cfs_quota_us"); period=$(read_file "$walk/cpu.cfs_period_us")
      case "$quota" in
        -1|'') ;;
        *)
          if [ "$period" -gt 0 ] 2>/dev/null; then
            ratio=$(awk -v q="$quota" -v p="$period" 'BEGIN { printf "%.6f", q / p }')
            if [ -z "$best_ratio" ] || awk -v a="$ratio" -v b="$best_ratio" 'BEGIN { exit !(a < b) }'; then
              best_ratio=$ratio; cpu_quota_us=$quota; cpu_period_us=$period; cpu_source=$walk
            fi
          fi
          ;;
      esac
      [ "$walk" != "$cpu_root" ] && [ "${walk#"$cpu_root"}" != "$walk" ] || break
      walk=$(dirname "$walk")
    done
    walk=$mem_dir
    while :; do
      value=$(normalize_limit "$(read_file "$walk/memory.limit_in_bytes")")
      if [ -n "$value" ] && [ "$(min_limit "$memory_limit" "$value")" = "$value" ] && [ "$value" != "$memory_limit" ]; then
        memory_limit=$value; memory_source=$walk
      fi
      swap_limit=$(min_limit "$swap_limit" "$(normalize_limit "$(read_file "$walk/memory.memsw.limit_in_bytes")")")
      [ "$walk" != "$mem_root" ] && [ "${walk#"$mem_root"}" != "$walk" ] || break
      walk=$(dirname "$walk")
    done
    walk=$pid_dir
    while :; do
      pids_max=$(min_limit "$pids_max" "$(normalize_limit "$(read_file "$walk/pids.max")")")
      [ "$walk" != "$pid_root" ] && [ "${walk#"$pid_root"}" != "$walk" ] || break
      walk=$(dirname "$walk")
    done
  fi

  cpu_limit_cores=null
  if [ -n "$cpu_quota_us" ] && [ -n "$cpu_period_us" ] && [ "$cpu_period_us" -gt 0 ] 2>/dev/null; then
    cpu_limit_cores=$(awk -v q="$cpu_quota_us" -v p="$cpu_period_us" 'BEGIN { printf "%.3f", q / p }')
  fi

  printf '{'
  printf '"scope":%s,' "$(json_str "$scope")"
  printf '"target_pid":%s,' "$(json_num "$target_pid")"
  printf '"postmaster_count":%s,' "$(json_num "$postmaster_count")"
  printf '"cgroup_count":%s,' "$(json_num "$cgroup_count")"
  printf '"cgroup_version":%s,' "$(json_str "$cgroup_version")"
  printf '"cgroup_path":%s,' "$(json_str "$cgroup_path")"
  printf '"path_resolved":%s,' "$path_resolved"
  printf '"container_hint":%s,' "$(json_str "$container_hint")"
  printf '"cpu_quota_us":%s,' "$(json_num "$cpu_quota_us")"
  printf '"cpu_period_us":%s,' "$(json_num "$cpu_period_us")"
  printf '"cpu_limit_cores":%s,' "$cpu_limit_cores"
  printf '"cpu_limit_source":%s,' "$(json_str "$cpu_source")"
  printf '"cpuset_cpus_effective":%s,' "$(json_str "$cpuset")"
  printf '"host_online_cpus":%s,' "$(json_num "$host_cpus")"
  printf '"memory_limit_bytes":%s,' "$(json_num "$memory_limit")"
  printf '"memory_limit_source":%s,' "$(json_str "$memory_source")"
  printf '"memory_high_bytes":%s,' "$(json_num "$memory_high")"
  printf '"memory_current_bytes":%s,' "$(json_num "$memory_current")"
  printf '"memory_swap_limit_bytes":%s,' "$(json_num "$swap_limit")"
  printf '"host_memory_total_bytes":%s,' "$(json_num "$host_mem_bytes")"
  printf '"pids_max":%s,' "$(json_num "$pids_max")"
  printf '"source_path":%s' "$(json_str "$source_path")"
  printf '}'
}

printf '['
mode=${1:-}
if [ "$mode" = self ]; then
  emit_row $$ collector 0 0
elif [ -n "$mode" ]; then
  emit_row "$mode" process 0 0
else
  # group postmasters by cgroup path; the group with most postmasters comes first
  groups=$(postmasters | while read -r pid ppid; do
    if [ "$cgroup_version" = v2 ]; then path=$(cgroup_path_of "$pid" unified); else path=$(cgroup_path_of "$pid" memory); fi
    printf '%s\t%s\n' "${path:-/}" "$pid"
  done | sort | awk -F'\t' '{ if (!($1 in first)) first[$1] = $2; n[$1]++ } END { for (p in n) printf "%d\t%s\t%s\n", n[p], first[p], p }' | sort -t"$(printf '\t')" -k1,1nr -k2,2n)
  if [ -z "$groups" ]; then
    emit_row $$ collector 0 0
  else
    total=$(printf '%s\n' "$groups" | wc -l | tr -d ' ')
    first=1
    printf '%s\n' "$groups" | while IFS="$(printf '\t')" read -r count pid path; do
      [ "$first" = 1 ] || printf ','
      first=0
      emit_row "$pid" postmaster "$count" "$total"
    done
  fi
fi
printf ']\n'
