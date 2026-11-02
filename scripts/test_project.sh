#!/usr/bin/env bash
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
case ${1:---unit} in
    --render)
        warehouse_usd_env
        "$isaac_dir/python.sh" "$project_dir/src/factory_render.py"
        "$isaac_dir/python.sh" "$project_dir/tests/test_factory_render.py"
        WAREHOUSE_TEST_STAGE="$project_dir/maps/warehouse_factory_runtime.usda" \
            "$isaac_dir/python.sh" "$project_dir/tests/test_factory_scene.py"
        ;;
    --render-gpu)
        (
            warehouse_usd_env
            "$isaac_dir/python.sh" "$project_dir/src/factory_render.py"
        )
        cd "$isaac_dir"
        export ROS_DOMAIN_ID=171 ROS_LOCALHOST_ONLY=1
        exec ./python.sh "$project_dir/tests/test_factory_render_gpu.py"
        ;;
    --web)
        exec /usr/bin/python3 "$project_dir/tests/test_web.py"
        ;;
    --web-ros)
        set +u
        source /opt/ros/humble/setup.bash
        set -u
        export ROS_DOMAIN_ID=${WAREHOUSE_TEST_DOMAIN:-171}
        export ROS_LOCALHOST_ONLY=1
        exec /usr/bin/python3 "$project_dir/tests/test_web_ros.py"
        ;;
    --unit)
        set +u
        source /opt/ros/humble/setup.bash
        source "$HOME/apf_ws/install/local_setup.bash"
        set -u
        /usr/bin/python3 "$project_dir/tests/test_factory_cycle.py"
        /usr/bin/python3 "$project_dir/tests/test_warehouse_cycle_dispatch.py"
        ;;
    --usd)
        warehouse_usd_env
        for test in test_factory_startup.py test_factory_scene.py verify_warehouse_map.py verify_warehouse_cycles.py; do
            "$isaac_dir/python.sh" "$project_dir/tests/$test"
        done
        ;;
    --ros)
        warehouse_usd_env
        sdk_ros="$isaac_dir/exts/isaacsim.ros2.core/humble"
        export PYTHONPATH="$usd_dir:$sdk_ros/rclpy:$project_dir/src"
        export LD_LIBRARY_PATH="$usd_dir/bin:$sdk_ros/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
        export ROS_DOMAIN_ID=${WAREHOUSE_TEST_DOMAIN:-171}
        export ROS_LOCALHOST_ONLY=1
        exec "$isaac_dir/python.sh" "$project_dir/tests/test_factory_scene.py" --ros
        ;;
    --physics)
        cd "$isaac_dir"
        exec ./python.sh "$project_dir/tests/test_factory_physics_clock.py"
        ;;
    *) echo 'Usage: bash scripts/test_project.sh [--unit|--usd|--ros|--physics|--web|--web-ros|--render|--render-gpu]' >&2; exit 2 ;;
esac
