# Benchmark — Thông tư 91/2026/TT-BTC (trang 1–32)

`questions.jsonl`: 20 câu, 15 dev / 5 test, chốt **trước khi chạy pipeline**. Không sửa tập test sau khi xem kết quả; nếu phải sửa, ghi lại ở đây và không coi là holdout độc lập.

Kiểm chứng evidence (mỗi quote phải nằm nguyên văn trên trang gold của text OCR, so khớp sau khi gộp khoảng trắng):

```bash
cd starter
python -m src.evaluation --verify ../benchmark/questions.jsonl results/pages_TT-91-2026.jsonl
```

## Trường và quy ước
- `gold_page`: số trang vật lý của PDF (1-based), là danh sách để chấp nhận nhiều trang hợp lệ.
- `evidence_quote`: chép nguyên văn từ text OCR, **giữ cả lỗi OCR** (vd. `tôi thiều`, `thành phân`) vì đây là text pipeline truy xuất. `expected_answer` viết đúng chính tả theo PDF gốc.
- `filter`: chỉ có ở câu `metadata_filter`; giá trị `chapter` là input giả định người dùng cung cấp trước khi truy xuất (xem `filter_context`), không suy ra từ gold.
- `type`: `truc_tiep`, `dien_dat_lai`, `dieu_kien`, `ngoai_le`, `metadata_filter`.

## Chương → trang (nguồn giá trị cho trường lọc `chapter`)
| Chương | Nội dung | Trang | Điều |
|---|---|---|---|
| I | Quy định chung | 1–2 | 1–2 |
| II | Hóa đơn điện tử | 3–28 | 3–16 |
| III | Chứng từ điện tử | 28–30 | 17–20 |
| IV | Tra cứu, cung cấp thông tin hóa đơn | 30–31 | 21–23 |
| V | Điều khoản thi hành | 32 | 24–25 |

Heading OCR bị sai (`Chương H` = II, `Chương HỊ` = III); khi gắn metadata cần map thủ công theo bảng trên.

## Cách chia dev/test và nguy cơ rò rỉ
- Chia theo **Điều**: test lấy từ Điều 7, 13, 18, 22, 25; dev dùng Điều 3, 4, 5, 6, 8, 9, 10, 12, 20. Không Điều nào xuất hiện ở cả hai tập.
- Rò rỉ còn lại: t04 (Điều 18, định dạng chứng từ) gần giống d01 (Điều 3, định dạng hóa đơn); t01 (Điều 7) được Điều 6 và 8 dẫn chiếu. Chỉnh tham số trên dev có thể gián tiếp có lợi cho các câu này.
- Câu filter: d10 (Ch. II) và d15 (Ch. III) là cặp nội dung gần giống nhau (xử lý khi lập sai); t04 (Ch. III) có bản gần giống ở Ch. II. Đây là nơi filter thực sự cần để phân biệt.

## Tiêu chí chọn chiến lược (chốt trước khi xem test)
1. Evidence Hit@3 trên **dev** cao nhất.
2. Hòa thì xét Hit@1 trên dev, rồi điểm grounding thủ công.
3. Vẫn hòa thì chọn cấu hình ít chunk / ingest nhanh hơn.

Test chỉ chạy **một lần** sau khi đã cố định cấu hình theo tiêu chí trên.

## Ghi chú về cách tạo
Câu hỏi và evidence do **Phạm Đức Vinh** biên soạn và trích xuất từ text OCR ngày 14/11/2026; evidence được kiểm tra tự động bằng lệnh trên.

Đối chiếu với PDF gốc (`data/raw/Thông-tư-91-2026-TT-BTC.pdf`, render ảnh 16 trang gold), **trước khi chạy pipeline**, ngày 14/11/2026:
- 18/20 câu: đáp án, trang và điều kiện khớp PDF.
- t05: sửa trước khi chạy. Bản đầu hỏi văn bản nào hết hiệu lực nhưng evidence chỉ có nửa đầu câu, không chứa "hết hiệu lực thi hành". Đổi sang hỏi ngày hiệu lực (Điều 25 khoản 1), evidence đầy đủ.
- t01: giữ nguyên, thêm `note`: câu dẫn "có một trong những dấu hiệu sau" của Điều 7 nằm ở trang 10, evidence ở trang 11.
- Người biên soạn bộ câu hỏi và người chấm thủ công là tác giả (Phạm Đức Vinh), có nguy cơ thiên lệch.
