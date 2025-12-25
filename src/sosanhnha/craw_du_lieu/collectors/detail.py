from __future__ import annotations

import os
import re
from typing import Callable

from selenium.common.exceptions import WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from .. import utils
import time

def clean_image_url(url: str | None):
    if not url or "no-photo" in url:
        return None
    return url


def _scroll_detail(driver, steps: int, human_sleep: Callable[[float, float], None]):
    for _ in range(steps):
        driver.execute_script("window.scrollBy(0, 1000);")
        human_sleep(0.5, 2.0)

def _extract_images(driver) -> list[str]:
    images = set()

    try:
        srcs = driver.execute_script("""
            return Array.from(
                document.querySelectorAll(
                    '#animated-thumbnails-gallery a.swiper-slide'
                )
            )
            .map(a => a.getAttribute('data-src'))
            .filter(src => src && src.startsWith('http'));
        """)

        for src in srcs:
            images.add(src)

    except Exception:
        pass

    return list(images)


def _extract_description(driver, wait) -> str:
    try:
        desc_el = wait.until(
            EC.presence_of_element_located((
                By.CSS_SELECTOR,
                ".description"
            ))
        )
        return desc_el.get_attribute("innerText").strip()  # GIỮ XUỐNG DÒNG
    except Exception:
        return ""


def extract_contact_info(driver, wait):
    contact_name = ""
    phone_text = ""

    # ==========================
    # Contact name
    # ==========================
    try:
        contact_name = wait.until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, ".page-right span.font-bold.text-gray-700")
            )
        ).text.strip()
    except:
        contact_name = ""

    # ==========================
    # Phone (click để hiện)
    # ==========================
    try:
        phone_btn = wait.until(
            EC.element_to_be_clickable(
                (By.CSS_SELECTOR, ".page-right #phone button")
            )
        )

        # Click bằng JS cho chắc (tránh overlay)
        driver.execute_script("arguments[0].click();", phone_btn)

        # Chờ text KHÔNG còn ***
        wait.until(
            lambda d: "***" not in phone_btn.text
        )

        phone_text = phone_btn.text.strip()

        # Optional: clean chỉ lấy số
        phone_text = re.sub(r"[^\d+]", "", phone_text)

    except:
        phone_text = ""

    return contact_name, phone_text


def _extract_map(driver, wait):
    map_coords = ""
    map_link = ""
    map_dms = ""

    try:
        # Tìm link Google Maps trong detailactions
        map_a = wait.until(
            EC.presence_of_element_located((
                By.CSS_SELECTOR,
                "#detailactions a[href*='maps.google.com']"
            ))
        )

        map_link = map_a.get_attribute("href") or ""
        if not map_link:
            return "", "", ""

        lat_str = lng_str = None

        # ================================
        # Pattern: daddr=LAT+LNG
        # ================================
        m = re.search(r'daddr=([0-9.\-]+)\+([0-9.\-]+)', map_link)
        if m:
            lat_str, lng_str = m.group(1), m.group(2)

        if not lat_str:
            return "", map_link, ""

        # Convert to float
        lat = float(lat_str)
        lng = float(lng_str)

        # Validate
        if not (-90 <= lat <= 90 and -180 <= lng <= 180):
            return "", map_link, ""

        map_coords = f"{lat},{lng}"

        try:
            map_dms = utils.format_dms(lat, lng)
        except:
            map_dms = ""

    except Exception:
        return "", "", ""

    return map_coords, map_link, map_dms

def _extract_specs(driver) -> dict[str, str]:
    data = {}

    items = driver.find_elements(
        By.CSS_SELECTOR,
        ".detail-params .item"
    )

    for it in items:
        try:
            label = it.find_element(By.CSS_SELECTOR, ".label").text.strip()
            value = it.find_element(By.CSS_SELECTOR, ".value").text.strip()
            data[label] = value
        except:
            continue

    return data

def open_detail_and_extract(
    driver,
    wait,
    item: dict,
    *,
    current_list_url: str,
    screenshot_dir: str,
    detail_scroll_steps: int,
    human_sleep: Callable[[float, float], None],
):
    href = item["href"]
    print(f"  -> Opening detail: {href}")

    try:
        driver.get(href)
    except WebDriverException:
        driver.get(href)
    human_sleep(3, 5)

    _scroll_detail(driver, detail_scroll_steps, human_sleep)

    cur_url = driver.current_url.lower()
    page_source = driver.page_source.lower()

    if "captcha" in cur_url or "captcha" in page_source[:3000]:
        fname = os.path.join(screenshot_dir, f"captcha_detail_{href}.png")
        try:
            driver.save_screenshot(fname)
        except Exception:
            pass
        print("CAPTCHA detected:", href)
        driver.get(current_list_url)
        human_sleep(2, 4)
        return item

    # Lấy địa chỉ
    try:
        addr_el = wait.until(
            EC.presence_of_element_located((
                By.XPATH,
                "//div[@class='detail-params']//div[@class='item'][.//span[contains(normalize-space(),'Địa chỉ')]]//span[@class='value']"
            ))
        )
        item["location"] = addr_el.text.strip()
    except Exception:
        item["location"] = ""


    # Lấy ngày cập nhật
    try:
        date_el = wait.until(
            EC.presence_of_element_located((
                By.XPATH,
                "//div[@class='detail-params']//div[@class='item'][.//span[contains(normalize-space(),'Cập nhật')]]//*[@class='value']"
            ))
        )
        item["posted_date"] = date_el.text.strip()
    except Exception:
        item["posted_date"] = ""


    item["description"] = _extract_description(driver, wait)
    item["images"] = _extract_images(driver)

    contact_name, phone_text = extract_contact_info(driver, wait)
    item["agent_phone"] = phone_text
    item["agent_name"] = contact_name

    map_coords, map_link, map_dms = _extract_map(driver, wait)
    item["map_coords"] = map_coords
    item["map_link"] = map_link
    item["map_dms"] = map_dms
    specs_map = _extract_specs(driver)
    item["specs"] = specs_map

    human_sleep(2, 4)
    try:
        driver.get(current_list_url)
        human_sleep(2, 4)
    except Exception:
        pass

    return item

