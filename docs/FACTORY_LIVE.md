# Nhà máy hoạt động trong Isaac

Chế độ mô phỏng theo kịch bản: thùng chạy trên 4 tuyến băng chuyền, 8 tay Comau
N220-27 gắp/nhấc/đặt bằng đầu hút bổ sung, AGV hiện hàng sau khi nhận và ẩn hàng
sau khi giao. Hai nhóm AGV vẫn chạy lần lượt từng xe như bản kiểm chứng tuyến.
UR5 trên AGV giữ nguyên tư thế. APF trong `~/apf_ws/src` không sửa.

## Chạy

1. Ctrl+C terminal đang chạy chu trình AGV. Đóng cửa sổ Isaac cũ để chỉ có một
   mô phỏng phát topic. Không cần xóa hoặc sinh lại USD nguồn.
2. Trong terminal mới, chạy:

```bash
bash ~/warehouse_twin/scripts/run_factory_live.sh
```

Script tạo hai file runtime dùng chung model trong `maps/`, rồi mở
`warehouse_factory_runtime.usda` (tham chiếu `warehouse_ros2_ridgeback.usd`), nạp chuyển động rồi in
`[FACTORY] Ready: 4 conveyors, 8 Comau pick/place workcells, 6 AGV load displays`.
Bản launcher chọn camera `/Warehouse/Camera` nhìn toàn kho trong session tạm.
Các dòng `[FACTORY LOAD]` báo đã mở USD, chọn camera, chờ tài nguyên và nạp
animation/ROS. Chờ tài nguyên nền tối đa 30 giây kể từ khi bắt đầu vòng chờ;
nếu texture vẫn đang tải, launcher tiếp tục nạp runtime trên USD đã mở.
Giới hạn này không tính thời gian khởi động Isaac hoặc thời gian xử lý một frame.
Bấm **Play**. Trước khi có bộ điều phối, dây chuyền chạy xem trước (`mode=preview`).

Launcher mặc định dùng profile `fast`: RaytracedLighting, viewport 960 × 540,
một GPU; giảm tải render so với mặc định RealTimePathTracing 1280 × 720 của
Isaac 6.1. Không thay timestep vật lý, lidar, tuyến hoặc thuật toán APF.
Chất lượng hiển thị cũ: `bash scripts/run_factory_live.sh --quality quality`.
Chọn lại chế độ nhanh: `bash scripts/run_factory_live.sh --quality fast`.
Cần đóng phiên Isaac cũ và chạy lại launcher để áp dụng. Mức cải thiện RTF
phải đo trên phiên thực tế, không suy ra trực tiếp từ độ phân giải.

3. Terminal thứ hai:

```bash
WAREHOUSE_FACTORY=1 bash ~/warehouse_twin/scripts/run_warehouse_cycles.sh
```

Sau khi dữ liệu đủ, log có `robot1: pickup`, `robot4: pickup` và
`[FACTORY] mode=linked sim=...s physics_steps=... arm_cycles=... belt_outputs=...`.
Các số tăng dần khi mô phỏng chạy. Xe đến điểm nhận, chờ 3 giây mô phỏng rồi có
thùng trên sàn xe; đến điểm giao, chờ rồi thùng biến mất; xe về bãi và đổi xe.
Đây là hiển thị nhận/trả theo sự kiện, chưa mô phỏng tay gắp chuyển thùng lên AGV.

Pause dừng dây chuyền. `DATA HOLD`, lỗi điều phối hoặc Ctrl+C terminal AGV cũng
giữ dây chuyền. Trong chế độ `WAREHOUSE_FACTORY=1`, mất heartbeat nhà máy sẽ đóng
khóa chạy AGV. Khi chốt lỗi, Ctrl+C, Stop/reset Isaac rồi khởi động chu trình lại.

Chỉ muốn xem dây chuyền và tay máy, không nối điều phối AGV:

```bash
bash ~/warehouse_twin/scripts/run_factory_live.sh --no-ros
```

Hoặc nạp vào cửa sổ Isaac đang mở đúng USD bằng Script Editor, khi đã dừng/reset xe:

```python
import sys
sys.path.insert(0, "/home/dhqg/warehouse_twin/src")
from factory_live import start_factory
start_factory()
```

Không lưu đè USD sau khi nạp animation. Các thay đổi nằm trong session layer tạm,
được gỡ khi dừng driver hoặc đóng app. Mở USD bình thường sẽ không tự chạy animation;
dùng launcher hoặc Script Editor ở trên.

## Phạm vi

- N220 dùng đúng 6 khớp và giới hạn khớp của model, giải tư thế gắp/đặt trước;
  runtime ghi chuyển động các link. Đầu hút và thùng không dùng solver tiếp xúc.
