# KhoTwin — Trung tâm giám sát kho 3D

Danh sách chức năng theo nghiệp vụ: [WEB_FEATURES.md](WEB_FEATURES.md).

Web chạy trên cùng PC Ubuntu, mặc định `http://127.0.0.1:8080`.
Dùng Python hệ thống, SQLite và HTML/CSS/JavaScript; không cần Node, npm,
rosbridge hoặc cài thêm package Python. Bộ thu ROS chỉ subscribe dữ liệu,
không phát cmd_vel/joint_command, không gọi service điều khiển APF.

## Chạy

Để có mã phiên/chuyến ổn định và telemetry sản xuất mới, khởi động lại hai
terminal Isaac/chu trình đang chạy sau khi cập nhật mã:

```bash
# Terminal 1: đợi Ready, thấy kho rồi bấm Play
bash ~/warehouse_twin/scripts/run_factory_live.sh
```

```bash
# Terminal 2: điều phối hiện có, mỗi nhóm lần lượt một xe
WAREHOUSE_FACTORY=1 bash ~/warehouse_twin/scripts/run_warehouse_cycles.sh
```

```bash
# Terminal 3: web theo dõi và quản lý hàng hóa
bash ~/warehouse_twin/scripts/run_web.sh
```

Mở **http://127.0.0.1:8080**. Có thể chạy web trước khi có Isaac:
web hiển thị “Chờ dữ liệu ROS”; không tự tạo vị trí hoặc sản lượng giả.
Đổi cổng nếu đang bận: `bash scripts/run_web.sh --port 8081`.
Ctrl+C terminal web dừng web; không dừng hoặc thay đổi lệnh lái của AGV.

Sau khi cập nhật mã web, dừng rồi chạy lại `run_web.sh` và nhấn
**Ctrl+Shift+R** trong trình duyệt. Tiến trình Python cũ không tự nạp lại mã:
có thể vẫn nhận ROS nhưng API thiếu hình học `scene`, khiến 3D chờ khởi tạo.
Web phát hiện trường hợp này và chuyển sang 2D với hướng dẫn khởi động lại.
Lỗi dựng 3D được báo riêng; các bản tin ROS hợp lệ vẫn tiếp tục cập nhật 2D.

Xem giao diện bằng dữ liệu demo, không cần Isaac/ROS:

```bash
bash ~/warehouse_twin/scripts/run_web.sh --demo
```

Demo luôn có nhãn rõ, dùng database trong bộ nhớ, tách hoàn toàn dữ liệu
vận hành. Thời gian demo tăng tốc 6 lần. Tắt demo là xóa dữ liệu demo.

## Giao diện Digital Twin 3D

