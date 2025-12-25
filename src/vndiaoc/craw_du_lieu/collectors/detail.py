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


def _extract_specs(driver) -> dict:
    specs = {
        "loai_bds": "",
        "ngay_het_han": "",
        "features": []
    }

    # ===== listOption =====
    try:
        items = driver.find_elements(By.CSS_SELECTOR, ".listOption ul li")

        for li in items:
            key = li.find_element(By.TAG_NAME, "span").text.strip()
            val = li.text.replace(key, "").replace(":", "").strip()

            if key == "Loại bất động sản":
                specs["loai_bds"] = val
            elif key == "Ngày hết hạn":
                specs["ngay_het_han"] = val

    except:
        pass

    # ===== listDesign (tiện ích) =====
    try:
        specs["features"] = [
            el.text.strip()
            for el in driver.find_elements(
                By.CSS_SELECTOR,
                ".listDesign ul li .item"
            )
            if el.text.strip()
        ]
    except:
        pass

    return specs


def _extract_images(driver) -> list[str]:
    images = []
    try:
        imgs = driver.find_elements(
            By.CSS_SELECTOR,
            "#slideImgNav .slick-slide img"
        )

        for img in imgs:
            src = img.get_attribute("data-src") or img.get_attribute("src")

            if not src or src.startswith("data:image"):
                continue

            clean_src = clean_image_url(src)

            if clean_src and clean_src not in images:
                images.append(clean_src)

    except Exception as e:
        print(e)

    return images


def _extract_description(driver, wait) -> str:
    try:
        desc_el = wait.until(
            EC.presence_of_element_located((
                By.CSS_SELECTOR,
                "#vnt-content .wrapper .gridContent .col1 .boxDesign .content .the-info .the-cap"
            ))
        )

        # Lấy nguyên HTML bên trong
        html = desc_el.get_attribute("outerHTML") or ""

        return html.strip()

    except Exception:
        return ""

def _extract_phone(driver, wait, human_sleep):
    phone_text = ""
    contact_name = ""

    try:
        # ===== LẤY TÊN LIÊN LẠC =====
        name_el = wait.until(
            EC.presence_of_element_located((
                By.XPATH,
                "//li[.//div[@class='at' and normalize-space()='Tên liên lạc']]//div[@class='as']"
            ))
        )
        contact_name = name_el.text.strip()

    except Exception:
        contact_name = ""

    try:
        # ===== LẤY SỐ ĐIỆN THOẠI =====
        phone_el = wait.until(
            EC.presence_of_element_located((
                By.XPATH,
                "//li[.//div[@class='at' and normalize-space()='Điện thoại']]//a"
            ))
        )

        phone_text = phone_el.text.strip()

        # Fallback lấy từ href tel:
        if not phone_text:
            href = phone_el.get_attribute("href") or ""
            phone_text = href.replace("tel:", "").strip()

    except Exception:
        phone_text = ""

    return phone_text, contact_name


def _extract_map(driver, wait):
    map_coords = ""
    map_link = ""
    map_dms = ""

    try:
        # Đảm bảo page load xong
        wait.until(lambda d: d.execute_script("return typeof data_map !== 'undefined'"))

        data = driver.execute_script("return data_map")

        if not data or not isinstance(data, list):
            return "", "", ""

        item = data[0]

        lat = float(item.get("lat", ""))
        lng = float(item.get("lon", ""))

        if not (-90 <= lat <= 90 and -180 <= lng <= 180):
            return "", "", ""

        map_coords = f"{lat},{lng}"

        # Optional: link Google Maps
        map_link = f"https://www.google.com/maps?q={lat},{lng}"

        # Optional: DMS
        try:
            map_dms = utils.format_dms(lat, lng)
        except:
            map_dms = ""

    except Exception:
        return "", "", ""

    return map_coords, map_link, map_dms

def _extract_area(driver, wait):
    area = ""
    total_area = ""

    try:
        # Diện tích
        area_el = driver.find_element(
            By.XPATH,
            "//div[@class='the-attr']//li[starts-with(normalize-space(), 'Diện tích')]//span"
        )
        area = area_el.text.strip()

    except:
        pass

    try:
        # Tổng diện tích
        total_el = driver.find_element(
            By.XPATH,
            "//div[@class='the-attr']//li[contains(normalize-space(), 'Tổng diện tích')]//span"
        )
        total_area = total_el.text.strip()

    except:
        pass

    return area, total_area


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

    try:
        title_el = wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".title h1"))
        )
        item["title"] = title_el.text.strip()
    except Exception:
        item["title"] = ""


    specs_map = _extract_specs(driver)

    # Lấy địa chỉ
    try:
        addr_el = wait.until(
            EC.presence_of_element_located((
                By.XPATH,
                "//div[@class='boxOption']//li[.//div[@class='at' and normalize-space()='Địa chỉ']]//div[@class='as']"
            ))
        )
        item["location"] = addr_el.text.strip()

    except Exception:
        item["location"] = ""

    item["description"] = _extract_description(driver, wait)
    item["images"] = _extract_images(driver)

    item["specs"] = specs_map
    item["posted_date"] = specs_map['ngay_het_han']
    
    phone_text, contact_name = _extract_phone(driver, wait, human_sleep)
    item["agent_phone"] = phone_text
    item["agent_name"] = contact_name
    
    area, total_area = _extract_area(driver, wait)
    item["area"] = total_area

    map_coords, map_link, map_dms = _extract_map(driver, wait)
    item["map_coords"] = map_coords
    item["map_link"] = map_link
    item["map_dms"] = map_dms

    human_sleep(2, 4)
    try:
        driver.get(current_list_url)
        human_sleep(2, 4)
    except Exception:
        pass

    return item

