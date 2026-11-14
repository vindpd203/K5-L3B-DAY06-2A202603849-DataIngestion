# Báo cáo cá nhân — Day 6

**Học viên:** Phạm Đức Vinh · **MSSV:** 2A202603849 · **Lớp:** L3B · **Ngày:** 2026-11-14

## Dữ liệu và pipeline

- **Chủ đề, nguồn/quyền, số trang và quy tắc tính trang:** Hóa đơn điện tử, chứng từ điện tử. Corpus là một văn bản: Thông tư 91/2026/TT-BTC của Bộ Tài chính (ban hành 30/06/2026, hiệu lực 01/07/2026, còn hiệu lực khi truy cập 14/11/2026), tải từ vbpl.vn. Đây là văn bản quy phạm pháp luật công khai, không chứa dữ liệu cá nhân; điều khoản riêng của vbpl.vn chưa được kiểm tra. PDF có 97 trang vật lý, toàn bộ là bản scan. Tính **trang 1–32** (thân văn bản, Chương I–V, Điều 1–25) = **32 trang nội dung**, 72.408 ký tự sau OCR. Loại trang 33 (nơi nhận, chữ ký) và 34–97 (phụ lục biểu mẫu, OCR nhiễu). Chi tiết từng trang trong `data/manifest.yaml`. Trước khi chọn, đã kiểm tra và loại Nghị định 123/2020, Thông tư 78/2021 và 32/2025 vì đã hết hiệu lực.
- **Chuẩn hóa, lỗi và giới hạn:** pypdf không trích được chữ ở trang nào, nên OCR bằng Tesseract 5.4 (`vie`, 300 dpi, psm 6), render trang bằng PyMuPDF. OCR mất 249 giây cho 97 trang. Bản Tesseract đi kèm PyMuPDF bị loại vì làm mất dấu cách sau chữ có dấu. Chuẩn hóa Unicode NFC, gộp khoảng trắng, giữ xuống dòng. Lỗi OCR còn lại: sai dấu (`thuê`/`thuế`, `tô chức`), số nhận thành ký hiệu (`khoản §`), heading chương đọc sai (`Chương H` = II). Evidence trong benchmark được chép nguyên văn từ text OCR, kể cả lỗi.
- **Embedding, vector store, metric, lệnh chạy và chi phí:** `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` chạy local (sentence-transformers 6.3.0, torch 2.15.0+cpu), 384 chiều, chuẩn hóa L2, query và document xử lý giống nhau. Giới hạn đầu vào là 128 token. PostgreSQL 16.16 + pgvector 0.8.7 (Docker), metric cosine, **exact search** (không dùng index ANN). Chi phí: 0. Lệnh chạy ghi trong `README.md`.
- **Kiểm tra nạp lại:** hai lần ingest liên tiếp (2026-11-14 03:34 và 03:35) cùng ghi 173 chunk A và 98 chunk B, `rows_in_db` bằng số chunk ở cả hai lần, không nhân đôi (`starter/results/ingest_log.jsonl`). Lần ingest 03:39 với cấu hình cuối (A 235, B 275) xóa 95 dòng B cũ của phiên bản 1000 ký tự (`deleted_obsolete = 95`).
- **Metadata bắt buộc, trường lọc, nguồn giá trị và lý do chọn:** mỗi chunk có `document_id`, `source` (tên file PDF), `page` (trang vật lý 1-based), `pages` (các trang mà chunk trải qua). Trường lọc là `chapter` (text, I–V), cùng `article` (số nguyên). Giá trị `chapter` suy ra từ số Điều theo bảng Chương → Điều đã đối chiếu trên PDF, không đọc từ heading OCR vì OCR đọc sai. Chọn `chapter` vì văn bản có nội dung gần trùng giữa Chương II (hóa đơn) và Chương III (chứng từ), ví dụ cùng có quy định về định dạng XML và xử lý khi lập sai.

## Cấu hình và benchmark

