"""Canonical project directories, independent of the caller's working directory."""
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = PROJECT_ROOT / 'config'
MAPS_DIR = PROJECT_ROOT / 'maps'
ASSETS_DIR = PROJECT_ROOT / 'assets'
ASSET_MANIFEST = ASSETS_DIR / 'nvidia_cache/warehouse_assets.json'
ENVIRONMENT_USD = MAPS_DIR / 'warehouse_environment_models.usd'
ROS2_USD = MAPS_DIR / 'warehouse_ros2_ridgeback.usd'
