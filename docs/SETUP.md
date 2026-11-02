# Setup and reproducibility

## Dashboard demo (no GPU or ROS required)

Use Ubuntu with system Python 3.10 or newer. No pip or npm installation is needed for the dashboard; Three.js and its MIT license are vendored.

```bash
git clone <your-repository-url> warehouse_twin
cd warehouse_twin
bash scripts/run_web.sh --demo
```

Open http://127.0.0.1:8080. Demo data is temporary and separate from operational inventory.

## Full simulation

The development environment uses Ubuntu, Isaac Sim 6.1, ROS 2 Humble, NVIDIA RTX hardware and a separately built APF workspace at `~/apf_ws`. The external APF controller is not included in this repository; full AGV navigation requires the `multibot_controller` package, its `set_goal` service and configuration documented in the source scripts. There is no public download URL recorded for that workspace.

The default Isaac location is `~/isaacsim/isaac-sim-standalone-6.1.0-linux-x86_64`; override it with `ISAAC_DIR`. ROS is sourced from `/opt/ros/humble/setup.bash`.

1. Read the asset sources in `config/warehouse_assets_requested.json` and their upstream license terms.
2. Download NVIDIA assets using `bash scripts/build_warehouse_map.sh --download`.
3. Download the pinned Hugging Face assets using the commands in [WAREHOUSE_MODELS.md](WAREHOUSE_MODELS.md). Some assets need a separate download and are not supplied by the NVIDIA downloader.
4. Generate the environment and ROS graphs:

   ```bash
   bash scripts/build_warehouse_map.sh
   bash scripts/build_warehouse_map.sh --verify
   bash scripts/build_ros2_graph.sh
   ```

5. Run the factory, wait for `Ready`, then press Play:

   ```bash
   bash scripts/run_factory_live.sh
   ```

6. In separate terminals, start navigation and the dashboard:

   ```bash
   WAREHOUSE_FACTORY=1 bash scripts/run_warehouse_cycles.sh
   bash scripts/run_web.sh
   ```

Scripts contain assumptions about the original workstation. Follow [local operations](LOCAL_OPERATIONS.md) for those paths; do not expect a fresh clone to contain assets, Isaac, ROS or APF. Generated USD files from another machine should be rebuilt rather than copied. Keep the historical `~/warehouse_assets` symlink if existing downloaded layers still depend on it.

## Performance

The launcher defaults to `--quality fast` (RaytracedLighting, 960 × 540). Use `--quality quality` for Isaac's default realtime path tracing. Renderer changes require a restart. Simulation speed depends on RTF as well as AGV velocity; the current scene has six RTX lidars. A measured development session had RTF around 0.23; performance is not guaranteed on other machines.

## Checks

```bash
PYTHONPATH=src python3 tests/test_factory_cycle.py
PYTHONPATH=src python3 tests/test_web.py
bash scripts/test_project.sh --unit  # requires ROS and APF workspace
```

GPU/ROS/GUI checks are separate from lightweight CI; see [factory](FACTORY_LIVE.md) and [dashboard](WEB_DASHBOARD.md) documentation.
