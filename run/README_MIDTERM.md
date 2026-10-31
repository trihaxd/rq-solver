# INVENTORY MIDTERM — HƯỚNG DẪN TỪ SỐ 0

**Chủ đề:** Mô hình quản lý tồn kho `(s, Q)` hay `(r, Q)`, nhu cầu ngẫu nhiên (*stochastic demand*), **lead time không đổi**, giải bằng thuật toán lặp.  
**Hai thành phẩm chính:** chương trình Python trong terminal + giao diện người dùng GUI. **Cả hai gọi chung thuật toán `solve_rq()` trong `rq_solver.py`.**

> Hướng dẫn này dành cho người chưa biết mô hình tồn kho hoặc Python. Thực hiện các lệnh trong **thư mục `run`** có chứa `solve_steps.py`.
>
> **QUAN TRỌNG:** Trong GUI, nhấn **Save Excel in run (.xlsx)** sẽ tạo/cập nhật **`run/rq_iteration_results.xlsx`**; giao diện hiện đường dẫn đầy đủ. Không cần tìm trong Downloads. Sau khi cập nhật code, **đóng ứng dụng cũ và khởi chạy lại** để chạy bản mới.

---

## 1. Chương trình giải bài toán gì?

Giả sử cửa hàng không biết chắc nhu cầu khách sẽ đến bao nhiêu trong thời gian giao hàng. Cửa hàng cần chọn:

- **`Q` — order quantity:** mỗi lần đặt thêm bao nhiêu sản phẩm?
- **`r` hoặc `s` — reorder point:** khi **inventory position** giảm đến ngưỡng nào phải đặt hàng?
- **Inventory position (IP):** `hàng đang có + hàng đang đặt − đơn hàng chưa giao (backorders)`; KHÔNG chỉ là hàng đang có.
- **`L` — lead time:** khoảng thời gian cố định từ khi đặt tới khi được giao hàng.

Dữ liệu mô hình gồm nhu cầu `D`, chi phí đặt một lần `A`, chi phí lưu kho `h`, chi phí thiếu hàng `p` (B2), phân phối của nhu cầu trong lead time `X`, và tùy chọn đơn giá `v`.

Mục tiêu của chính sách B2 là giảm tổng chi phí gần đúng mỗi kỳ:

`Y(Q,r) = h[Q/2 + r − θ] + A·D/Q + p·D·n(r)/Q + D·v`

Trong đó **θ = E[X]**, `G(r) = P(X ≤ r)`, và `n(r) = E[max(X − r, 0)]` — lượng thiếu hụt kỳ vọng mỗi chu kỳ.

### Quy trình thuật toán B2 (quan trọng nhất cho midterm)

1. Tính `EOQ = sqrt(2·A·D/h)` rồi đặt `Q0 = EOQ`.
2. Ở vòng `t`, tính xác suất phía trên reorder point: `1 − G(r_t) = Q_t·h/(p·D)`.
3. Dùng phân phối nhu cầu để tìm `r_t` từ `G(r_t)`.
4. Tính expected shortage `n(r_t)` theo phân phối tương ứng.
5. Cập nhật `Q_(t+1) = sqrt(2·D·[A + p·n(r_t)]/h)`.
6. Lặp cho đến khi đạt tolerance **hoặc** đủ `Iteration cap`.

**Cách đếm:** Iteration 0: `Q0 → r0 → n(r0) → Q1`. Iteration 1: `Q1 → r1 → n(r1) → Q2`. Iteration 2: `Q2 → r2 → n(r2) → Q3`.

Nếu dừng **sau đúng 3 vòng** thì **đáp án báo cáo là `(Q3, r2)`**, không phải `(Q2, r2)`. Nghiệm sau 3 vòng là *kết quả dừng sớm*; chưa chắc đã hội tụ.

Các chế độ B1 (phí một lần stockout), α/β service level, periodic `(R,S)` cũng có sẵn để tham khảo nhưng **không phải thay thế thuật toán B2**.

---

## 2. Cài đặt một lần trên Windows / VS Code

1. Giải nén ZIP. Mở Visual Studio Code → **File → Open Folder** → chọn thư mục **`run`**.
2. Cài Python phiên bản 3.10 trở lên. Chạy `python --version` trong Terminal của VS Code.
3. Tạo môi trường ảo (khuyên dùng):