- **A / B / C:**
  - **A:** cửa sổ ký tự cố định 360, overlap 36, trong từng trang. `article`/`chapter` lấy theo vị trí đầu chunk. 235 chunk.
  - **B:** gom các đoạn trong cùng một Điều, tối đa 360 ký tự, không vượt ranh giới Điều. Đoạn bị ngắt trang được nối lại. Câu quá dài được cắt ở `.`/`;`/`:`, cắt cứng nếu vẫn quá dài. 275 chunk, 34 chunk trải qua 2 trang.
  - **C:** dùng chunk của B, thêm `WHERE chapter = <giá trị filter>` **chỉ cho câu có filter**. Khác biệt duy nhất giữa B và C là filter.
  - Kích thước 360 là mức lớn nhất mà không chunk nào vượt 128 token. Phiên bản đầu dùng A 500/50 và B 1000, khi đó 98/173 chunk A và 85/98 chunk B bị cắt khi embed (phát hiện qua câu dev d10: evidence bắt đầu ở token 138). Đã đổi trước khi chạy câu test nào.
- **≥20 câu, phân chia, câu filter và cách kiểm chứng evidence:** 20 câu, 15 dev / 5 test, chia theo Điều (test lấy từ Điều 7, 13, 18, 22, 25, không trùng Điều với dev). Có 3 câu filter: d10 (`chapter=II`), d15 và t04 (`chapter=III`). Giá trị filter là input giả định người dùng cung cấp trước khi truy xuất. Loại câu: trực tiếp, diễn đạt lại, điều kiện, ngoại lệ, metadata_filter. Evidence được kiểm tự động (`src.evaluation --verify`, 20/20 nằm đúng trang) và đối chiếu bằng mắt với ảnh 16 trang gold của PDF. Kết quả đối chiếu: t05 được sửa trước khi chạy (evidence ban đầu không đủ chứng minh đáp án); t01 được ghi chú là ngữ cảnh nằm ở trang khác. Rò rỉ còn lại: t04 gần giống d01.
- **Tiêu chí chọn chiến lược đã chốt trước khi xem test:** (1) Evidence Hit@3 dev, (2) Hit@1 dev, (3) grounding thủ công, (4) tài nguyên. Test chỉ chạy một lần, sau khi đã ghi `results/selection.json`.

## Kết quả

| Strategy | Split | Hit@1 (n/N) | Evidence Hit@3 (n/N) | Chunk count | Thời gian | Chi phí |
|---|---|---|---|---|---|---|
| A | dev | 6/15 | 8/15 | 235 | embed 6,74 s + ghi DB 0,13 s | 0 |
| B | dev | 1/15 | 7/15 | 275 | embed 6,16 s + ghi DB 0,15 s | 0 |
| C | dev | 2/15 | 8/15 | 275 (dùng của B) | như B | 0 |
| A | test | 2/5 | 2/5 | 235 | tìm kiếm trung vị 27,9 ms/câu (n=5) | 0 |
| B | test | 2/5 | 2/5 | 275 | tìm kiếm trung vị 22,2 ms/câu (n=5) | 0 |
| C | test | 2/5 | 2/5 | 275 | tìm kiếm trung vị 22,6 ms/câu (n=5) | 0 |

Thời gian chung: tải model 10,7 s; OCR 249 s (một lần cho cả 3 cấu hình); truy vấn trung vị 29 ms/câu (exact search, CPU).

| Strategy | Coherence trung bình /2 (n) | Metadata đủ và đúng (n/N) | Filter tuân thủ (n/N hoặc N/A) | Grounding 0/1/2 (số câu) và trung bình /2 |
|---|---|---|---|---|
| A | 0,7 (n=10; 0:3, 1:7, 2:0) | 13/15 | dev 0/2, test 0/1 | 3/0/2 — 0,8 |
| B | 1,3 (n=10; 0:2, 1:3, 2:5) | 15/15 | dev 1/2, test 0/1 | 3/0/2 — 0,8 |
| C | 1,3 (cùng chunk với B) | 15/15 | dev 2/2, test 1/1 | 3/0/2 — 0,8 |