Bố cục tối ba cột tham khảo [WareTwin](https://ware-twin.vercel.app/): thống kê
đội xe/nhiệm vụ/nguồn dữ liệu bên trái; kho 3D ở giữa; xe được chọn, góc quan sát
và nhật ký bên phải. Các màn nhập hàng/đơn/tồn kho vẫn giữ nghiệp vụ hiện có.

- **Kho 3D:** kéo chuột để xoay, cuộn để zoom; chọn AGV bằng nhãn hoặc thân xe.
  “Đến xe” phóng tới AGV, “Theo góc nhìn xe” bám theo xe trên web.
- **Bản đồ 2D:** xem vị trí toàn kho với cùng tọa độ và dữ liệu ROS.
- **Tuyến xe:** hiển thị tuyến hiện tại và vệt đã đi.
- **Bản đồ nhiệt:** thời gian hiện diện quan sát từ pose, theo ô 2,5 m. Không
  đếm lại timestamp trùng; xóa khi đồng hồ mô phỏng reset. Đơn vị là giây AGV,
  không phải dự báo tắc nghẽn.
- **Góc quan sát 3D:** chọn kho trái/phải, lắp ráp, đóng gói hoặc dock; “Mở lớn”
  chuyển góc đó vào khung chính. Đây là góc nhìn mô hình web, chưa phải video Isaac.
- **Thanh công cụ:** xoay, pan, đặt lại góc, hiện tuyến/nhãn, đo hai điểm trên sàn
  theo mét, lưu ảnh PNG và toàn màn hình.
- **Chất lượng:** Tiết kiệm / Cân bằng / Rõ nét. Mức tiết kiệm giảm độ phân giải
  và tần số vẽ của trình duyệt, không thay đổi physics/lidar hay APF trong Isaac.
- **Phân tích:** nhận xét theo quy tắc từ dữ liệu mới/độ trễ/đơn chờ/RTF; chưa
  nối LLM, không tự phát lệnh điều khiển robot.

Hình học web là mô hình nhẹ bằng Three.js 0.187.0: 40 kệ lấy kích thước thật từ
USD, 6 Ridgeback proxy, 4 băng chuyền, 8 chuỗi khớp N220 và các khu/thiết bị.
Đây không phải render đầy đủ vật liệu/model USD gốc. Thư viện đã lưu cục bộ
trong `web/public/vendor/` kèm giấy phép MIT, không cần CDN khi mở web.

`config/web_scene.json` được sinh bằng OpenUSD từ bản environment. Lệnh build
kho đầy đủ tự cập nhật file này. Khi cần xuất lại riêng:

```bash
source ~/warehouse_twin/scripts/common.sh
warehouse_usd_env
"$isaac_dir/python.sh" "$project_dir/tools/export_web_geometry.py"
```

Telemetry mới có tọa độ 52 thùng và 8 chuỗi điểm khớp. Web chuyển trục
`(x,y,z)` của USD thành `(x,z,-y)` và nội suy để hiển thị mượt. Khi mất dữ liệu,
xe được đánh dấu cũ và chuyển động dừng ở giá trị cuối, không tự chạy tiếp.
Khởi động lại runtime Isaac để có các trường telemetry mới.

## Các màn hình

1. **Tổng quan:** số hàng khai báo, AGV online/đang chạy, chuyến đang vận chuyển,
   chuyến đã giao, bản đồ 120 × 80 m, tuyến và vệt di chuyển, thông tin xe được chọn.
2. **Hàng hóa:** nhập SKU và số lượng theo vị trí; mức tồn tối thiểu; tồn tại chỗ,
   giữ chỗ, khả dụng; tìm kiếm, lọc vị trí và xuất CSV.
3. **Đơn vận chuyển:** tạo đơn theo hai tuyến hiện có, mức ưu tiên, ghi chú,
   ghép xe, chi tiết lịch sử theo mã kiện/đơn, hủy đơn chờ, đối soát chuyến gián đoạn.
4. **Đội xe:** sáu AGV, pose, tốc độ đo, lidar, nhóm phục vụ, tình trạng tải,
   số chu kỳ và liên kết xem xe trên bản đồ.
5. **Dây chuyền & tay máy:** 4 băng chuyền, 8 Comau N220, trạng thái/chu kỳ,
   số thùng ra, thời gian vật lý và đồ thị sản lượng.
6. **Nhật ký:** nhập kho, tạo/hủy đơn, nhận/giao hàng, phiên điều phối thay đổi,
   trạng thái từng nguồn dữ liệu và cảnh báo mất dữ liệu/tồn thấp.

Giao diện nhận snapshot qua Server-Sent Events mỗi 250 ms. Pose/lidar/clock được
thu theo tần số ROS; telemetry sản xuất phát mỗi 0,5 giây thực. Dữ liệu quá 3 giây
không được coi là đang online; vị trí cũ vẫn hiện trên bản đồ với nhãn mất dữ liệu.

## Theo dõi hàng và ghi sổ tồn kho

- Ban đầu dữ liệu vận hành trống. Vào **Hàng hóa → Nhập hàng** để khai báo.
  Không lấy 760 thùng hình học của map làm số tồn kho thật.
- Đơn đi **lắp ráp** lấy từ kho trái, ghép robot1–3. Đơn đi **đóng gói** lấy
  từ kho phải, ghép robot4–6. Đây là các tuyến đã có trong bộ điều phối.
- Tạo đơn giữ chỗ số lượng tại kho nguồn. Khi một AGV bắt đầu chu kỳ nhận mới,
  backend ghép đơn đang chờ theo ưu tiên. Không ghép đơn vào kiện đã trên xe.
- Khi nhận xong: trừ kho nguồn một lần, trạng thái `in_transit`. Khi giao xong:
  cộng kho đích một lần, trạng thái `delivered`. Nhận lặp cùng message không trừ/cộng lại.
- Chu kỳ không có đơn khai báo vẫn được gắn **mã kiện theo dõi**, nhưng không
  tự đoán SKU/số lượng và không ghi sổ tồn kho.
- Phiên mô phỏng thay đổi, hoặc chuyển chu kỳ mà chưa thấy giao: đơn thành
  **Cần đối soát**. Người vận hành xác nhận hàng đã trả kho hoặc đã giao;
  backend không tự ghi nhận giao thành công khi mất dữ liệu.

**Giới hạn:** đơn là lô hàng khai báo gắn với chu kỳ mô phỏng có sẵn; không phải
lệnh yêu cầu APF chạy theo tuyến mới. Chưa có barcode/RFID, kiểm đếm tự động,
đo tải trọng hoặc liên kết từng mesh thùng USD với SKU. Chưa tích hợp PLC,
camera nhận dạng hàng, phân quyền người dùng hoặc WMS/ERP bên ngoài.

## Lưu dữ liệu

Database vận hành: `web/data/warehouse.sqlite` (SQLite WAL). Tồn kho, đơn và
nhật ký được giữ qua các lần tắt web. Pose/vệt xe và biểu đồ telemetry là dữ
liệu phiên trong bộ nhớ. Mã `run_id` + robot + số chu kỳ giữ định danh chuyến
khi chỉ khởi động lại web; khởi động lại bộ điều phối tạo mã phiên mới.

Có thể chọn database khác bằng `--database /đường/dẫn/kho.sqlite`.
Muốn sao lưu đầy đủ: dừng web trước khi copy database, hoặc dùng công cụ
SQLite backup; không chỉ copy file chính khi WAL còn đang được ghi.

## Nguồn dữ liệu

| Topic | Dữ liệu web |
|---|---|
| `/robotN/warehouse_pose` | Pose toàn kho và tốc độ suy từ pose/time stamp |
| `/robotN/scan` | Tình trạng nhận lidar, không tải toàn bộ tia lên trình duyệt |
| `/clock` | Thời gian mô phỏng, real-time factor ước tính |
| `/warehouse/factory_state` | Phiên, nhóm/phase, tải xe, số chu kỳ, hold/fault |
| `/warehouse/factory_heartbeat` | Runtime nhà máy còn hoạt động |
| `/warehouse/factory_telemetry` | Băng chuyền, tay máy, lượng ra, thời gian vật lý |

Các thay đổi ở `warehouse_cycles.py` chỉ bổ sung metadata giám sát;
`factory_live.py` bổ sung publisher telemetry. Mã APF không thay đổi.

## Kiểm chứng

```bash
bash ~/warehouse_twin/scripts/test_project.sh --web
bash ~/warehouse_twin/scripts/test_project.sh --web-ros
```

- 11 kiểm thử model/HTTP: tồn kho giữ chỗ, idempotence nhận/giao, hủy, bảo toàn
  dữ liệu qua restart, mất sự kiện/đối soát, pose cũ, heatmap theo timestamp, validation, API/CSV/SSE và
  giới hạn đường dẫn file tĩnh.
- ROS DDS domain riêng: pose, scan, clock, dispatcher, heartbeat và production
  đi vào model web; không có publisher điều khiển xe.
- Runtime Isaac SDK: telemetry có đủ 4 băng chuyền và 8 tay máy.
- Chrome thật: 6 màn hình, 6 marker AGV, nhập/tìm hàng, báo thiếu tồn, tạo đơn,
  chi tiết chuyến, chọn xe, mobile không tràn ngang, không có exception JS.
- Kiểm thử điều phối APF/bridge cũ vẫn đạt.

Chưa chạy nghiệm thu toàn kho + 6 lidar + web cùng lúc trên một phiên Isaac GUI.
Ảnh chụp trong `diagrams/warehouse_dashboard.png`, `warehouse_heatmap_web.png` và `warehouse_production_web.png`
là giao diện ở chế độ demo, không phải số liệu vận hành thật.

Kiểm thử Chrome bổ sung (`tests/web_twin3d_qa.py` với browser thử cục bộ): 40 kệ,
6 target xe đúng trục tọa độ ROS, 8 chuỗi khớp, 52 thùng; cả 4 chế độ xem, chọn/
theo xe, preset camera, đổi chất lượng, pan/orbit, nhãn/tuyến, đo đoạn 10 m,
lưu PNG, phân tích và mobile; draw calls được giới hạn dưới 200 trong cảnh thử.
