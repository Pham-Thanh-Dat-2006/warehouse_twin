#!/usr/bin/env bash
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
if [[ " $* " != *' --demo '* ]]; then
    set +u
    source /opt/ros/humble/setup.bash
    set -u
fi
exec /usr/bin/python3 "$project_dir/web/server.py" "$@"
