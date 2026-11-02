# Warehouse Digital Twin — Isaac Sim 6.1 + ROS 2 Humble

Mở thư mục **`~/warehouse_twin`** trong VS Code. Đây là nơi chứa mã nguồn,
model đã tải, cấu hình, USD và tài liệu của dự án.

## Chạy nhà máy

Dừng các terminal chu trình cũ và đóng Isaac cũ trước khi mở phiên mới.

Terminal 1:

```bash
bash ~/warehouse_twin/scripts/run_factory_live.sh
```

Đợi `[FACTORY] Ready`, thấy kho rồi bấm **Play**. Băng chuyền và 8 tay N220 chạy
xem trước. Terminal 2 nối 6 AGV vào chu trình:

```bash
WAREHOUSE_FACTORY=1 bash ~/warehouse_twin/scripts/run_warehouse_cycles.sh
```

Hai nhóm chạy đồng thời, mỗi nhóm lần lượt một xe. Robot1–3: kho trữ ↔ lắp ráp;
robot4–6: kho trữ ↔ đóng gói. UR5 trên AGV giữ nguyên tư thế. APF không sửa.
Xem log `sim`, `physics_steps`, `arm_cycles`, `belt_outputs` để theo dõi tiến độ.
Dây chuyền và gắp/đặt là mô phỏng theo kịch bản; chưa nối PLC hoặc gắp bằng tiếp xúc.

Chỉ xem dây chuyền, không nối điều phối AGV:

```bash
bash ~/warehouse_twin/scripts/run_factory_live.sh --no-ros
```

Mở USD trực tiếp sẽ chỉ mở cảnh; dùng launcher để nạp chuyển động nhà máy.

## Web giám sát kho 3D

Sau khi chạy Isaac và chu trình, mở terminal thứ ba:

```bash
bash ~/warehouse_twin/scripts/run_web.sh
```

Vào **http://127.0.0.1:8080**: kho 3D xoay/zoom, bản đồ 2D/tuyến/nhiệt, AGV trực tiếp, SKU và tồn kho, đơn vận
chuyển theo từng kiện, dây chuyền/tay máy, nhật ký và cảnh báo. Web chỉ giám sát
ROS và quản lý dữ liệu hàng; không gửi lệnh điều khiển xe.

Xem giao diện trước, không cần Isaac: `bash scripts/run_web.sh --demo`.
Demo có nhãn riêng và không ghi vào database vận hành. Xem
[hướng dẫn web](WEB_DASHBOARD.md) để nhập hàng, tạo đơn và hiểu cách ghi sổ.
Danh sách chức năng hiện có: [WEB_FEATURES.md](WEB_FEATURES.md).

## Thư mục

| Thư mục | Nội dung |
|---|---|
| `scripts/` | Lệnh chạy, build và kiểm thử; `common.sh` dùng chung đường dẫn |
| `web/` | Backend HTTP/SSE/SQLite, bộ thu ROS và giao diện KhoTwin 3D |
| `src/` | Sinh kho, graph ROS2, bridge/relay, điều phối AGV và runtime nhà máy |
| `config/` | Nguồn model và tư thế gắp/đặt N220 |
| `maps/` | Hai USD đang dùng: environment và bản có graph ROS2 |
| `assets/` | Toàn bộ model đã tải và cache NVIDIA/Hugging Face |
| `tools/` | Kiểm tra odom/TF và lidar |
| `tests/` | Kiểm thử dòng hàng, điều phối, clock, USD và tuyến |
| `docs/` | Hướng dẫn chi tiết, sơ đồ và nhật ký sắp xếp file |
| `legacy/` | Hai script SLAM/đi ngang cũ để tham khảo, không chạy cùng chu trình mới |
| `apf_ws` | Liên kết đến `~/apf_ws`; workspace APF giữ vị trí build cũ |

Hai bản đồ cần giữ:

- `maps/warehouse_environment_models.usd`: môi trường + 6 Ridgeback, đầu vào build graph.
- `maps/warehouse_ros2_ridgeback.usd`: bản chạy ROS2 và nhà máy hiện tại.

Model đã được chuyển vào `assets/`. **Giữ liên kết `~/warehouse_assets`**: một số
USD/MDL đã tải còn tham chiếu đường dẫn này. Liên kết không tạo thêm bản sao model.
Bộ cài Isaac ở `~/isaacsim/isaac-sim-standalone-6.1.0-linux-x86_64` và workspace
APF ở `~/apf_ws` là môi trường bên ngoài, không đổi vị trí.

## Sinh lại bản đồ khi thay bố cục

Không cần build lại chỉ vì vừa sắp xếp thư mục.

```bash
bash ~/warehouse_twin/scripts/build_warehouse_map.sh
bash ~/warehouse_twin/scripts/build_warehouse_map.sh --verify
bash ~/warehouse_twin/scripts/build_ros2_graph.sh
```

Bước tạo graph mở Isaac headless, cần GPU; kết quả ghi vào `maps/`.
Tải asset khi bổ sung model: `bash scripts/build_warehouse_map.sh --download`.
Đường dẫn chung được khai báo tại `src/project_paths.py` và `scripts/common.sh`.
Có thể đặt `ISAAC_DIR` nếu chuyển bộ cài Isaac.

## Kiểm tra

```bash
source /opt/ros/humble/setup.bash
/usr/bin/python3 ~/warehouse_twin/tools/check_ros2_fleet.py --require-map
```

Kiểm thử không điều khiển các AGV đang chạy:

```bash
bash ~/warehouse_twin/scripts/test_project.sh --unit
bash ~/warehouse_twin/scripts/test_project.sh --usd
```

Các kiểm thử tích hợp riêng:

- `--ros`: kiểm tra ROS SDK Isaac trên domain cục bộ riêng 171, có thể đặt
  `WAREHOUSE_TEST_DOMAIN` để đổi domain kiểm thử.
- `--physics`: mở Isaac headless với cảnh PhysX nhỏ, không tải AGV/ROS bridge.

## Tài liệu

- [Web giám sát kho 3D](WEB_DASHBOARD.md)
- [Nhà máy hoạt động](FACTORY_LIVE.md)
- [Chu trình AGV](WAREHOUSE_CYCLES.md)
- [Model và bố cục kho](WAREHOUSE_MODELS.md)

Các thử nghiệm cũ và cache Python trong Downloads được đưa vào Thùng rác;
phần mềm tải về, workspace ROS khác và dữ liệu ngoài dự án được giữ nguyên.
