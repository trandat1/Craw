from __future__ import annotations

import time
from typing import List, Tuple

from selenium.common.exceptions import StaleElementReferenceException
from selenium.webdriver.common.by import By


def _scroll_listing(driver, steps: int):
    try:
        driver.execute_script("window.scrollTo(0, 0);")
        for _ in range(steps):
            driver.execute_script("window.scrollBy(0, 1200);")
            time.sleep(0.3)
    except Exception:
        pass


def collect_list_items(
    driver,
    scraped_hrefs: set[str],
    max_items: int,
    scroll_steps: int,
) -> Tuple[list[dict], int, int, int]:
    """
    Return (items, total_cards, skipped_pid, skipped_href).
    """
    _scroll_listing(driver, scroll_steps)

    out: List[dict] = []
    els = []

    # Chờ danh sách xuất hiện
    for _ in range(20):
        els = driver.find_elements(
            By.CSS_SELECTOR,
            "ul.ListAds_ListAds__ANK2d > li"
        )
        if els:
            break
        time.sleep(1)

    skipped_href = 0

    for el in els:
        try:
            # Lấy thẻ <a>
            a = el.find_element(By.CSS_SELECTOR, "a")
            href = a.get_attribute("href")
            if not href:
                continue

            # Check trùng
            if href in scraped_hrefs:
                skipped_href += 1
                continue

            # Lấy title (thẻ h3)
            try:
                title = el.find_element(By.CSS_SELECTOR, "h3").text.strip()
            except:
                title = ""

            # =============================
            # Lấy giá, giá/m2, diện tích
            # =============================

            # Các span giá nằm trong div.sqqmhlc
            try:
                info_spans = el.find_elements(By.CSS_SELECTOR, ".sqqmhlc span")
                price = info_spans[0].text.strip() if len(info_spans) > 0 else ""
                price_per_m2 = info_spans[1].text.strip() if len(info_spans) > 1 else ""
                area = info_spans[2].text.strip() if len(info_spans) > 2 else ""
            except:
                price = price_per_m2 = area = ""

            out.append(
                {
                    "href": href,
                    "title": title,
                    "price": price,               # ← giá
                    "price_per_m2": price_per_m2, # ← giá/m²
                    "area": area,                 # ← diện tích
                    "location": "",
                    "description": "",
                    "thumbnail": "",
                    "posted_date": "",
                    "agent_name": "",
                    "agent_phone": "",
                    "images": [],
                    "specs": {},
                    "config": {},
                    "map_coords": "",
                    "map_link": "",
                    "map_dms": ""
                }
            )

        except StaleElementReferenceException:
            continue
        
    if not out:
        print(
            f"[collect_list_items] Found {len(els)} cards but skipped {skipped_href} by href."
        )
        
    return out[:max_items], len(els), 0, skipped_href

