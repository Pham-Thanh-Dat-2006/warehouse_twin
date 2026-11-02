# Chu trình AGV trong kho

Bản kiểm chứng này giữ nguyên code APF. Các file trong `~/apf_ws/src` không đổi.
Chỉ thêm bộ điều phối gọi `set_goal`, khóa chạy cho bridge và adapter tọa độ/lidar.

## Chu trình

- Robot1 → robot2 → robot3, mỗi lần một xe: bãi chờ → nhận hàng trước cụm kệ trái
  `(43,49)` → giao cạnh đầu dây chuyền lắp ráp `(47,23)` → về đúng bãi chờ.
- Robot4 → robot5 → robot6, mỗi lần một xe: bãi chờ → nhận hàng trước cụm kệ phải
  `(85,49)` → giao tại khu staging đóng gói `(91,27)` → về bãi chờ.
- Hai nhóm chạy đồng thời, tối đa hai xe di chuyển. Dừng 3 giây mô phỏng tại điểm
  nhận/trả và bãi trước khi đổi xe. Tiếp tục lặp sau robot3/robot6.
- Tuyến lắp ráp có vạch xanh dương; đóng gói xanh lá. Những xe đang chờ giữ khóa vận tốc.
- Mặc định giới hạn 1,0 m/s (trước đây 0,7 m/s), giảm tịnh tiến khi quay gấp. Đây là chu trình di chuyển/dừng;
  chưa có animation tay UR5 gắp, đặt. Chế độ nhà máy hoạt động bổ sung băng chuyền,
  tay N220 và hiển thị tải AGV: xem [FACTORY_LIVE.md](FACTORY_LIVE.md).

## Tọa độ và lidar

`IsaacReadWorldPose` đọc pose vật lý trong kho, xuất `/robotN/warehouse_pose`.
Bộ điều phối ghép world pose với `/robotN/odom` theo timestamp (ưu tiên trùng, cho phép lệch tối đa 20 ms mô phỏng), tính TF
`robotN/map → robotN/odom`; các map được nối vào frame chung `warehouse`.
APF vẫn lấy `robotN/map → robotN/base_link` như cũ.
Chế độ này dùng pose mô phỏng để kiểm chứng tuyến, không dùng SLAM làm định vị lái.
Không chạy đồng thời `run_apf.sh`/slam_toolbox vì sẽ có hai nguồn TF cho odom.
Bản SLAM cũ vẫn được giữ để dùng lại sau khi tuyến đã đạt.

APF cũ cộng cố định pi/2 vào góc lidar. Relay ở chế độ `--apf-alignment` tạo frame
`robotN/apf_lidar` quay +pi/2 so với lidar thật, trừ pi/2 khỏi góc scan. Cách biểu diễn
này giữ nguyên vị trí vật cản vật lý, đồng thời bù quy ước cũ của APF. Relay mặc định
vẫn chuyển tiếp như trước nếu không có cờ này.

## Chạy

1. Bấm Stop trong Isaac. Ctrl+C terminal chạy `run_apf.sh` cũ và các bridge/SLAM cũ.
2. Mở lại **`~/warehouse_twin/maps/warehouse_ros2_ridgeback.usd`** đã thêm WorldPose; bấm Play để reset
   xe về 6 vị trí xuất phát. Không mở bản environment khi chạy điều khiển ROS2.
3. Có thể xác nhận topic mới trước khi khởi động chu trình:

```bash
source /opt/ros/humble/setup.bash
ros2 topic echo /robot1/warehouse_pose --once --field pose.pose.position
```

Ban đầu x/y phải gần `(10,33)`. Sau đó:

```bash
bash ~/warehouse_twin/scripts/run_warehouse_cycles.sh
```

Không chạy `send_routes.sh`; chương trình tự gửi đích theo chu trình.
Ctrl+C dừng các tiến trình chu trình và bridge gửi vận tốc khớp bằng 0.
Xem trạng thái/so pose map với pose thật:

```bash
source /opt/ros/humble/setup.bash
/usr/bin/python3 ~/warehouse_twin/tools/check_ros2_fleet.py --require-map
```

`map/world_diff` cần gần 0. Thay tốc độ/thời gian chờ khi cần:

```bash
WAREHOUSE_SPEED=0.25 WAREHOUSE_DWELL=5 bash ~/warehouse_twin/scripts/run_warehouse_cycles.sh
```