```powershell
python -m venv .venv
.\.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

4. Nếu gõ `python` không được, thử lệnh `py` thay cho `python` (Windows).
5. **Không cần cài thư viện Excel riêng:** exporter ưu tiên `artifact_tool` nếu có và tự động dùng **Python standard-library XLSX fallback** nếu không có. Bản fallback vẫn xuất được tệp `.xlsx`, tất cả vòng lặp và số thực đầy đủ, nhưng kiểu trình bày đơn giản hơn. Nếu môi trường của bạn hỗ trợ, có thể cài `artifact_tool_v2` riêng để xuất bản định dạng đẹp hơn.
6. `pywebview` là tùy chọn cho cửa sổ app kiểu desktop. **Chạy trong trình duyệt không cần pywebview.**

**Thư mục lúc chạy:** tất cả file `.py` và folder `web` phải nằm chung trong `run`. Không mở đơn lẻ file HTML bằng `file://` vì GUI phải gọi API `/api/solve`.

---

## 3. CÁCH A — chạy code giải trực tiếp (Terminal)

Từ terminal của thư mục `run`:

```powershell
# Homework Problem 1: chạy cho đến hội tụ HOẶC tối đa 200 vòng.
# Chỉ diễn giải chi tiết tối đa các vòng 0, 1, 2; bảng tóm tắt có ĐỦ mọi vòng.
python solve_steps.py -p hw1 --tol 1e-2 --max-iter 200 --no-pause

# Cùng cách chạy trên nhưng xuất thêm Excel với tất cả iterations
python solve_steps.py -p hw1 --tol 1e-2 --max-iter 200 --no-pause --excel results_hw1.xlsx

# CHỈ KHI cần chạy ĐÚNG 3 vòng cho phần bài tập yêu cầu 0,1,2:
python solve_steps.py -p hw1 --tol 0 --max-iter 3 --no-pause

# Homework Problem 2
python solve_steps.py -p hw2 --tol 1e-2 --no-pause --excel results_hw2.xlsx

# Nhập dữ liệu mới từng bước
python solve_steps.py -p new

# Chạy bộ test
python -m unittest -v test_midterm_review.py
```

Thêm `--no-color` để bỏ màu, `--ascii` nếu font terminal không hiển thị được ký tự toán học. Bỏ `--no-pause` để có thể bấm Enter đọc từng bước. Chỉ dùng `-p hw1`, `-p hw2` khi muốn nạp mẫu sẵn; `-p new` để tự nhập.

**Terminal trình bày:** Chuyển đổi đầu vào → mô hình/công thức → **chi tiết iteration 0, 1, 2 (nếu có)** → **bảng tóm tắt TẤT CẢ iterations (0, 1, 2, 3, …)** → đáp án → kiểm tra → chi phí. Bất kỳ vòng nào cũng được lưu trong Excel nếu chọn `--excel`.

**PHÂN BIỆT:** `--max-iter 200` là giới hạn vòng **tính toán**, không phải giới hạn vòng **trình bày chi tiết**. Kể cả khi bài toán hội tụ sau 5, 8 hoặc 15 vòng thì vẫn chỉ mở rộng phép thế số của tối đa 3 vòng đầu, còn bảng summary cho đầy đủ 5, 8 hoặc 15 hàng. Không cần (và không nên) đặt `--max-iter 3` chỉ vì bạn muốn thấy ba vòng giải chi tiết.

### Ý nghĩa `--tol` và `--max-iter`

| `--tol` | Ý nghĩa | Khi dùng |
|---|---|---|
| `0` | **Không dừng sớm theo tolerance**. Chạy đúng số vòng trong `--max-iter` (trừ trường hợp bài toán vô nghiệm, single-pass hoặc mô hình không cần lặp). | Tái hiện 3 vòng đề bài: `--tol 0 --max-iter 3`. |
| `1e-2` | Sai số ngưỡng `0.01` theo **cả `r` và `Q`** (theo điều kiện dừng hiện có của solver). | Dừng sớm, ít vòng hơn. Mặc định ở GUI/terminal. |
| `1e-4`, `1e-8` | Sai số nhỏ hơn → yêu cầu chính xác hơn, thường nhiều vòng hơn. | Khi cần kiểm tra hội tụ kỹ. |

**Rất quan trọng:** tolerance **không phải** số chữ số thập phân. Chương trình luôn tính với số thực đầy đủ và **chỉ làm tròn khi hiển thị thành 3 số sau dấu phẩy**. Một cột thay đổi có thể hiện `0.000` nhưng sai số thực vẫn khác 0.

