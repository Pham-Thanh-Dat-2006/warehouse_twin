#!/bin/bash
project_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
N=${1:-1}
X0=(10 10 10 110 110 110)
Y0=(33.0 38.2 43.4 35.6 40.8 46.0)
Y0=(33.0 38.2 43.4 35.6 40.8 46.0)
source /opt/ros/humble/setup.bash
source ~/apf_ws/install/local_setup.bash
LIST=""
for i in $(seq 1 $N); do
  ns=robot$i; LIST="$LIST'$ns',"
  /usr/bin/python3 "$project_dir/src/ridgeback_bridge.py" --ros-args -p ns:=$ns -r __node:=bridge_$ns &
  /usr/bin/python3 "$project_dir/src/scan_relay.py" $ns &
  ros2 run tf2_ros static_transform_publisher --x ${X0[$((i-1))]} --y ${Y0[$((i-1))]} --z 0 --yaw 0 --pitch 0 --roll 0 --frame-id $ns/map --child-frame-id $ns/slam_map &
  ros2 run slam_toolbox async_slam_toolbox_node --ros-args -r __ns:=/$ns -r __node:=slam_toolbox -p use_sim_time:=true -p odom_frame:=$ns/odom -p map_frame:=$ns/slam_map -p base_frame:=$ns/base_link -p scan_topic:=/$ns/scan_fixed -p resolution:=0.05 -p max_laser_range:=12.0 -r /map:=/$ns/map -r /map_metadata:=/$ns/map_metadata &
done
ros2 run multibot_controller multimode_controller_node --ros-args -r __node:=multimode_controller --params-file ~/apf_ws/src/multibot_controller/config/controllets.yaml -p use_sim_time:=true -p robot_namespaces:="[${LIST%,}]" &
trap 'kill $(jobs -p) 2>/dev/null' EXIT
wait
