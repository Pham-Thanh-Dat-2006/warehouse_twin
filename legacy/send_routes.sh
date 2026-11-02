#!/bin/bash
project_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
source /opt/ros/humble/setup.bash
source ~/apf_ws/install/local_setup.bash
S=/multimode_controller/set_route
T=multibot_interfaces/srv/SetRoute
route() { ros2 service call $S $T "{robot_namespace: '$1', xs: [$2, $3], ys: [$4, $4]}"; }
route robot1 10.0 108.0 33.0
route robot2 10.0 108.0 38.2
route robot3 10.0 108.0 43.4
route robot4 110.0 12.0 35.6
route robot5 110.0 12.0 40.8
route robot6 110.0 12.0 46.0