**Khi `tol=0`, chương trình đánh dấu `converged=False` để diễn đạt rằng đã chạy đủ số vòng yêu cầu, chứ không tự khẳng định đã hội tụ.**

---

## 4. CÁCH B — chạy giao diện người dùng GUI

Từ thư mục `run`:

```powershell
python app_desktop.py --browser
```

Trình duyệt mở trang trên `http://127.0.0.1:<port>` (port hiển thị trong terminal). Giữ terminal chạy khi đang sử dụng; đóng bằng `Ctrl+C`.

Muốn cửa sổ ứng dụng riêng: `python app_desktop.py` (cần `pywebview`, có thể cần Microsoft WebView2 trên Windows).

### Thao tác GUI theo thứ tự

1. **Homework problems** → chọn mẫu `hw1` hoặc `hw2` → **Load this problem**. Hoặc nhập thông số tùy chỉnh trong form.
2. Kiểm tra đơn vị `base time unit` (year/week), `lead-time unit`, `Demand`, `A`, `h`, `p`, phân phối Normal/Uniform/Exponential/Poisson và các tham số.
3. Ở **Method** chọn `Stopping tolerance`: `0 (fixed iteration count)`, `1e−2`, `1e−4`, v.v.; điền `Iteration cap`.
4. Ví dụ đúng 3 vòng: chọn `0` và `3`. Nếu muốn dừng sớm, chọn `1e−2` và `200`.
5. Bấm **Solve**. Trang hiện kết luận, đồ thị hội tụ, bảng iterations, summary/cost.
6. Trong **The iteration**: trình bày đầy đủ phép thế số của `Iteration 0`, `Iteration 1`, `Iteration 2` (nếu có). **Bảng bên dưới bao gồm TẤT CẢ các vòng kể cả t ≥ 3**.
7. Bấm **Save Excel in run (.xlsx)**. Chương trình **tự ghi file `rq_iteration_results.xlsx` trực tiếp vào thư mục `run`** (cùng chỗ với `webapp.py`, `app_desktop.py`), KHÔNG cần tìm trong Downloads. Ngay dưới nút sẽ hiện **đường dẫn đầy đủ** đến file vừa lưu. Ví dụ `D:\Inventory\run\rq_iteration_results.xlsx`. Mỗi lần nhấn, file cũ sẽ được **ghi đè bằng kết quả hiện tại** (đóng Excel trước khi xuất lại). Nút **Table as CSV** vẫn tải CSV qua trình duyệt; **Full working** vẫn tải TXT.

**Nếu chọn `0` và cap = 3**: GUI và Terminal dùng cùng solver, cho cùng các giá trị `Q3` và `r2` trước khi làm tròn.

---

## 5. FILE EXCEL XUẤT RA CÓ GÌ?

`excel_export.py` là bộ xuất chung của terminal lẫn GUI. Workbook gồm các sheet:

| Worksheet | Nội dung |
|---|---|
| `Guide` | Method, tolerance, iteration cap, số vòng thực hiện, cách đếm iteration và kết quả cuối. Không có ba dòng `Converged`, `Note`, `Precision`. |
| `Answer` | Q, r, safety stock, EOQ, fill rate, số lần đặt… |
| `Inputs` | Dữ liệu sau chuyển đổi đơn vị. |
| **`Iterations`** | **TẤT CẢ các iteration**, gồm `t, Q_t, 1-G(r_t), G(r_t), r_t, n(r_t), Q_(t+1), |Δr|`. |
| **`Worked 0-2`** | **Công thức và cách thay số từng bước** cho tối đa 3 vòng `t=0,1,2`. |
| `Costs` | Holding, ordering, shortage và purchase costs. |
| `Periodic policy`, `Comparison` | Chỉ xuất thêm khi có bài yêu cầu so sánh chính sách (R,S). |

Các ô số trong sheet `Iterations` lưu **đúng số thực chưa làm tròn**; Excel định dạng hiển thị `0.000`. Đừng làm tròn ngay trong công thức vì sẽ tích lũy sai số giữa các vòng.

---

## 6. SƠ ĐỒ LIÊN KẾT CÁC FILE