**Đường dẫn trace, nhãn thủ công và cách chọn mẫu:** trace đầy đủ ở `starter/results/traces_dev.jsonl` và `traces_test.jsonl`; chỉ số ở `metrics_*.json`; nhãn ở `starter/results/audit/` (`coherence.csv`, `metadata.csv`, `grounding.csv`, `audit_summary.json`). Coherence: 10 vị trí cố định trước khi xem điểm (trang 1–10, mỗi trang lấy 60 ký tự từ dòng đầu tiên sau giữa trang). Metadata: 5 câu test × top-3 × 3 cấu hình = 45 bản ghi. Grounding: 5 câu test × 3 cấu hình. Metadata được kiểm bằng script so vị trí chunk với heading Điều, rồi xem lại bằng mắt các bản ghi lỗi trên PDF. **Người chấm:** Phạm Đức Vinh (tác giả). Người chấm biết kết quả tự động khi chấm, nên có nguy cơ thiên lệch.

## Phân tích và kết luận

- **So sánh A–B (không phải thay đúng một yếu tố):** B đổi đồng thời chunking, overlap (36 → 0) và cách gán `article`/`chapter` (theo vị trí đầu chunk → chính xác từng chunk). Kết quả A–B vì vậy là tác động tổng hợp của ba thay đổi, không cô lập được riêng chunking.
  - **Coherence:** B tốt hơn rõ (1,3 so với 0,7). A cắt giữa từ ở hầu hết vị trí. Ở pos06, A mất cụm "không thuộc trường hợp", nên đoạn đọc lên thành ngược nghĩa.
  - **Metadata:** B đúng 15/15, A 13/15. Hai lỗi của A là chunk vắt qua tiêu đề chương mới: t04 hạng 3 bị gắn Điều 2/Chương I thay vì Điều 3/Chương II; t05 hạng 2 bị gắn Điều 20/Chương III thay vì Điều 21/Chương IV.
  - **Truy xuất:** gần như hòa ở Hit@3 (dev 8 so với 7, test 2 so với 2), nhưng A hơn hẳn ở Hit@1 dev (6 so với 1). Trong 6 câu dev mà B xếp chunk đúng ở hạng 2–3, có 5 câu mà chunk hạng 1 là một khoản/điểm **cùng Điều**, điểm số chỉ chênh 0,005–0,08 (ví dụ d03, d13). B tìm đúng Điều nhưng tách Điều thành nhiều chunk ngắn tương tự nhau mà không có tiêu đề.
  - **Tài nguyên:** tương đương (B nhiều hơn 40 chunk nhưng ít ký tự hơn vì không có overlap).
- **So sánh B–C (chỉ đổi filter):**
  - Filter chỉ tác động lên 3 câu, nhưng tác động rõ: tuân thủ filter tăng từ 1/2 lên 2/2 (dev) và từ 0/1 lên 1/1 (test).
  - **d15** (dev, `chapter=III`, gold trang 30, Điều 20): B trả về 3 chunk Chương II/V (hạng 1 là Điều 10 trang 17, quy định gần giống cho hóa đơn), trượt. C lấy đúng chunk Điều 20 ở hạng 1.
  - **t04** (test, `chapter=III`, gold trang 29, Điều 18): cả B và C có evidence ở hạng 1, nhưng hạng 2–3 của B là nội dung hóa đơn ở Chương II (Điều 3, 4), dễ gây nhầm. C có cả 3 chunk thuộc Chương III.
  - Câu không có filter: B và C giống hệt nhau.
- **Hai ví dụ sai (ID câu và nguồn):**
  1. **t04 với A** (gold TT-91-2026 trang 29, Điều 18): evidence "Định dạng chứng từ điện tử gồm hai thành phần…" bị chia qua hai cửa sổ 360 ký tự, nên không chunk nào chứa trọn evidence. Đây là lỗi do chunking, không phải do truy xuất (đã biết từ trước khi chạy). A cũng có d12; B có d08.
  2. **t05 với cả A, B, C** (gold trang 32, Điều 25): câu hỏi ngày hiệu lực. Từ "hiệu lực" và "hóa đơn điện tử, chứng từ điện tử" xuất hiện khắp văn bản, nên top-3 rơi vào Điều 12, 21, 24 và phần căn cứ. Chunk chứa "hiệu lực thi hành kể từ ngày 01 tháng 7 năm 2026" không lọt top-3 ở cấu hình nào. Tương tự, t01 (tiêu chí rủi ro cao, trang 11) trượt cả ba vì câu dẫn của Điều 7 nằm ở trang 10, tách khỏi chunk liệt kê.
