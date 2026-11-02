#!/usr/bin/env bash
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
if [[ ! -f "$project_dir/config/factory_motion_plan.json" ]]; then
    echo 'Missing config/factory_motion_plan.json; prepare the Comau motion plan first.' >&2
    exit 1
fi
# Compose lightweight instance opinions with CPU OpenUSD before RTX loads the
# warehouse. A separate wrapper leaves both saved warehouse maps untouched.
render_stage="$project_dir/maps/warehouse_factory_runtime.usda"
stage_args=()
app_args=()
while (( $# )); do
    case "$1" in
        --stage)
            if (( $# < 2 )); then echo 'Missing path after --stage' >&2; exit 2; fi
            stage_args=(--stage "$2"); shift 2 ;;
        --stage=*) stage_args=(--stage "${1#--stage=}"); shift ;;
        *) app_args+=("$1"); shift ;;
    esac
done
(
    warehouse_usd_env
    "$isaac_dir/python.sh" "$project_dir/src/factory_render.py" "${stage_args[@]}" --output "$render_stage"
)
cd "$isaac_dir"
exec ./python.sh "$project_dir/src/factory_app.py" --stage "$render_stage" "${app_args[@]}"
