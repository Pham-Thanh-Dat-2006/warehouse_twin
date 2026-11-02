# Kho dùng model đã chọn

Mở `~/warehouse_twin/maps/warehouse_environment_models.usd`: kho hiện tại kèm 6 Ridgeback + UR5.

Đã ghép 40 RackLong_A3, 8 Comau N220-27, 20 AgiBot A3 Ultra, 6 bàn packing,
2 giàn cẩu, 3 Forklift_C, 5 quạt treo tường và module cửa phía tây.
Dây chuyền dùng A05; hai module băng chuyền qua cổng quét A61 đặt ở đầu ra khu đóng gói.
Pallet_A1 và Cardbox_A3 dùng ở băng chuyền/khu dock.

20 humanoid: 8 cạnh dây chuyền lắp ráp, 6 cạnh bàn packing,
2 cạnh cổng quét băng chuyền, 4 ở tiếp nhận/staging. Các robot công nhân và
N220 đứng yên trong USD môi trường; launcher nhà máy bổ sung chuyển động N220. APF giữ nguyên.

Nguồn/path được lưu ở `../config/warehouse_assets_requested.json`; thông tin nguồn
cũng nằm trong metadata của USD. Model N220 đầy đủ nằm trong `../assets/nvidia_cache/`;
các entry USD tải rời trong Home trước đây thiếu payloads và được dọn vào Thùng rác.
Cửa được khôi phục entry USD vào cùng thư mục payloads đã có.

Sinh lại map bằng CPU:

```bash
bash ~/warehouse_twin/scripts/build_warehouse_map.sh
bash ~/warehouse_twin/scripts/build_warehouse_map.sh --verify
```

Sinh bản có 6 Ridgeback (cần GPU):

```bash
cd ~/isaacsim/isaac-sim-standalone-6.1.0-linux-x86_64
ROBOT=ridgeback ROBOTS=6 ./python.sh ~/warehouse_twin/src/warehouse.py
```

Tải/cập nhật các model NVIDIA và lớp USD phụ thuộc:

```bash
bash ~/warehouse_twin/scripts/build_warehouse_map.sh --download
```

Mặc định texture/MDL NVIDIA được tham chiếu qua HTTPS, cần mạng khi render.
Thêm `--offline` sau `--download` nếu muốn tải toàn bộ; dữ liệu có thể lớn.
Vật liệu/texture của AgiBot và bàn packing đã tải trong gói Hugging Face.

Các gói HF dùng đúng revision:

```bash
hf download AGIBOT-Yuanzheng/A3_Ultra_usd --repo-type dataset --revision d24fd57ec9a9e917741fa9e871a71907ea7e2307 --include 'raise_a3_ultra_t3d0/*' --exclude '*/source_assets/*.png' --local-dir ~/warehouse_twin/assets/simready-assets-d24fd57e
hf download nvidia/simready-assets --repo-type dataset --revision 653d91e182011f357cf1644013cc94ddf194d349 --include 'table_deluxe_packing_a01/*' --exclude '*/source_assets/*.png' --local-dir ~/warehouse_twin/assets/simready-assets-653d91e1
```

Xe tải, cổng quét, giàn thép trần và phòng kính còn là hình học dựng bằng script.
Chưa kiểm chứng render RTX hoặc chuyển động của 6 robot trong phiên không có GPU.

Bố cục hiện tại: 2 cụm kệ trái–phải, mỗi cụm 20 module (5 hàng × 4).
Lối giữa rộng 5,5 m, các module nối dãy cách nhau 1,5 m; khoảng giữa các hàng
khoảng 3,45 m. Không tạo collider bao kín toàn cụm kệ.

61 wall panel thật thay các tường hộp; chiều cao vỏ kho khoảng 11,1 m.
Đã bỏ đèn hex-grid và các RectLight trên trần; giữ DomeLight để chiếu sáng nền.
Hai ô cẩu có vạch vàng và pallet hàng dưới khung; chưa lập trình thao tác gắp.
Cần trục bên phải giữ góc 180°. Tổng 59 pallet đầy hàng ngoài phần hàng có sẵn trong kệ.
Hành lang robot y=32–48 được giữ trống.

Model đèn và tường dùng cùng revision 653d91e182011f357cf1644013cc94ddf194d349:

```bash
hf download nvidia/simready-assets --repo-type dataset --revision 653d91e182011f357cf1644013cc94ddf194d349 --include 'lighting_overheadLed_hexGrid_a01/*' --include 'structure_wall_straight_a01/*' --exclude '*/source_assets/*.png' --local-dir ~/warehouse_twin/assets/simready-assets-653d91e1
```

Sơ đồ CPU: `~/warehouse_twin/docs/diagrams/warehouse_split_layout.png`.
Chưa kiểm chứng hình ảnh RTX/độ sáng thực tế do phiên hiện tại không nhận GPU.

Quạt đã chuyển sang dạng treo tường: đáy ở 7,2 m, có giá đỡ thép;
ẩn bánh xe và dây nguồn kéo dưới sàn của model quạt di động.

Bản hiện tại mặc định thêm 6 robot: 3 xe ở x=10, 3 xe ở x=110; các làn
33 / 35,6 / 38,2 / 40,8 / 43,4 / 46 m. Dùng ENV_ONLY=1 khi chỉ cần sinh môi trường.
Các robot giữ physics/articulation; không thêm ROS2 graph trong bước dựng kho.
Khi tạo graph ROS2 tiếp theo, đặt SRC=~/warehouse_twin/maps/warehouse_environment_models.usd.

Để phát topic ROS2: mở `~/warehouse_twin/maps/warehouse_ros2_ridgeback.usd`, không phải
`warehouse_environment_models.usd`. Bấm Play sau khi stage tải xong.
Lidar dùng bản cache local; LaserScan frame_id có dạng robotN/rplidar_link.
Script tạo graph mặc định đọc map hiện tại và tạo cho 6 xe.

Kiểm tra odom và TF của cả 6 xe (chỉ đọc, không gửi cmd_vel):

```bash
source /opt/ros/humble/setup.bash
/usr/bin/python3 ~/warehouse_twin/tools/check_ros2_fleet.py
```

Chu trình mới: xem WAREHOUSE_CYCLES.md. Hai nhóm 3 xe phục vụ kho trữ/lắp ráp
và kho trữ/đóng gói; mỗi nhóm một xe hoạt động. Khởi động bằng
`bash ~/warehouse_twin/scripts/run_warehouse_cycles.sh` sau khi dừng bộ chạy SLAM/APF cũ
và mở lại file ROS2. `../legacy/run_apf.sh`/`../legacy/send_routes.sh` là kịch bản đi ngang cũ.