```text
                         Người sử dụng
                               |
                  +------------+------------+
                  |                         |
          solve_steps.py             app_desktop.py
          (terminal)                  (mở GUI)
                  |                         |
                  |                     webapp.py
                  |                    HTTP /api/*
                  |                         |
                  |                 web/index.html
                  |                 web/app.js
                  |                 web/app.css
                  |                         |
                  +------------+------------+
                               |
                        derive.py
                        timeunits.py
                               |
                        rq_solver.py
                     (CÔNG THỨC, VÒNG LẶP)
                               |
                    +----------+----------+
                    |          |          |
                 steps.py   report.py  excel_export.py
                (giải thích) (bảng/TXT)   (XLSX)
```

### Từng file có nhiệm vụ gì, cấu trúc ra sao?

**1. `rq_solver.py` — BỘ NÃO tính toán (nên đọc sau khi hiểu mô hình).**
- `Distribution`, `Normal`, `Uniform`, `Exponential`, `Poisson`: mô tả phân phối nhu cầu; CDF, phân vị và expected loss.
- `Inputs`: dữ liệu đầu vào đã chuẩn hóa; `Iteration`: một hàng lịch sử lặp; `Result`: kết quả và chi phí.
- **`solve_rq(inputs, tol, max_iter, single_pass)`**: bắt đầu từ EOQ; trong `for` tính xác suất → `r` → `n(r)` → `Q_next`; thêm record vào `iterations`; kiểm tra điều kiện dừng. **Mới:** khi `tol == 0` bỏ qua điều kiện dừng sớm.
- `_solve_b1()` và `_solve_service()`: các biến thể B1, α, β; `solve_periodic()` / `compare_policies()`: phần so sánh `(R,S)` tùy chọn.
- **Không sửa công thức toán để giảm số vòng.** Tolerance chỉ thay đổi điểm dừng.

**2. `derive.py` — chuẩn hóa dữ liệu Homework trước khi giải.**
- `_holding()`: tính holding cost từ tỷ lệ carrying charge × unit cost.
- `_demand()`, `_demand_scaled()`, `_period_span()`: đổi nhu cầu theo tuần/tháng/năm thành phân phối nhu cầu trong lead time.
- `_penalty()`: tính penalty từ dữ liệu đầu bài khi có.
- `derive()`: gom các bước biến đổi để terminal và GUI dùng chung.

**3. `timeunits.py` — quy đổi đơn vị thời gian.** Hàm `convert(value, source, target)` đổi week/month/year, `unit_label()` viết tên đơn vị.

**4. `steps.py` — soạn lời giải từng bước, KHÔNG giải lại bài toán.**
- `pass_steps(inputs, iteration)`: dựng từng dòng công thức và số thế cho **bất kỳ iteration nào**.
- `_opening`, `_tail`, `_cdf`, `_normal` / `_uniform` / `_exponential` / `_discrete`, `_next_q`, `_movement`: các phép tính trong một vòng.
- Kết quả gồm `label`, `tex` (hiển thị đẹp trên GUI), `plain` (hiển thị terminal / Excel).

**5. `report.py` — tạo bảng kết quả.**
- `summary_rows()`, `iteration_rows()`, `cost_rows()`: dữ liệu hiển thị trong cả hai giao diện.
- `fmt()`: làm tròn số khi HIỂN THỊ, hiện thống nhất **3 decimal places**.
- `to_csv()`, `to_text()`: hai dạng xuất cũ vẫn giữ.

**6. `solve_steps.py` — entry point CLI, bài giải in ra VS Code.**
- `main()`: đọc các lựa chọn dòng lệnh `-p`, `--tol`, `--max-iter`, `--excel`.
- `spec_for()` / `build()`: lấy mẫu homework hoặc dữ liệu tự nhập.
- **`walk()`**: điều phối mọi phần: input → mô hình → vòng lặp → nghiệm → chi phí → xuất Excel.
- `show_iteration_table()`: **luôn** đưa tất cả iterations (0,1,2,…,vòng cuối) vào bảng tóm tắt, dù ba vòng đầu đã được giải thích riêng hoặc người dùng nhấn `s` để bỏ qua diễn giải.
- `Console`: trình bày màu sắc và chế độ bấm Enter.

**7. `app_desktop.py` — mở GUI.**
- `main()` đọc `--browser` / `--port`.
- `launch()` bật local web server của `webapp.py`, mở trình duyệt hoặc desktop window.
- **Không chứa công thức tính Q/r.**

