#!/usr/bin/env bash
# Opens Isaac headless and writes maps/warehouse_ros2_ridgeback.usd (GPU required).
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
cd "$isaac_dir"
exec ./python.sh "$project_dir/src/add_ros2_ridgeback.py" "$@"
