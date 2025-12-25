from __future__ import annotations

import os
import re
from typing import Callable

from selenium.common.exceptions import WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from .. import utils
import time
from urllib.parse import unquote, quote
from selenium.webdriver.common.by import By
from selenium import webdriver

def clean_image_url(url: str | None):
    if not url or "no-photo" in url:
        return None
    return url


def _scroll_detail(driver, steps: int, human_sleep: Callable[[float, float], None]):
    for _ in range(steps):
        driver.execute_script("window.scrollBy(0, 1000);")
        human_sleep(0.5, 2.0)


def _extract_images(driver) -> list[str]:
    images = []
    try:
        # Chọn tất cả ảnh trong slick slider
        imgs = driver.find_elements(By.CSS_SELECTOR, ".slick-item img")

        for img in imgs:
            # Lấy src của ảnh, fallback nếu cần
            src = img.get_attribute("data-src") or img.get_attribute("src") or ""

            # Bỏ qua base64 hoặc rỗng
            if not src or src.startswith("data:image"):
                continue

            # Hàm xử lý url nếu cần
            clean_src = clean_image_url(src)

            # Thêm vào danh sách nếu chưa có
            if clean_src and clean_src not in images:
                images.append(clean_src)

    except Exception:
        pass

    return images


def _extract_description(driver, wait) -> str:
    try:
        desc_el = wait.until(
            EC.presence_of_element_located((
                By.CSS_SELECTOR,
                ".div-mota"
            ))
        )
        return desc_el.text.strip()
    except Exception:
        return ""

def _extract_phone(driver, wait, human_sleep: Callable[[float, float], None]) -> tuple[str, str]:
    phone_text = ""
    contact_name = ""

    try:
        rows = driver.find_elements(By.CSS_SELECTOR, ".panel-detail-info .row-line")
        for row in rows:
            label = row.find_element(By.CSS_SELECTOR, ".span-1").text.strip()
            value = row.find_element(By.CSS_SELECTOR, ".span-2").text.strip()

            if label in ["Tên liên lạc", "Người đăng", "Liên hệ"]:
                contact_name = value
            elif label in ["Di động", "Điện thoại", "SĐT"]:
                phone_text = value

    except Exception:
        pass

    return phone_text, contact_name

def _extract_map(driver, wait):
    map_coords = ""
    map_link = ""
    map_dms = ""

    try:
        # Tìm iframe bản đồ
        iframe = wait.until(EC.presence_of_element_located(
            (By.CSS_SELECTOR, "#block-4 iframe")
        ))

        # Lấy src
        map_link = iframe.get_attribute("src") or iframe.get_attribute("data-src") or ""
        if not map_link:
            return "", "", ""

        lat_str = lng_str = None

        # ================================
        # Pattern 1: !3dLAT!4dLNG
        # ================================
        match = re.search(r'!3d([0-9\.\-]+)!4d([0-9\.\-]+)', map_link)
        if match:
            lat_str, lng_str = match.group(1), match.group(2)

        # ================================
        # Pattern 2: ?q=LAT,LNG
        # ================================
        if not lat_str:
            match2 = re.search(r'q=([0-9\.\-]+),([0-9\.\-]+)', map_link)
            if match2:
                lat_str, lng_str = match2.group(1), match2.group(2)

        # ================================
        # Pattern 3: chỉ có địa chỉ → mở Google Maps để lấy tọa độ
        # ================================
        if not lat_str:
            addr_match = re.search(r'[?&]q=([^&]+)', map_link)
            if addr_match:
                driver_ = webdriver.Chrome()
                address = unquote(addr_match.group(1))  # decode URL
                search_url = f"https://www.google.com/maps/search/{quote(address)}"

                # Mở Google Maps search
                driver_.get(search_url)
                time.sleep(5)  # chờ load, có thể tăng nếu mạng chậm

                # Lấy URL hiện tại, thường có dạng: .../@LAT,LNG,ZOOMz
                current_url = driver_.current_url
                m_url = re.search(r'@([0-9\.\-]+),([0-9\.\-]+),', current_url)
                if m_url:
                    lat_str, lng_str = m_url.group(1), m_url.group(2)
                driver_.quit()
        # ================================
        # Chuyển sang float và kiểm tra
        # ================================
        if lat_str and lng_str:
            try:
                lat = float(lat_str)
                lng = float(lng_str)
                if -90 <= lat <= 90 and -180 <= lng <= 180:
                    map_coords = f"{lat},{lng}"
                    try:
                        map_dms = utils.format_dms(lat, lng)
                    except:
                        map_dms = ""
            except:
                return "", map_link, ""

    except Exception:
        return "", map_link, ""

    return map_coords, map_link, map_dms

def _extract_location(driver, wait):
    try:
        addr_el = wait.until(
            EC.presence_of_element_located((
                By.CSS_SELECTOR,
                "p.span-info"
            ))
        )
        full_text = addr_el.text.strip()  # "Vị trí: Bán đất nền dự án tại Đồng Việt - Yên Dũng - Bắc Giang"

        # Tách phần "Bán đất nền dự án tại ..." để lấy tên địa phương
        a_text = addr_el.find_element(By.TAG_NAME, "a").text  # "Bán đất nền dự án tại Đồng Việt"
        match = re.search(r'tại (.+)', a_text)
        if match:
            project_location = match.group(1).strip()  # "Đồng Việt"
        else:
            project_location = ""

        # Lấy phần còn lại sau link
        remaining = full_text.split(a_text)[-1].strip(" -")  # "Yên Dũng - Bắc Giang"
        # Nối tất cả
        location = ", ".join([project_location] + [x.strip() for x in remaining.split("-")])
        return location
    except Exception:
        return ""

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

    item["description"] = _extract_description(driver, wait)
    item["images"] = _extract_images(driver)

    phone_text, contact_name = _extract_phone(driver, wait, human_sleep)
    item["agent_phone"] = phone_text
    item["agent_name"] = contact_name
    
    item["location"] = _extract_location(driver, wait)

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

