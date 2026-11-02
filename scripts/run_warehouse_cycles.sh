#!/usr/bin/env bash
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
set +u
source /opt/ros/humble/setup.bash
source "$HOME/apf_ws/install/local_setup.bash"
set -u
ros_cli=(/usr/bin/python3 /opt/ros/humble/bin/ros2)
existing_nodes=$("${ros_cli[@]}" node list --no-daemon 2>/dev/null)
if [[ $existing_nodes == *multimode_controller* || $existing_nodes == *slam_toolbox* || $existing_nodes == *warehouse_cycles* || $existing_nodes == *cycle_bridge* || $existing_nodes == *scan_relay_robot* || $existing_nodes == *ridgeback_bridge* || $existing_nodes == *bridge_robot* ]]; then
    echo 'Stop run_apf.sh/SLAM/old bridges first. This mode publishes map->odom from Isaac world pose.' >&2
    exit 1
fi
pids=()
cleanup() {
    trap - EXIT INT TERM
    for pid in "${pids[@]}"; do kill -TERM -- "-$pid" 2>/dev/null || true; done
    wait || true
}
trap cleanup EXIT
trap 'exit 130' INT TERM
start() { setsid "$@" & pids+=("$!"); }
for i in 1 2 3 4 5 6; do
    start /usr/bin/python3 "$project_dir/src/ridgeback_bridge.py" --ros-args -p ns:="robot$i" \
        -p use_sim_time:=true -r __node:="cycle_bridge_robot$i" \
        -p motion_gate:=true -p pose_topic:="/robot$i/warehouse_pose" \
        -p max_lin:="${WAREHOUSE_SPEED:-1.0}" -p max_ang:=0.7 \
        -p acc_lin:="${WAREHOUSE_ACCEL:-0.8}" -p acc_ang:=1.4 -p turn_in_place_angular:=0.35 \
        -p pose_timeout:=3.0 -p pose_sim_timeout:=0.7
    start /usr/bin/python3 "$project_dir/src/scan_relay.py" "robot$i" --apf-alignment
 done
start "${ros_cli[@]}" run multibot_controller multimode_controller_node --ros-args \
    -r __node:=multimode_controller --params-file "$HOME/apf_ws/src/multibot_controller/config/controllets.yaml" \
    -p use_sim_time:=true -p "robot_namespaces:=['robot1','robot2','robot3','robot4','robot5','robot6']"
factory_args=()
if [[ ${WAREHOUSE_FACTORY:-0} == 1 ]]; then factory_args+=(--require-factory); fi
start /usr/bin/python3 "$project_dir/src/warehouse_cycles.py" --dwell "${WAREHOUSE_DWELL:-3}" "${factory_args[@]}"
echo 'Cycles: robot1-3 storage/assembly; robot4-6 storage/packing; 1 moving robot per group.'
echo "AGV speed limit: ${WAREHOUSE_SPEED:-1.0} m/s (simulation); dwell: ${WAREHOUSE_DWELL:-3} s. Turns/obstacles may reduce speed."
wait -n "${pids[@]}"
echo 'A process exited; stopping cycle processes.' >&2
exit 1
