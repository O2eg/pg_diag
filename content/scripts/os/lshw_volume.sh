#!/bin/sh
set -eu

lshw_output="$("$(dirname "$0")/lshw_json.sh" volume 2>/dev/null || true)"

if command -v python3 >/dev/null 2>&1; then
  if printf '%s' "$lshw_output" | python3 -c '
import json
import sys

try:
    value = json.load(sys.stdin)
except Exception:
    sys.exit(1)
if isinstance(value, list) and value:
    sys.exit(0)
if isinstance(value, dict) and value:
    sys.exit(0)
sys.exit(1)
' >/dev/null 2>&1; then
    printf '%s\n' "$lshw_output"
    exit 0
  fi
else
  printf '%s\n' "$lshw_output"
  exit 0
fi

if ! command -v lsblk >/dev/null 2>&1; then
  echo "[]"
  exit 0
fi

columns="NAME,PATH,PKNAME,TYPE,SIZE,FSTYPE,LABEL,UUID,FSAVAIL,FSUSE%,MOUNTPOINTS,MODEL,SERIAL"
lsblk_output="$(lsblk --json --bytes -o "$columns" 2>/dev/null || true)"
if [ -z "$lsblk_output" ]; then
  columns="NAME,PATH,TYPE,SIZE,FSTYPE,MOUNTPOINT"
  lsblk_output="$(lsblk --json --bytes -o "$columns" 2>/dev/null || printf '{"blockdevices":[]}')"
fi

printf '%s' "$lsblk_output" | python3 -c '
import json
import sys

try:
    payload = json.load(sys.stdin)
except Exception:
    print("[]")
    raise SystemExit(0)

rows = []

def mountpoints_for(node):
    value = node.get("mountpoints", node.get("mountpoint"))
    if value is None:
        return ""
    if isinstance(value, list):
        return ", ".join(str(item) for item in value if item)
    return str(value)

def visit(node, parent_name="", parent_model="", parent_serial=""):
    node_type = node.get("type") or ""
    model = node.get("model") or parent_model
    serial = node.get("serial") or parent_serial
    mountpoints = mountpoints_for(node)
    fstype = node.get("fstype") or ""

    include = node_type != "loop" and (
        node_type != "disk" or bool(fstype) or bool(mountpoints)
    )
    if include:
        rows.append(
            {
                "name": node.get("name"),
                "path": node.get("path"),
                "parent": node.get("pkname") or parent_name or None,
                "type": node_type or None,
                "size_bytes": node.get("size"),
                "fstype": fstype or None,
                "label": node.get("label"),
                "uuid": node.get("uuid"),
                "fs_avail_bytes": node.get("fsavail"),
                "fs_use_pct": node.get("fsuse%"),
                "mountpoints": mountpoints or None,
                "model": model or None,
                "serial": serial or None,
            }
        )

    for child in node.get("children") or []:
        visit(child, node.get("name") or parent_name, model, serial)

for device in payload.get("blockdevices") or []:
    visit(device)

print(json.dumps(rows, ensure_ascii=False))
'
