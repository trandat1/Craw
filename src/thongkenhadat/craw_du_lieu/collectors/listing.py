from __future__ import annotations

from re import match
import re
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


def collect_list_items(driver, scraped_hrefs: set[str], max_items: int, scroll_steps: int) -> Tuple[List[dict], int, int, int]:
    """
    Return (items, total_cards, skipped_pid, skipped_href).
    """
    # Hàm scroll listing (bạn tự định nghĩa)
    _scroll_listing(driver, scroll_steps)

    out: List[dict] = []

    # Chờ danh sách xuất hiện
    els = []
    for _ in range(20):
        els = driver.find_elements(By.CSS_SELECTOR, "li.style1")
        if els:
            break
        time.sleep(1)

    skipped_href = 0

    for el in els:
        try:
            # ==============================
            # Lấy link & title
            # ==============================
            try:
                a = el.find_element(By.CSS_SELECTOR, "h3.name a")
                href = a.get_attribute("href")
                title = a.get_attribute("title") or a.text.strip()
            except:
                continue  # nếu không có href thì bỏ qua

            if href in scraped_hrefs:
                skipped_href += 1
                continue

            # ==============================
            # Thumbnail (ảnh lớn)
            # ==============================
            try:
                img = el.find_element(By.CSS_SELECTOR, "a.img img")
                thumbnail = img.get_attribute("src")
            except:
                thumbnail = ""

            # ==============================
            # Giá & diện tích & location
            # ==============================
            price = ""
            area = ""
            location = ""

            try:
                info_lis = el.find_elements(By.CSS_SELECTOR, "ul.info li")
                for li in info_lis:
                    text = li.text.strip()
                    if text.startswith("Giá:"):
                        price = li.find_element(By.TAG_NAME, "span").text.strip()
                    elif text.startswith("Diện tích:"):
                        area = li.find_element(By.TAG_NAME, "span").text.strip()
                    elif text.startswith("Vị trí:"):
                        location = li.find_element(By.TAG_NAME, "span").text.strip()
            except:
                pass

            # ==============================
            # Thời gian (posted_date)
            # ==============================
            try:
                posted_date = el.find_element(By.CSS_SELECTOR, "span.up-time").text.strip()
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