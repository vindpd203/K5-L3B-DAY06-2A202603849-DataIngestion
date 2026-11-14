# Hướng dẫn chấm thủ công (GUIDE.md §4)

Sinh lại các file: `python -m src.run audit`. Lệnh từ chối chạy nếu file đã có nhãn (cột `annotator`); sao lưu rồi thêm `--force` để ghi đè.

**Trạng thái nhãn:** nhãn do **Phạm Đức Vinh** thực hiện ngày 2026-11-14 (đối chiếu với text OCR và ảnh PDF các trang liên quan; metadata kiểm bằng script so vị trí chunk với heading Điều, rồi xem lại bằng mắt 2 bản ghi lỗi; ghi nhận ở cột `annotator`). Tổng hợp nằm ở `audit_summary.json`. Mở bằng Excel (UTF-8 có BOM). Đối chiếu với PDF `data/raw/Thông-tư-91-2026-TT-BTC.pdf`, không chỉ với text OCR. Người chấm là tác giả, cần ghi nhận nguy cơ thiên lệch trong báo cáo.

## coherence.csv: 30 dòng (10 vị trí × A/B/C)
- Vị trí chọn theo quy tắc cố định trước khi xem điểm: trang 1–10, neo = 60 ký tự bắt đầu ở dòng đầu tiên sau giữa thân trang.
- C dùng cùng chunk với B, nên chép nhãn của B.
- `boundary_inside_anchor = True`: ranh giới chunk rơi trong đoạn neo (pos07/B).
- `score_0_1_2`: **0** = bị cắt giữa ý hoặc thiếu chủ thể nên không hiểu được; **1** = hiểu một phần, thiếu ngữ cảnh; **2** = tự hiểu được và giữ trọn ý. Ghi `reason` cho mọi dòng.

## metadata.csv: 45 dòng (5 câu test × top-3 × A/B/C)
- `source_ok`, `page_ok`, `chapter_ok`, `article_ok`: ghi `1`/`0`, so với PDF (trang trong `pages` có chứa text này không; Chương/Điều có đúng không).
- Bản ghi "đủ và đúng" khi cả 4 cột đều là 1. Báo n/45 theo từng chiến lược (n/15) và ghi từng lỗi vào `note`.
- Lỗi đã biết của A: `article`/`chapter` lấy theo vị trí đầu chunk, nên chunk bắt đầu trước heading Điều mới sẽ bị gắn Điều cũ.
- Tuân thủ filter (t04, `chapter=III`) đã tính tự động trong `metrics_test.json`.

## grounding.csv: 15 dòng (5 câu test × A/B/C)
- Đọc cả top-3 (`top3_text`) so với `expected_answer`. Chỉ đánh giá bằng chứng truy xuất, **không** phải độ chính xác câu trả lời LLM.
- `score_0_1_2`: **0** = không có bằng chứng; **1** = có nhưng thiếu điều kiện/ngữ cảnh cần thiết; **2** = đủ để trả lời và truy nguồn.
- `auto_evidence_hit_at_3` chỉ là proxy tự động, không thay nhãn thủ công. Có thể có bằng chứng tương đương ở chunk khác trang gold.
- Báo số câu ở mỗi mức 0/1/2 và trung bình /2 cho từng chiến lược, kèm lý do.