- Thùng trên băng chuyền giữ khoảng cách, chờ trạm, theo đầu hút rồi tiếp tục đi.
  Hàng ra cuối tuyến được tạo lại ở đầu vào để chạy demo liên tục.
- Đồng bộ hiện tại là nhận/trả hàng của AGV và trạng thái chạy/dừng chung. Chưa
  quản lý tồn kho giữa AGV và dây chuyền, chưa mô phỏng PLC hay cảm biến nhà máy thật.
- Dây chuyền chạy theo thời gian mô phỏng: nếu Isaac chạy chậm hơn thời gian thực,
  toàn bộ chuyển động trên màn hình cũng chậm tương ứng.
  Runtime tích lũy `dt` từ callback sau bước vật lý (`omni.physics.core`), không lấy
  độ chênh của timeline hiển thị: USD hiện tại có `startTimeCode=endTimeCode=0`,
  timeline có thể đứng ở 0 trong khi PhysX, AGV và `/clock` vẫn chạy.
  Pause không tích lũy chuyển động bù; Stop reset chu trình.

Chiều cao thùng lấy từ mặt con lăn thực trong USD, không lấy đỉnh khung bảo vệ.
A05 hiện cao khoảng 0,769 m ở lắp ráp và 0,750 m ở đóng gói. Runtime đặt đáy
thùng cách mặt đỡ 2 mm, cập nhật lại vị trí gắp/đặt của N220 theo cùng mặt đỡ.
Module A61 là cổng quét có băng tải ngang; runtime căn mặt con lăn và bỏ chuyển
động lên dốc giả. Dải băng chạy cũng được đặt sát con lăn. Các điều chỉnh runtime
nằm trong session layer; hai USD nguồn cũ không bị ghi đè. Lần build map mới sẽ
sinh thùng đúng chiều cao và đặt tên module `ScanningTransfer`.
Web dùng cùng số đo qua `config/web_scene.json`; cần khởi động lại web và tải
lại trang khi thay cấu hình hình học.

## Lỗi RTX hết resource descriptors

`[Fatal] [omni.rtx] Out of resource descriptors!` là lỗi cấp phát tài nguyên
render, làm Isaac dừng và topic ROS mất dữ liệu. Đây không phải bằng chứng GPU
hết VRAM; không thể kết luận riêng các cảnh báo tham số `OmniGlass` gây lỗi Fatal.

Launcher hiện chuẩn bị 1.034 model lặp thành instance tham chiếu 10 định nghĩa
dùng chung trước khi RTX nạp cảnh. Giữ nguyên model, texture, vị trí, collider,
6 graph ROS và các khớp tay máy. Các opinion tắt physics và bỏ bánh quạt được
đưa vào định nghĩa dùng chung; không đánh dấu instance trực tiếp rồi làm mất
opinion con. Tám N220 và sáu Ridgeback vẫn chỉnh khớp độc lập.

`warehouse_factory_runtime.usda` và `warehouse_factory_runtime.props.usda` là
file sinh lại tự động, không thay thế/xóa hai USD nguồn. Sau lỗi Fatal, đóng
Isaac cũ và dừng chu trình AGV, rồi chạy lại launcher để dùng bản runtime này.

