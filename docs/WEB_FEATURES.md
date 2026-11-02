# Chức năng web KhoTwin hiện có

Bản ghi ngày **30/10/2026**, đối chiếu giao diện và mã nguồn hiện tại.
Web chạy trên PC Isaac, địa chỉ mặc định `http://localhost:8080`.

## 1. Tổng quan Digital Twin

| Chức năng | Nội dung hiện có |
| --- | --- |
| Kho 3D | Mô hình nhẹ của kho 120 × 80 m: 40 kệ, 6 AGV, 4 băng chuyền, 8 tay N220 và các khu chức năng. |
| Đồng bộ chuyển động | Vị trí/hướng AGV, trạng thái mang hàng, vị trí 52 thùng băng chuyền và chuỗi khớp tay máy lấy từ telemetry khi có dữ liệu. |
| Bản đồ 2D | Xem bố cục, vị trí/hướng xe, xe được chọn và tình trạng tải. |
| Tuyến xe | Hiện tuyến đã cấu hình cho các pha nhận/giao/về bãi và vệt xe đã đi. |
| Bản đồ nhiệt | Thời gian AGV hiện diện trong ô 2,5 m, gồm cả lúc đỗ; tích lũy trong phiên web, xóa khi reset clock. |
| Thao tác quan sát | Xoay, zoom, kéo góc nhìn, đặt lại camera, bật/tắt tuyến và nhãn. |
| Chọn/theo xe | Chọn AGV trên mô hình/bản đồ hoặc danh sách; đưa camera tới xe và bám theo xe. |
| Góc quan sát phụ | Toàn kho, kho trái/phải, lắp ráp, đóng gói, dock; mở lớn góc đang chọn. |
| Công cụ 3D | Đo khoảng cách hai điểm trên sàn theo mét, lưu ảnh PNG, xem toàn màn hình. |
| Chất lượng hình ảnh | Ba mức Tiết kiệm, Cân bằng, Rõ nét cho phần render web. |
| Thống kê tổng quan | AGV online/di chuyển/có nhiệm vụ/chờ, đơn chờ/đang giao/đã giao, tồn kho, số SKU và biểu đồ sản lượng. |

## 2. Quản lý hàng hóa và tồn kho

- Khai báo SKU, tên hàng, đơn vị, số lượng, vị trí và mức tồn tối thiểu.
- Nhập thêm hàng vào SKU đã có; cập nhật thông tin khai báo khi nhập.
- Quản lý bốn vị trí: kho trữ trái, kho trữ phải, khu lắp ráp, khu đóng gói.
- Hiện tồn tại từng vị trí, lượng giữ chỗ và lượng khả dụng.
- Tìm theo SKU/tên hàng, lọc vị trí, xuất bảng tồn kho CSV.
- Cảnh báo khi **tổng tồn của SKU** thấp hơn mức tối thiểu.
- Giữ chỗ khi tạo đơn; trừ nguồn khi ghi nhận đã nhận, cộng đích khi ghi nhận đã giao.
- Chống cộng/trừ lặp khi nhận lại cùng sự kiện mô phỏng.

Tồn kho là số liệu khai báo và ghi sổ theo sự kiện điều phối. Các thùng hình học
trong USD không tự trở thành hàng tồn có SKU.

## 3. Đơn vận chuyển và truy vết hàng

- Tạo đơn với SKU, số lượng, ba mức ưu tiên và ghi chú; kiểm tra đủ hàng khả dụng.
- Hai tuyến đang hỗ trợ:
  - Kho trữ trái → lắp ráp: AGV 01–03.
  - Kho trữ phải → đóng gói: AGV 04–06.
- Ghép đơn chờ theo ưu tiên khi AGV bắt đầu chu kỳ nhận mới; không ghép vào chuyến đã mang hàng.
- Theo dõi mã đơn/kiện, SKU, số lượng, nguồn/đích, AGV thực hiện và thời điểm cập nhật.
- Các trạng thái: **Chờ ghép chuyến → Đến nhận → Đang vận chuyển → Đã giao**;
  bổ sung **Đã hủy**, **Cần đối soát**, **Đã trả kho** khi phù hợp.
- Mở chi tiết đơn để xem tiến trình và nhật ký sự kiện của chuyến đó.
- Tìm theo mã đơn/SKU/tên hàng, lọc trạng thái và xuất CSV.
- Hủy đơn còn chờ để giải phóng lượng giữ chỗ.
- Đánh dấu cần đối soát khi đổi phiên hoặc thiếu sự kiện giao; người vận hành
  xác nhận trả kho hoặc đã giao theo các điều kiện của đơn.
- Tự gắn mã kiện theo dõi cho chuyến chưa khai báo SKU; không tự ghi sổ tồn kho cho chuyến này.

