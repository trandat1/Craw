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


def collect_list_items(driver, scraped_hrefs: set[str], max_items: int, scroll_steps: int):
    """
    Crawl danh sách sản phẩm, trả về list dict template.
    Chỉ update href, title, price, thumbnail nếu có.
    """
    _scroll_listing(driver, scroll_steps)

    skipped_href = 0
    out = []

    # Chờ product xuất hiện
    for _ in range(20):
        els = driver.find_elements(By.CSS_SELECTOR, "div.product")
        if els:
            break
        time.sleep(0.5)

    for el in els:
        try:
            item = {
                "href": "",
                "title": "",
                "price": "",
                "price_per_m2": "",
                "area": "",
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

            # ==============================
            # Link & title
            # ==============================
            try:
                a = el.find_element(By.CSS_SELECTOR, ".caption_wrapper .caption_wrap .tend a")
                href = a.get_attribute("href")
                title = a.text.strip()
                if href:
                    item["href"] = href
                if title:
                    item["title"] = title
            except:
                pass

            if item["href"] in scraped_hrefs:
                skipped_href += 1
                continue

            # ==============================
            # Thumbnail
            # ==============================
            try:
                img = el.find_element(By.CSS_SELECTOR, ".img img")
                thumbnail = img.get_attribute("src")
                if thumbnail:
                    item["thumbnail"] = thumbnail
            except:
                pass

            # ==============================
            # Price (nếu rỗng = "0")
            # ==============================
            try:
                price_el = el.find_element(By.CSS_SELECTOR, ".price")
                price_text = price_el.text.strip()
                item["price"] = price_text if price_text else "0"
            except:
                item["price"] = "0"

            # Push vào output
            out.append(item)

        except StaleElementReferenceException:
            continue

    return out[:max_items], len(els), 0, skipped_href

