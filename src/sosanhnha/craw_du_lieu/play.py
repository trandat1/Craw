"""Script CLI để chạy scraper với config từ file config.py"""
import pathlib
import sys

# Thư mục src/
PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from sosanhnha import config
from sosanhnha.craw_du_lieu.runner import run_scraper



def main():
    """Chạy scraper với config từ file config.py"""
    # Xử lý BASE_URL có thể là string hoặc list
    base_urls = config.BASE_URL
    
    # Chạy scraper không có filter (dùng config mặc định)
    result = run_scraper(
        base_urls=base_urls,
        filters=None,  # Không dùng filter khi chạy từ CLI
        debugger_address=config.DEBUGGER_ADDRESS
    )
    
    print(f"\n{'='*60}")
    print(f"Hoàn thành! Đã scrape {result['total_items']} items")
    print(f"Kết quả lưu tại: {result['results_file']}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
