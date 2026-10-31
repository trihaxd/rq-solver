# Những thay đổi so với ZIP gốc của lần chỉnh sửa này

- `rq_solver.py`: `tol == 0` tắt early stopping (B2 và B1); thông báo chạy đúng max_iter; giữ nguyên công thức.
- `webapp.py`: thêm tolerance `0`, `1e-2`, GUI default `1e-2`; trả về `steps_by_iteration[0:3]`; thêm endpoint `POST /api/export-xlsx`.
- `solve_steps.py`: default tolerance `1e-2`, thêm `--excel`, trình bày chi tiết tối đa ba vòng đầu và summary từ iteration 3 trở đi; diễn đạt đúng `tol=0`.
- `steps.py` và `derive.py`: định dạng kết quả bằng 3 số thập phân, KHÔNG làm tròn trong phép tính số học của solver.
- `report.py`: bảng summary và CSV/TXT theo 3 số thập phân.
- `web/index.html`, `web/app.js`, `web/app.css`: nút Excel; chi tiết iterations 0,1,2; form tolerance và kết quả 3 số thập phân.
- **Mới:** `excel_export.py`: Excel đầy đủ lịch sử và từng bước 0–2.
- `test_midterm_review.py`: bổ sung regression tests.
- `README_MIDTERM.md`: viết lại toàn diện bằng tiếng Việt cho người chưa biết lập trình.
- `requirements.txt`: thêm thư viện dùng xuất Excel.

Tất cả các vòng lặp vẫn được tính với độ chính xác số của Python; thay đổi số chữ số chỉ ảnh hưởng trình bày.

## Điều chỉnh theo phản hồi tiếp theo

- `solve_steps.py`: lệnh giải vẫn chạy tới tolerance/cap; phần tính chi tiết tối đa 0,1,2; **bảng CLI hiển thị toàn bộ iteration 0..last**, kể cả những vòng đã giải thích.
- `web/index.html`: ghi rõ giới hạn trình bày không giới hạn solver; bảng GUI chứa toàn bộ lịch sử.
- `excel_export.py`: loại bỏ ba hàng `Converged`, `Note`, `Precision` khỏi sheet `Guide` trong đường xuất chính; bản fallback cũng không thêm các hàng giải thích tương tự.
- `README_MIDTERM.md`: sửa ví dụ mặc định để chạy tới hội tụ hoặc cap; giải thích độc lập giữa số vòng tính và số vòng trình bày.

## Xuất Excel trực tiếp vào thư mục run (bản sửa tiếp theo)

- `webapp.py`: POST `/api/export-xlsx` hiện **ghi file** qua `save_payload()` vào đường dẫn tuyệt đối `Path(__file__).resolve().parent / 'rq_iteration_results.xlsx'`, sau đó trả JSON xác nhận `saved_to`. Không còn gửi dữ liệu dạng browser attachment (WebView2 có thể bỏ qua download).
- `web/index.html`: đổi nút thành **Save Excel in run (.xlsx)**, bổ sung thông báo đường dẫn lưu ngay dưới nút.
- `web/app.js`: nhận JSON xác nhận lưu thành công/thất bại và hiển thị đường dẫn; không tạo blob hay download qua browser.
- `web/app.css`: định dạng thông báo; `README_MIDTERM.md` hướng dẫn tìm file trong folder `run`.
- Workbook cùng tên được **ghi đè** khi bấm Save nhiều lần. Thuật toán, tolerance, cap iteration, bảng summary và chi tiết 0–2 **không thay đổi**.