Kiểm tra USD/physics/chuyển động bằng `bash scripts/test_project.sh --render`.
Kiểm thử GPU riêng, khoảng 8–10 phút kể cả khởi động:
`bash scripts/test_project.sh --render-gpu`. Test dùng ROS domain 171 và không
phát lệnh lái; kết quả headless không thay thế kiểm chứng GUI/APF chạy lâu dài.
Tham khảo [tối ưu asset của NVIDIA](https://docs.isaacsim.omniverse.nvidia.com/6.1.0/robot_setup/asset_transformer_rules.html).

## Kiểm chứng

- `test_factory_cycle.py`: mô phỏng 480 giây, cả 4 tuyến xuất hàng, cả 8 tay hoàn
  thành chu kỳ, kiểm tra khoảng cách và tính lặp lại sau reset.
- `test_factory_scene.py`: dùng USD/model thật, giả lập API timeline/event của GUI;
  đầu hút tới đỉnh thùng sai số dưới 5 mm, thùng theo tay khi nhấc, mọi tay hoàn
  thành chu kỳ; kiểm tra hiển thị tải AGV, hold/pause/reset và gỡ session layer.
- `test_warehouse_cycle_dispatch.py`: cả 6 xe hoàn tất chu trình offline; sự kiện
  tải/giao hàng đúng thời điểm; heartbeat nhà máy khóa chạy khi thiếu/hỏng.
- `test_factory_scene.py --ros`: đã chạy với thư viện Humble/Python 3.12 đi kèm
  Isaac, domain thử riêng 171. Hai node trao đổi trạng thái và heartbeat khi
  context mặc định chưa khởi tạo; lỗi transport chỉ xử lý một lần và phát
  heartbeat lỗi. Runtime giữ executor riêng cùng context với node, không dùng
  executor mặc định của Kit.
- `test_factory_startup.py`: tài nguyên nền bị treo không gây vòng chờ vô hạn;
  chờ hữu hạn và đóng app được xử lý; camera chứa toàn bộ 8 góc kho 120 × 80 × 12 m
  trong khung hình và không ghi đè camera ở file USD gốc.
- `test_factory_scene.py`: bổ sung hồi quy timeline luôn bằng 0 nhưng callback
  vật lý vẫn tăng thời gian, chuyển ma trận USD của thùng, chạy đủ 8 tay và xuất
  hàng; không bỏ qua bước tích lũy lớn hơn 1 giây.
- `test_factory_physics_clock.py`: đã chạy Isaac headless với PhysX thật trên
  RTX 2000 Ada, cảnh thử có timeline 0..0, không tải AGV/ROS bridge. Đạt 22 giây
  vật lý/1320 bước, timeline `0.000s`, tổng 12 chu kỳ tay và 4 thùng ra; Pause
  giữ nguyên số bước. Đây là kiểm thử tích hợp clock, chưa phải chạy toàn kho
  cùng 6 lidar và APF.

- `test_factory_render.py`: 1.034 instance dùng chung 10 định nghĩa; toàn bộ số
  lượng hình học khi duyệt proxy, cờ physics, bbox từng model và 6 graph ROS
  khớp bản gốc. Tám tay máy vẫn chỉnh khớp độc lập. USD nguồn không đổi.
  `test_factory_scene.py` cũng chạy đạt trên bản runtime tối ưu.
- Hồi quy thùng/băng chuyền: kiểm tra đáy cả 52 thùng với mặt con lăn thực
  tại nhiều bước chạy, kiểm tra A61 ngang và căn đúng mặt đỡ; N220 vẫn gắp đúng
  đỉnh thùng trong 5 mm. Build thử ra `/tmp` cũng đặt đúng 52 thùng ngay trong USD.
  Isaac GPU chạy đạt 26 giây vật lý (100,2 giây thực sau khởi động), đủ 6 scan/odom,
  8 tay máy hoàn tất chu kỳ và có thùng ra. Chrome kiểm tra độ cao 3D và nghiệp vụ
  nhập hàng/tạo đơn đạt; 11 kiểm thử web và kiểm thử điều phối vẫn đạt.
- `test_factory_render_gpu.py`: đã chạy toàn kho headless trên RTX 2000 Ada,
  6 lidar RTX + 6 odom và camera 960 × 540, đủ chuyển động tay máy/băng chuyền.
  Chạy 450 giây thực sau khởi động (203,6 giây vật lý), mỗi lidar nhận hơn
  1.900 bản tin; số render product giữ ở 8; không tái hiện lỗi Fatal descriptor.
  Các cảnh báo vật liệu của asset vẫn còn, gồm OmniGlass và shader cần trục.
  Lượt 450 giây bị kẹt lúc teardown mặc định của Kit sau khi các kiểm tra đạt;
  đã dừng riêng tiến trình thử. Test chuyển sang `SimulationApp.close` với
  `skip_cleanup=True` (không có USD/capture cần lưu); lượt xác nhận 100 giây
  chạy đạt 31 giây vật lý và tự thoát mã 0, trả lại tài nguyên GPU.

Chưa kiểm chứng GUI chạy lâu cùng APF và web sau tối ưu. Thử nghiệm GPU dùng
domain 171, không phát lệnh lái; chưa kiểm chứng hành trình AGV hay DDS điều
phối giữa hai tiến trình trong lượt thử này. Không kết luận đã loại bỏ mọi
nguyên nhân có thể gây hết descriptor khi chạy dài hơn.

## File

- `run_factory_live.sh`, `factory_app.py`: mở Isaac và nạp runtime.
- `factory_render.py`: sinh wrapper/định nghĩa prop dùng chung trước khi nạp RTX.
- `factory_surfaces.py`: đo mặt con lăn/băng đỡ và căn module A61; dùng chung
  chiều cao cho runtime, sinh map, giải tư thế tay và export mô hình web.
- `factory_live.py`: chuyển động USD, đầu hút, hàng trên AGV, liên kết ROS.
- `factory_cycle_core.py`: dòng thùng và trạng thái gắp/đặt.
- `factory_kinematics.py`, `factory_motion_plan.json`: động học model Comau và tư thế.
- `prepare_factory_motion.py`: giải lại tư thế khi đổi model/vị trí trạm.
- `warehouse_cycles.py`: phát `/warehouse/factory_state`, nhận
  `/warehouse/factory_heartbeat`; `run_warehouse_cycles.sh` bật kiểm tra bằng
  `WAREHOUSE_FACTORY=1`.
