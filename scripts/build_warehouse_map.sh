#!/usr/bin/env bash
# CPU authoring: preserves NVIDIA models/materials, no GPU/SimulationApp required.
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
warehouse_usd_env
if [[ ${1:-} == --download ]]; then
    shift
    exec "$isaac_dir/python.sh" "$project_dir/src/prepare_warehouse_assets.py" "$@"
fi
if [[ ${1:-} == --verify ]]; then
    shift
    exec "$isaac_dir/python.sh" "$project_dir/tests/verify_warehouse_map.py" "$@"
fi
export USD_ONLY=1
export ENV_ONLY=${ENV_ONLY:-0}
export ROBOTS=${ROBOTS:-6}
export OUTPUT=${OUTPUT:-$project_dir/maps/warehouse_environment_models.usd}
"$isaac_dir/python.sh" "$project_dir/src/warehouse.py"
if [[ ${LITE:-0} != 1 && ${ASSET_MODE:-models} == models ]]; then
    exec "$isaac_dir/python.sh" "$project_dir/tools/export_web_geometry.py" --stage "$OUTPUT"
fi