**8. `webapp.py` — bộ trung gian giữa GUI và solver.**
- `meta_payload()` trả về danh sách lựa chọn: phân phối, bài mẫu, tolerance (có **0** và **1e-2**).
- `solve_payload()` đọc JSON, kiểm tra đầu vào, gọi `derive()` rồi **`solve_rq()`**, trả về summary + **`steps_by_iteration` cho tối đa 3 vòng** + tất cả lịch sử.
- `Handler` nhận `POST /api/solve`, `POST /api/export-xlsx` (tạo và **lưu Excel trực tiếp vào `run`**) và `GET /api/meta`. Giá trị `EXCEL_OUTPUT` chỉ đến vị trí lưu cố định.

**9. `web/index.html` — bố cục màn hình.** Form nhập đầu vào, phần Method, các tabs, bảng iteration và nút **Save Excel in run**.

**10. `web/app.js` — tương tác GUI.**
- `buildSelects()` tạo lựa chọn tolerance và phân phối.
- `readForm()` gom dữ liệu người dùng; `solve()` gửi `/api/solve` và nhận kết quả.
- **`renderSteps()`** hiển thị `steps_by_iteration` của 3 vòng đầu.
- `renderTrace()` hiển thị **mọi hàng iteration**, `renderChart()` vẽ convergence chart.
- Click **`dlXlsx`** gửi `/api/export-xlsx`; Python server lưu workbook vào `run/rq_iteration_results.xlsx` và trả đường dẫn đầy đủ (không download qua trình duyệt).
- `num()` / `trim()` hiển thị **3 decimal places**, không thay đổi số liệu gốc.

**11. `web/app.css` — thiết kế giao diện.** Màu sắc, font, bố cục responsive và đề mục cho từng iteration; không tính toán.

**12. `excel_export.py` — tạo Excel thực thụ.**
- `create_workbook(payload)`: tạo các worksheets từ dữ liệu trả về.
- `export_bytes(payload)`: tạo byte XLSX để gửi qua web.
- `save_payload(payload, filename)`: ghi file thật ra ổ đĩa; **được dùng chung cho terminal và nút Save Excel của GUI**.

**13. `test_midterm_review.py` — kiểm thử hồi quy.** Chạy `python -m unittest -v test_midterm_review.py`; kiểm tra đáp án, số vòng, tolerance 0/1e-2, kết quả GUI so với solver và file XLSX.

**14. `requirements.txt` — dependency tùy chọn.** Excel có chế độ xuất không cần thư viện bổ sung; desktop window cần `pywebview`; browser và thuật toán chỉ dùng Python standard library.

### Nên đọc code theo thứ tự nào?

`README` → `solve_steps.py: main, walk` → `rq_solver.py: solve_rq` → `steps.py: pass_steps` → `report.py` → `excel_export.py` → `webapp.py: solve_payload` → `web/app.js: solve, renderSteps, renderTrace`.

---

## 7. CHECKLIST TRƯỚC KHI NỘP

- [ ] Terminal chạy được Homework 1 với **`--tol 0 --max-iter 3`**.
- [ ] Có **3 phần giải chi tiết** trong cả GUI và terminal: t=0,1,2.
- [ ] Đặt tolerance=0, cap=8: GUI **8 dòng summary**, terminal **8 dòng summary (t=0,…,7)**; cả hai chỉ mở rộng tối đa ba vòng 0,1,2.
- [ ] Chọn `1e-2` dừng nhanh hơn `1e-8` (tùy bài). Đừng tuyên bố đạt nghiệm y hệt khi dừng sớm.
- [ ] Nhấn **Save Excel in run**: file `run/rq_iteration_results.xlsx` tồn tại, giao diện thông báo đường dẫn; terminal vẫn tạo file với `--excel`.
- [ ] Worksheet `Iterations` có đúng bằng số vòng đã thực hiện và có đủ 8 cột.
- [ ] Các số **được trình bày 3 chữ số thập phân**, nhưng tính toán không bị làm tròn ở giữa.
- [ ] `python -m unittest -v test_midterm_review.py` chạy `OK`.

## 8. Lỗi thường gặp và cách xử lý