- **Chiến lược chọn, đánh đổi, điều kiện áp dụng:** theo tiêu chí đã chốt, **A được chọn** (hòa C ở Hit@3 dev 8/15, thắng ở Hit@1 dev 6 so với 2). Trên test, cả ba hòa 2/5, nên test không phân biệt được. Đánh đổi: A cho top-1 tốt hơn với câu hỏi sự kiện ngắn, nhưng chunk kém mạch lạc và metadata sai khi chunk vắt qua heading. B/C mạch lạc hơn và metadata đúng, nên phù hợp hơn khi cần đưa ngữ cảnh cho người đọc hoặc LLM, hoặc khi có filter theo phạm vi. Nếu người dùng thường biết trước phạm vi (hóa đơn hay chứng từ), C đáng ưu tiên hơn A. Kết luận chỉ áp dụng cho corpus này.
- **Hạn chế:**
  - **Dữ liệu:** một văn bản, OCR có lỗi; phụ lục bị loại.
  - **Mẫu nhỏ:** 5 câu test, chênh 1 câu là 20%. Chỉ 3 câu filter.
  - **Nhãn:** coherence, metadata và grounding do một người chấm (Phạm Đức Vinh), người chấm biết kết quả tự động.
  - **Giới hạn model:** kích thước chunk bị ép xuống 360 ký tự do model chỉ đọc 128 token. Điều này làm B phải cắt cứng câu luật dài (có chunk chỉ 4 ký tự).
  - **Thời gian:** đo một lần trên CPU, không lặp lại.
  - **Quy trình:** việc đổi kích thước chunk được quyết định dựa trên một lần thử trên dev.
- **Nếu làm lại hoặc mở rộng:** (1) dùng model đọc được 512 token (ví dụ `intfloat/multilingual-e5-small`) để B giữ trọn Khoản; (2) thêm tiêu đề Điều vào đầu mỗi chunk B, nhằm sửa lỗi chunk cùng Điều cạnh tranh nhau và lỗi t01; (3) thử hybrid BM25 + dense cho câu có số liệu hoặc ngày (t05, t02); (4) tạo thêm câu test và câu filter để giảm sai số; (5) có người chấm thứ hai độc lập.

## Công cụ và cách kiểm tra

Tác giả (Phạm Đức Vinh) trực tiếp đọc đề, viết code pipeline, soạn benchmark và thực hiện dán nhãn audit.

**Công cụ AI:** Claude Code (model Haiku 5.5). Trong các phiên rà soát và sửa tài liệu nộp bài, AI đã đọc và đối chiếu SUBMISSION, RULES, RUBRIC, CHECKPOINTS với cấu trúc repo; chạy lệnh kiểm tra evidence; sửa STUDENT.md, báo cáo và ghi chú `artifacts/experiment_log.csv`. Mọi số liệu trong báo cáo lấy từ file kết quả hoặc lệnh đã chạy, không do AI ước lượng. Việc AI có hỗ trợ viết code pipeline và benchmark hay không: [tác giả xác nhận trước khi nộp].

Cách kiểm tra:
- Selftest cho `ingestion`, `chunking`, `evaluation`.
- Lệnh `--verify` cho evidence của benchmark.
- Đối chiếu benchmark với ảnh PDF.
- Tác giả (Phạm Đức Vinh) trực tiếp rà soát và đối chiếu nhãn audit.
- Chạy lại các lệnh trong README.

Trong quá trình làm, tác giả (Phạm Đức Vinh) tự phát hiện và sửa các lỗi sau:
- Regex bỏ sót Điều 9.
- Chọn nhầm chunk ở file coherence.
- Giới hạn 128 token của model embedding.
