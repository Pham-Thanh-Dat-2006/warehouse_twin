# Generated warehouse stages

USD stages are generated locally and excluded from Git because they reference downloaded assets and machine-specific paths.

```bash
bash scripts/build_warehouse_map.sh --download
bash scripts/build_warehouse_map.sh
bash scripts/build_ros2_graph.sh
```

The factory launcher creates its runtime wrapper automatically. See [setup](../docs/SETUP.md) for prerequisites.
