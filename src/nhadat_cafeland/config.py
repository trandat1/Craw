from datetime import datetime
from pathlib import Path
import os

# === Config mặc định ===
DEBUGGER_ADDRESS = "127.0.0.1:9222"
BASE_URL = "https://www.nhatot.com/mua-ban-dat"   # hoặc list URL
MAX_PAGES = 5
MAX_ITEMS_PER_PAGE = 20
PAGE_COOLDOWN_SECONDS = 1 * 60
PAGE_LOAD_TIMEOUT = 60
WAIT_TIMEOUT = 20
LIST_SCROLL_STEPS = 6
DETAIL_SCROLL_STEPS = 6

SCREENSHOT_DIR = "screenshots_blocked"

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "output"
OUTPUT_DIR_FILTER = OUTPUT_DIR / "output_filtered"
OUTPUT_DIR_IMAGES = PROJECT_ROOT / "images"

def ensure_directories():
    """Create top-level directories required for scraping."""
    for d in [SCREENSHOT_DIR, OUTPUT_DIR]:
        os.makedirs(d, exist_ok=True)


def sanitize_filename(value: str) -> str:
    """Convert filter values to safe filename parts."""
    return str(value).replace("/", "_").replace("\\", "_").replace(" ", "_")


def prepare_output_paths(today: datetime | None = None, filters: dict | None = None):
    today = today or datetime.now()

    # Nếu có filter → output vào folder FILTER
    if filters:
        filtered = "_".join(
            f"{key}_{sanitize_filename(v)}"
            for key, v in filters.items() if v
        )

        month_folder = OUTPUT_DIR_FILTER / today.strftime("%Y-%m")
        month_folder.mkdir(parents=True, exist_ok=True)

        results_file = month_folder / f"{today.strftime('%Y-%m-%d')}_{filtered}.json"
        return today, month_folder, results_file

    # Nếu không có filter → output mặc định
    ensure_directories()

    month_folder = OUTPUT_DIR / today.strftime("%Y-%m")
    month_folder.mkdir(parents=True, exist_ok=True)

    results_file = month_folder / f"{today.strftime('%Y-%m-%d')}.json"
    return today, month_folder, results_file