| Tình huống | Xử lý |
|---|---|
| `python: command not found` | Cài Python, mở lại terminal, hoặc dùng `py` trên Windows. |
| `No module named artifact_tool` | Exporter tự dùng chế độ dự phòng (không cần cài gì). Để có định dạng Excel phong phú hơn, cài `artifact_tool_v2` nếu môi trường cho phép. |
| `No module named webview` | Dùng `python app_desktop.py --browser`, hoặc cài `pywebview` để mở window riêng. |
| GUI trắng hoặc báo server không phản hồi | Chạy GUI qua `app_desktop.py --browser`, không double-click `web/index.html`. Kiểm tra server còn chạy. |
| Không đủ ba iteration | Chọn `tolerance = 0`, `Iteration cap = 3` và tắt `single-pass`. |
| `Converged = no` khi `tol = 0` | Bình thường: đây là **fixed iteration count**, không đánh giá hội tụ tự động. |
| Không thấy file Excel xuất từ GUI | Tìm ở **`run/rq_iteration_results.xlsx`**, không phải Downloads. Sau khi bấm nút, đọc đường dẫn hiển thị ngay dưới nút. |
| Thông báo không ghi được Excel | Đóng file Excel đang mở (Windows có thể khóa file), kiểm tra quyền ghi của thư mục `run`, sau đó bấm Save lại. |
| Excel hiển thị `0.000` cho delta rất nhỏ | Chỉ là làm tròn cách HIỂN THỊ; số thật lưu trong workbook vẫn chính xác hơn. |
| Không xuất được Excel ở dữ liệu cực lớn | Workbook hiện giới hạn 10.000 rows/sheet để tránh treo máy. Giảm iteration cap. |

**Giới hạn mô hình:** Thuật toán dựa trên chi phí tồn kho kỳ vọng gần đúng, lead time cố định, nhu cầu không chắc chắn. Không nên diễn giải tất cả kết quả B1/α/β như nghiệm B2. Các diễn giải đặc biệt của slide về Uniform có thể không nhất quán với D·L; hãy ghi rõ giả định khi báo cáo.

---

## LƯU Ý SAU KHI CHỈNH SỬA YÊU CẦU TRÌNH BÀY

- **Số vòng giải thực tế** do `solve_rq()` quyết định: nếu `tol > 0`, dừng khi cả `|r_t-r_(t-1)|` và `|Q_(t+1)-Q_t|` không vượt quá tolerance; nếu chưa hội tụ thì dừng ở `max_iter`. Nếu `tol=0`, luôn chạy hết cap (trừ trường hợp bất thường/single pass).
- **Phần worked calculations** chỉ mở rộng tối đa 3 iteration đầu (0, 1, 2) trong GUI, terminal và sheet `Worked 0-2`. Đây là giới hạn hiển thị, **KHÔNG ảnh hưởng phép tính**.
- **Bảng iterations** luôn liệt kê đủ **mọi vòng đã thực sự tính**, gồm cả 0, 1, 2 và tất cả vòng tiếp theo cho đến khi dừng. Excel sheet `Iterations` cũng vậy.
- **Sheet `Guide` trong Excel** đã bỏ các dòng `Converged`, `Note`, `Precision` theo yêu cầu.


## 9. VỊ TRÍ LƯU EXCEL TRONG GUI (CẬP NHẬT)

- **Save Excel in run (.xlsx)** = ghi thật xuống ổ đĩa, đường dẫn được xác định từ `Path(__file__).resolve().parent` trong `webapp.py`. Vì thế dù mở VS Code ở thư mục khác, file vẫn vào **`run`** bên cạnh code.
- Ví dụ folder của bạn là `D:\Master\INVENTORY\run`, file sẽ ở `D:\Master\INVENTORY\run\rq_iteration_results.xlsx`. Đọc đường dẫn **Saved Excel to: ...** ngay bên dưới nút để biết vị trí chính xác.
- Nhấn lần nữa sẽ **cập nhật (ghi đè)** file cùng tên với input/iteration hiện tại. Nếu Excel đang mở, hãy đóng workbook trước khi bấm Save.
- **Không cần** `Ctrl+J`, không cần tìm thư mục **Downloads**, không phụ thuộc WebView2.
- Nếu chạy `solve_steps.py` và truyền `--excel`, lệnh terminal vẫn lưu theo đường dẫn bạn chỉ định (không bị thay đổi).
- Để xuất kết quả **từng iteration**: vào sheet `Iterations` (tất cả các vòng); sheet `Worked 0-2` chỉ giải thích phép tính chi tiết của tối đa ba vòng đầu.