Web **gắn đơn với chu trình AGV đã có**. Việc tạo đơn chưa phát lệnh cho APF
chạy một tuyến mới hoặc tự chọn một đích bất kỳ.

## 4. Giám sát đội xe AGV

- Hiện thông tin cả 6 Ridgeback + UR5, chia nhóm lắp ráp và đóng gói.
- Tọa độ toàn kho, hướng xe, tốc độ ước tính từ pose/thời gian mô phỏng.
- Tình trạng nhận pose/lidar, độ trễ dữ liệu và trạng thái online.
- Pha nhiệm vụ, đang chờ tại trạm, mang/không mang hàng và mã chuyến hiện tại.
- Số chu kỳ hoàn tất; chọn xe và xem xe trên bản đồ.
- Khi pose cũ, giữ vị trí nhận cuối và đánh dấu mất dữ liệu.

## 5. Giám sát dây chuyền và tay máy

- Bốn băng chuyền: tên tuyến, chạy/dừng, tốc độ danh định và số thùng ra.
- Tám Comau N220: chờ thùng, gắp, chuyển, đặt, về tư thế chờ và số chu kỳ hoàn tất.
- Tổng chu kỳ tay máy, tổng thùng ra và thời gian vật lý của runtime.
- Đồ thị sản lượng theo thời gian, dùng các mẫu telemetry trong phiên web.
- Hiển thị chuyển động thùng và khớp tay trên kho 3D khi runtime gửi đủ telemetry.

## 6. Nhật ký, cảnh báo và phân tích

- Nhật ký nhập hàng, tạo/hủy đơn, ghép xe, nhận/giao hàng và đối soát.
- Ghi nhận thay đổi phiên điều phối, chuyến thiếu sự kiện và các hoạt động liên quan.
- Lọc nhật ký theo hành trình, đơn vận chuyển, hàng hóa hoặc hệ thống.
- Hiện tình trạng kết nối điều phối AGV, runtime nhà máy, telemetry sản xuất và clock.
- Cảnh báo mất/chậm dữ liệu pose/lidar, thiếu telemetry, lỗi ROS, hold/fault từ điều phối và tồn thấp.
- Hiện đồng hồ mô phỏng và hệ số tốc độ mô phỏng so với thời gian thực (RTF).
- Nút **Phân tích** đưa nhận xét theo quy tắc về RTF thấp, đơn chờ, xe thiếu dữ
  liệu và thiếu telemetry; chưa dùng mô hình AI/LLM.

## 7. Cập nhật và lưu dữ liệu

- Web nhận snapshot tự động mỗi khoảng 250 ms qua SSE; nguồn ROS có tần số riêng.
- Dữ liệu quá 3 giây thực được đánh dấu không còn mới; không tự bịa vị trí/sản lượng.
- Khi SSE mất kết nối, trình duyệt tự thử nối lại.
- Khi 3D không khởi tạo được, chuyển về 2D và báo lỗi riêng, vẫn xử lý bản tin hợp lệ.
- SQLite lưu SKU, tồn kho, đơn và nhật ký qua các lần khởi động lại web.
- Pose, vệt xe, bản đồ nhiệt và biểu đồ sản lượng là dữ liệu phiên trong bộ nhớ.
- Chế độ **Live** đọc ROS thật; **Demo** có nhãn riêng, dùng dữ liệu giả lập và
  database tạm, không ghi vào tồn kho vận hành.
- Giao diện thích ứng với màn hình nhỏ.

Danh sách đơn hiển thị/xuất tối đa **500 chuyến gần nhất**; nhật ký tổng quan
đọc **150 sự kiện gần nhất**. Database vẫn giữ dữ liệu cũ và chi tiết sự kiện từng đơn.

## Phạm vi chưa có

- Đăng nhập, phân quyền, vận hành nhiều người dùng qua Internet.
- Điều khiển xe/tay máy/băng chuyền từ web; đổi tuyến hoặc thuật toán APF.
- Video camera trực tiếp từ Isaac: ô camera hiện là góc nhìn mô hình 3D web.
- Quét barcode/RFID, nhận dạng hàng từ ảnh, gắn từng mesh thùng USD với SKU.
- Đo pin, tải trọng thực, kiểm đếm tồn kho vật lý tự động.
- Kết nối PLC, cảm biến nhà máy thật, WMS/ERP bên ngoài.
- Dự báo tắc nghẽn, tối ưu tuyến bằng AI hoặc mô phỏng What-if trên web.

Nguồn đối chiếu: `web/public/index.html`, `app.js`, `twin3d.js`,
`web/model.py`, `ros_source.py`, `server.py`, `demo_source.py`.
Xem [hướng dẫn chạy và kiểm chứng](WEB_DASHBOARD.md) để biết chi tiết kỹ thuật.
