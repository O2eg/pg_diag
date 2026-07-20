#!/bin/sh
set -eu

hugepages_root=/sys/kernel/mm/hugepages
meminfo_path=/proc/meminfo

if [ ! -d "$hugepages_root" ]; then
  echo "$hugepages_root is unavailable" >&2
  exit 3
fi

default_page_size_kib=0
if [ -r "$meminfo_path" ]; then
  default_page_size_kib=$(
    awk '
      $1 == "Hugepagesize:" { print $2; found = 1; exit }
      END { if (!found) print 0 }
    ' "$meminfo_path"
  )
fi
case "$default_page_size_kib" in ''|*[!0-9]*) default_page_size_kib=0 ;; esac

page_sizes=
for pool_dir in "$hugepages_root"/hugepages-*kB; do
  [ -d "$pool_dir" ] || continue
  page_size_kib=${pool_dir##*/hugepages-}
  page_size_kib=${page_size_kib%kB}
  case "$page_size_kib" in ''|*[!0-9]*) continue ;; esac
  page_sizes="$page_sizes $page_size_kib"
done

if [ -z "$page_sizes" ]; then
  echo "no HugeTLB pools were found under $hugepages_root" >&2
  exit 3
fi

first=1
printf '[\n'
for page_size_kib in $(printf '%s\n' $page_sizes | sort -n); do
  pool_dir=$hugepages_root/hugepages-${page_size_kib}kB

  read_counter() {
    counter_file=$1
    if [ ! -r "$counter_file" ]; then
      printf '0\n'
      return
    fi
    counter_value=$(sed -n '1p' "$counter_file")
    case "$counter_value" in ''|*[!0-9]*) counter_value=0 ;; esac
    printf '%s\n' "$counter_value"
  }

  total_pages=$(read_counter "$pool_dir/nr_hugepages")
  free_pages=$(read_counter "$pool_dir/free_hugepages")
  reserved_pages=$(read_counter "$pool_dir/resv_hugepages")
  surplus_pages=$(read_counter "$pool_dir/surplus_hugepages")
  used_pages=$((total_pages - free_pages))
  [ "$used_pages" -ge 0 ] || used_pages=0
  free_unreserved_pages=$((free_pages - reserved_pages))
  [ "$free_unreserved_pages" -ge 0 ] || free_unreserved_pages=0
  page_size_bytes=$((page_size_kib * 1024))

  is_default_size=false
  if [ "$page_size_kib" -eq "$default_page_size_kib" ]; then
    is_default_size=true
  fi

  numa_distribution=
  numa_nodes_with_pages=0
  for node_dir in /sys/devices/system/node/node[0-9]*; do
    [ -d "$node_dir" ] || continue
    node_name=${node_dir##*/}
    node_pool=$node_dir/hugepages/hugepages-${page_size_kib}kB/nr_hugepages
    [ -r "$node_pool" ] || continue
    node_pages=$(read_counter "$node_pool")
    if [ -n "$numa_distribution" ]; then
      numa_distribution=$numa_distribution,
    fi
    numa_distribution=${numa_distribution}${node_name}=${node_pages}
    if [ "$node_pages" -gt 0 ]; then
      numa_nodes_with_pages=$((numa_nodes_with_pages + 1))
    fi
  done

  if [ "$first" -eq 0 ]; then
    printf ',\n'
  fi
  first=0
  printf '  {'
  printf '"page_size_bytes":%s,' "$page_size_bytes"
  printf '"is_default_size":%s,' "$is_default_size"
  printf '"total_pages":%s,' "$total_pages"
  printf '"used_pages":%s,' "$used_pages"
  printf '"free_pages":%s,' "$free_pages"
  printf '"reserved_pages":%s,' "$reserved_pages"
  printf '"free_unreserved_pages":%s,' "$free_unreserved_pages"
  printf '"surplus_pages":%s,' "$surplus_pages"
  printf '"pool_total_bytes":%s,' "$((total_pages * page_size_bytes))"
  printf '"pool_used_bytes":%s,' "$((used_pages * page_size_bytes))"
  printf '"pool_reserved_bytes":%s,' "$((reserved_pages * page_size_bytes))"
  printf '"pool_free_unreserved_bytes":%s,' "$((free_unreserved_pages * page_size_bytes))"
  printf '"numa_distribution":"%s",' "$numa_distribution"
  printf '"numa_nodes_with_pages":%s' "$numa_nodes_with_pages"
  printf '}'
done
printf '\n]\n'
