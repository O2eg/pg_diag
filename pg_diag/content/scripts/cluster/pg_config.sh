#!/bin/sh
set -eu

pg_config_bin="$(command -v pg_config 2>/dev/null || true)"
if [ -z "$pg_config_bin" ]; then
  echo "pg_config is not available in PATH" >&2
  exit 127
fi

pg_config_output="$(LC_ALL=C "$pg_config_bin")" || {
  status=$?
  echo "pg_config failed with exit code $status" >&2
  exit "$status"
}

{
  printf 'PG_CONFIG = %s\n' "$pg_config_bin"
  printf '%s\n' "$pg_config_output"
} | awk '
  function json_escape(value) {
    gsub(/\\/, "\\\\", value)
    gsub(/"/, "\\\"", value)
    gsub(/\r/, "\\r", value)
    gsub(/\t/, "\\t", value)
    return value
  }

  BEGIN {
    print "["
    first = 1
  }

  {
    separator = index($0, " = ")
    if (!separator) {
      next
    }
    parameter = substr($0, 1, separator - 1)
    value = substr($0, separator + 3)
    if (!first) {
      print ","
    }
    printf "  {\"parameter\":\"%s\",\"value\":\"%s\"}", json_escape(parameter), json_escape(value)
    first = 0
  }

  END {
    print ""
    print "]"
  }
'