Mức mặc định hiện tại là `WAREHOUSE_SPEED=1.0`, gia tốc tịnh tiến `WAREHOUSE_ACCEL=0.8` m/s²,
giới hạn quay vẫn 0,7 rad/s. APF có thể giảm lệnh gần góc cua, đích hoặc vật cản;
1,0 m/s là trần tốc độ, không phải tốc độ bắt buộc ở mọi điểm.
Không khuếch đại cmd_vel hoặc sửa mã APF.

Để áp dụng cho một phiên đã chạy: Ctrl+C terminal chu trình, Stop rồi Play/reset
trong Isaac để xe về bãi xuất phát, sau đó chạy lại script. Bridge đọc giới hạn
khi khởi tạo; sửa biến môi trường không cập nhật các bridge đang chạy.
Không cần build lại USD hoặc khởi động lại web.

Nếu cần quay về mức cũ:

```bash
WAREHOUSE_SPEED=0.7 WAREHOUSE_ACCEL=0.5 bash ~/warehouse_twin/scripts/run_warehouse_cycles.sh
```

Kiểm tra **RTF** trên web: tốc độ quan sát theo thời gian thực xấp xỉ tốc độ
mô phỏng × RTF. Ví dụ 1,0 m/s ở RTF 0,5 tương đương khoảng 0,5 m/s thực.
Tăng giới hạn lái không tự làm renderer/physics chạy nhanh hơn. Có thể chọn
chất lượng 3D web **Tiết kiệm** khi mở web cùng Isaac; đây chỉ giảm tải trình duyệt.

## Kiểm chứng đã làm

- Kiểm tra cú pháp, import ROS2/service từ workspace, kiểm tra environment Bash.
- Kiểm tra 6 publisher world pose trong USD và đường nối graph.
- Lấy mẫu tuyến mỗi 0,15 m, kiểm tra với collider thật trong USD: tâm tuyến cách
  vật cản gần nhất khoảng 1,98 m. Bbox robot có bán kính bao khoảng 0,71 m.
- Kiểm thử điều phối offline: cả 6 xe hoàn tất nhận/trả/về bãi; mỗi nhóm không quá
  một xe được cấp chạy; mất dữ liệu, lệch đường và reset clock đều đóng khóa.
- Kiểm thử phép đổi tọa độ, bù góc scan và khóa an toàn/đổi yaw trong bridge.
- **Chưa kiểm chứng chuyển động APF/va chạm và cả chu trình trên GPU.** Kiểm tra
  hình học và kiểm thử điều phối không thay thế chạy Isaac thực tế.

Giám sát dữ liệu dùng hai đồng hồ: tuổi timestamp tối đa 0,7 giây **mô phỏng**
và khoảng im lặng nhận dữ liệu tối đa 3 giây **thực**. Khi quá hạn, mọi khóa chạy
đóng ngay và log `DATA HOLD` chỉ rõ robot/luồng cùng `sim_age`, `wall_age`.
Dữ liệu trở lại ổn định 0,3 giây thì tiếp tục; nếu vẫn thiếu thêm 3 giây thực,
chương trình chốt lỗi `Persistent stale data` và giữ dừng. Pause của Isaac giữ
khóa dừng nhưng không tự chốt lỗi cảm biến. Ghép pose không phát lại TF trùng/cũ.

Các điều kiện lệch tâm tuyến >0,75 m, hai xe gần nhau <2 m hoặc không tiến triển
25 giây mô phỏng vẫn dừng. Khi chốt lỗi: Ctrl+C, Stop/reset Isaac rồi chạy lại.

Kiểm thử bổ sung đã đạt: clock chậm, dropout ngắn/phục hồi, mất dữ liệu kéo dài,
ghép timestamp lệch 15 ms và từ chối >20 ms, cùng timeout pose của bridge.

Nguồn đối chiếu: [Isaac Read World Pose](https://docs.isaacsim.omniverse.nvidia.com/6.2.0/py/source/extensions/isaacsim.core.nodes/docs/ogn/OgnIsaacReadWorldPose.html)
(mô tả/cổng khớp tài liệu SDK 6.1 đã cài) và
[quy ước LaserScan của ROS 2](https://github.com/ros2/common_interfaces/blob/rolling/sensor_msgs/msg/LaserScan.msg).
