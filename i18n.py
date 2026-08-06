"""All user-facing text in one place, keyed by language.

To translate the whole app (report, charts, and UI) or add a language, edit
this file only. `get_labels()` returns the active-language dict based on
config.REPORT_LANGUAGE.
"""

from config import REPORT_LANGUAGE

LABELS = {
    "English": {
        # --- report + chart labels ---
        "title": "Financial Report",
        "generated": "Generated",
        "summary": "Summary",
        "financials": "Financial Figures",
        "year": "Year",
        "revenue": "Revenue",
        "net_income": "Net income",
        "margins": "Profit Margins (latest period)",
        "gross": "Gross margin",
        "operating": "Operating margin",
        "net": "Net margin",
        "highlights": "Highlights",
        "risks": "Risks",
        "full_research": "Full Research",
        "none": "_None extracted._",
        "unknown": "n/a",
        "trend": "Revenue & Profit over time",
        "segments": "Revenue by segment",
        "profit_share": "Profit share of revenue",
        "profit_label": "Profit",
        "other_label": "Costs",
        "growth": "vs last year",
        "health_good": "Financially healthy",
        "health_mixed": "Mixed picture",
        "health_weak": "Financial concerns",
        "yoy": "YoY",
        "cash_vs_debt": "Cash vs Debt",
        "cash": "Cash",
        "debt": "Debt",
        "cash_flow": "Cash flow",
        "operating_cf": "Operating cash flow",
        "free_cf": "Free cash flow",
        "debt_to_equity": "Debt / Equity",
        "current_ratio": "Current ratio",
        "safety": "Financial safety",
        # --- app UI ---
        "app_title": "📊 Financial Report Agent",
        "app_caption": (
            "Type a company name and start a research job. Research runs in "
            "the background on Google's servers (typically 5–10 minutes) — "
            "you can start several jobs at once and refresh to collect "
            "finished reports."
        ),
        "company_input": "Company name(s), comma-separated",
        "company_placeholder": "e.g. Tesla, Apple",
        "start_btn": "Start research",
        "enter_name": "Enter at least one company name.",
        "started": "Started research for",
        "tab_jobs": "Jobs",
        "tab_reports": "Reports",
        "refresh": "🔄 Refresh",
        "clear_finished": "🧹 Clear finished",
        "no_jobs": "No jobs yet — start one above.",
        "started_at": "started",
        "state_running": "running",
        "state_done": "done",
        "state_failed": "failed",
        "job_done": "Report ready: `{name}` — open it in the **Reports** tab.",
        "job_running": "Research in progress — hit Refresh to update.",
        "job_failed": "This research run failed. Start it again above.",
        "no_reports": "No reports yet — they appear here once a job finishes.",
        "open_report": "Open a report",
        "download": "⬇️ Download markdown",
        "delete": "🗑️ Delete report",
        "confirm_delete": "⚠️ Confirm delete",
        # --- job-event toasts (from agent.refresh_jobs) ---
        "ev_ready": "report ready",
        "ev_failed": "research failed (status: {status})",
        "ev_no_data": (
            "no financial figures could be extracted from the research, so "
            "the report was not written. Try running it again."
        ),
        "ev_data_incomplete": (
            "report ready, but revenue could not be found in the research — "
            "the revenue chart may be incomplete."
        ),
        "ev_process_retry": (
            "could not process yet ({error}) — left running, will retry on the "
            "next refresh."
        ),
        "ev_check_fail": "could not check status ({error})",
    },
    "Vietnamese": {
        # --- report + chart labels ---
        "title": "Báo cáo tài chính",
        "generated": "Ngày tạo",
        "summary": "Tóm tắt",
        "financials": "Số liệu tài chính",
        "year": "Năm",
        "revenue": "Doanh thu",
        "net_income": "Lợi nhuận ròng",
        "margins": "Biên lợi nhuận (kỳ gần nhất)",
        "gross": "Biên LN gộp",
        "operating": "Biên LN hoạt động",
        "net": "Biên LN ròng",
        "highlights": "Điểm nổi bật",
        "risks": "Rủi ro",
        "full_research": "Toàn văn nghiên cứu",
        "none": "_Không có dữ liệu._",
        "unknown": "không rõ",
        "trend": "Doanh thu & Lợi nhuận theo năm",
        "segments": "Cơ cấu doanh thu theo mảng",
        "profit_share": "Tỷ lệ lợi nhuận trên doanh thu",
        "profit_label": "Lợi nhuận",
        "other_label": "Chi phí",
        "growth": "so với năm trước",
        "health_good": "Tài chính lành mạnh",
        "health_mixed": "Bức tranh trái chiều",
        "health_weak": "Có lo ngại tài chính",
        "yoy": "so cùng kỳ",
        "cash_vs_debt": "Tiền mặt & Nợ vay",
        "cash": "Tiền mặt",
        "debt": "Nợ vay",
        "cash_flow": "Dòng tiền",
        "operating_cf": "Dòng tiền kinh doanh",
        "free_cf": "Dòng tiền tự do",
        "debt_to_equity": "Nợ / Vốn CSH",
        "current_ratio": "Thanh khoản hiện hành",
        "safety": "Mức độ an toàn tài chính",
        # --- app UI ---
        "app_title": "📊 Trợ lý Báo cáo Tài chính",
        "app_caption": (
            "Nhập tên công ty và bắt đầu một lượt nghiên cứu. Quá trình chạy "
            "ngầm trên máy chủ của Google (thường 5–10 phút) — bạn có thể "
            "chạy nhiều công ty cùng lúc và nhấn Làm mới để lấy báo cáo đã "
            "hoàn tất."
        ),
        "company_input": "Tên công ty (cách nhau bằng dấu phẩy)",
        "company_placeholder": "ví dụ: FPT, Apple, Samsung",
        "start_btn": "Bắt đầu nghiên cứu",
        "enter_name": "Vui lòng nhập ít nhất một tên công ty.",
        "started": "Đã bắt đầu nghiên cứu",
        "tab_jobs": "Công việc",
        "tab_reports": "Báo cáo",
        "refresh": "🔄 Làm mới",
        "clear_finished": "🧹 Xóa mục đã xong",
        "no_jobs": "Chưa có công việc nào — hãy bắt đầu ở trên.",
        "started_at": "bắt đầu",
        "state_running": "đang chạy",
        "state_done": "hoàn tất",
        "state_failed": "thất bại",
        "job_done": "Báo cáo đã sẵn sàng: `{name}` — mở ở tab **Báo cáo**.",
        "job_running": "Đang nghiên cứu — nhấn Làm mới để cập nhật.",
        "job_failed": "Lượt nghiên cứu này thất bại. Hãy chạy lại ở trên.",
        "no_reports": "Chưa có báo cáo nào — sẽ xuất hiện khi một công việc hoàn tất.",
        "open_report": "Mở một báo cáo",
        "download": "⬇️ Tải xuống (markdown)",
        "delete": "🗑️ Xóa báo cáo",
        "confirm_delete": "⚠️ Xác nhận xóa",
        # --- job-event toasts ---
        "ev_ready": "báo cáo đã sẵn sàng",
        "ev_failed": "nghiên cứu thất bại (trạng thái: {status})",
        "ev_no_data": (
            "không trích xuất được số liệu tài chính nào từ nghiên cứu nên "
            "báo cáo chưa được tạo. Vui lòng chạy lại."
        ),
        "ev_data_incomplete": (
            "báo cáo đã sẵn sàng, nhưng không tìm thấy doanh thu trong nghiên "
            "cứu — biểu đồ doanh thu có thể chưa đầy đủ."
        ),
        "ev_process_retry": (
            "chưa xử lý được ({error}) — vẫn để đang chạy, sẽ thử lại ở lần "
            "làm mới sau."
        ),
        "ev_check_fail": "không kiểm tra được trạng thái ({error})",
    },
}


def get_labels() -> dict:
    """Return the active-language label set (falls back to English)."""
    return LABELS.get(REPORT_LANGUAGE, LABELS["English"])
