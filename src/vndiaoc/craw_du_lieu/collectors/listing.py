from __future__ import annotations

import time
from typing import List, Tuple

from selenium.common.exceptions import StaleElementReferenceException
from selenium.webdriver.common.by import By


def _scroll_listing(driver, steps: int):
    try:
        driver.execute_script("window.scrollTo(0, 0);")
        for _ in range(steps):
            driver.execute_script("window.scrollBy(0, 5000);")
            time.sleep(1)
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
        els = driver.find_elements(By.CSS_SELECTOR, "ul.props > li")
        if els:
            break
        time.sleep(1)

    skipped_href = 0
    out = []

    for el in els:
        try:
            # ==============================
            # Lấy link & title
            # ==============================
            try:
                a = el.find_element(By.CSS_SELECTOR, ".prop-info a.link-overlay")
                href = a.get_attribute("href")
                title = a.find_element(By.CSS_SELECTOR, "h2.prop-title").text.strip()
            except:
                continue  # nếu không có href thì bỏ qua

            if href in scraped_hrefs:
                skipped_href += 1
                continue

            # ==============================
            # Thumbnail (ảnh lớn)
            # ==============================
            try:
                img = el.find_element(By.CSS_SELECTOR, ".prop-img img")
                thumbnail = img.get_attribute("src")
            except:
                thumbnail = ""

            # ==============================
            # Giá & diện tích
            # ==============================
            try:
                price = el.find_element(By.CSS_SELECTOR, ".prop-info .price").text.strip()
            except:
                price = ""

            try:
                # Diện tích thường là li đầu tiên trong .prop-attr
                area = el.find_element(By.CSS_SELECTOR, ".prop-info .prop-attr li").text.strip()
            except:
                area = ""

            # ==============================
            # Vị trí
            # ==============================
            try:
                location = el.find_element(By.CSS_SELECTOR, ".prop-info .prop-addr").text.strip()
            except:
                location = ""

            # ==============================
            # Thời gian (posted_date)
            # ==============================
            try:
                posted_date = el.find_element(By.CSS_SELECTOR, ".prop-extra .prop-created").text.strip()
            except:
                posted_date = ""

            # ==============================
            # Push vào output
            # ==============================
            out.append(
                {
                    "href": href,
                    "title": title,
                    "price": price,
                    "price_per_m2": "",
                    "area": area,
                    "location": location,
                    "description": "",
                    "thumbnail": thumbnail,
                    "posted_date": posted_date,
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
        print(f"[collect_list_items] Found {len(els)} cards but skipped {skipped_href} by href.")

    return out[:max_items], len(els), 0, skipped_href
