#!/usr/bin/env bash
# Shared paths for launchers; this file is sourced, not a separate launch command.
project_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
isaac_dir=${ISAAC_DIR:-$HOME/isaacsim/isaac-sim-standalone-6.1.0-linux-x86_64}
export PYTHONPATH="$project_dir/src${PYTHONPATH:+:$PYTHONPATH}"
warehouse_usd_env() {
    local candidates=("$isaac_dir"/extscache/omni.usd.libs-*)
    usd_dir=${candidates[0]}
    if [[ ! -d "$usd_dir/pxr" ]]; then
        echo "Cannot find OpenUSD in $isaac_dir/extscache" >&2
        return 1
    fi
    export LD_LIBRARY_PATH="$usd_dir/bin${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
    export PYTHONPATH="$usd_dir:$project_dir/src${PYTHONPATH:+:$PYTHONPATH}"
}
