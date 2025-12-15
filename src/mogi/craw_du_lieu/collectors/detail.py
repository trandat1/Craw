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
    specs_map = {}
    try:
        # Lấy tất cả các mục thông số
        spec_items = driver.find_elements(By.CSS_SELECTOR, '.info-attrs.clearfix .info-attr.clearfix')
        for spec in spec_items:
            try:
                spans = spec.find_elements(By.TAG_NAME, "span")
                if len(spans) >= 2:
                    key = spans[0].text.strip()
                    val = spans[1].text.strip()
                    specs_map[key] = val
            except Exception:
                continue
    except Exception:
        specs_map = {}
    return specs_map

def _extract_images(driver) -> list[str]:
    images = []
    try:
        imgs = driver.find_elements(By.CSS_SELECTOR, ".owl-carousel .owl-item img")

        for img in imgs:
            src = img.get_attribute("data-src") or img.get_attribute("src") or ""

            if not src or src.startswith("data:image"):
                continue

            clean_src = clean_image_url(src)

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
                ".info-content-body"
            ))
        )
        # Lấy innerHTML
        html = desc_el.get_attribute("innerHTML") or ""

        # Thay <br> và <br/> bằng newline
        text = html.replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n")

        # Loại bỏ thẻ HTML còn lại nếu có
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(text, "html.parser")
        clean_text = soup.get_text().strip()

        return clean_text

    except Exception:
        return ""

def _extract_phone(driver, wait, human_sleep):
    phone_text = ""
    contact_name = ""

    try:
        span = wait.until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, "a[gtm-act='mobile-call'] span.ng-binding")
            )
        )
        phone_text = span.text.strip()

        def is_masked(phone):
            return (
                not phone
                or "xxx" in phone.lower()
                or "*" in phone
                or len(phone.replace(" ", "")) < 9
            )

        # 👉 Nếu bị che → click
        if is_masked(phone_text):
            btn = span.find_element(By.XPATH, "./ancestor::a")

            driver.execute_script(
                "arguments[0].scrollIntoView({behavior:'smooth', block:'center'});",
                btn
            )
            human_sleep(0.3, 0.6)

            try:
                btn.click()
            except:
                driver.execute_script(
                    "arguments[0].dispatchEvent(new MouseEvent('click', {bubbles:true}));",
                    btn
                )

            human_sleep(0.4, 0.7)

            # Lấy lại text sau khi click
            phone_text = span.text.strip()

    except Exception:
        # Fallback cuối cùng
        m = re.search(
            r"(0\d{8,10}|\+84\d{8,10})",
            driver.page_source.replace(" ", "")
        )
        phone_text = m.group(0) if m else ""

    # ===== Lấy tên người đăng =====
    try:
        name_el = driver.find_element(
            By.CSS_SELECTOR,
            ".agent-widget .agent-name a"
        )
        contact_name = name_el.text.strip()
       

    except:
        try:
            name_el = driver.find_element(
                By.CSS_SELECTOR,
                ".agent-widget .agent-name"
            )
            contact_name = name_el.text
            contact_name = re.sub(r"\s+", " ", contact_name).strip()
        except:
            pass

    return phone_text, contact_name


def _extract_map(driver, wait):
    map_coords = ""
    map_link = ""
    map_dms = ""

    try:
        # Tìm đúng iframe bản đồ
        iframe = wait.until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, ".map-content iframe")
            )
        )

        # Scroll đến iframe (bắt buộc để load lazy iframe)
        driver.execute_script("arguments[0].scrollIntoView(true);", iframe)
        time.sleep(1)

        # Lấy URL bản đồ
        map_link = iframe.get_attribute("src") or iframe.get_attribute("data-src") or ""
        if not map_link:
            return "", "", ""

        lat_str = lng_str = None

        # ================================
        # Pattern 1: Google Maps embed dạng !3dLAT!4dLNG
        # ================================
        m1 = re.search(r'!3d([0-9.\-]+)!4d([0-9.\-]+)', map_link)
        if m1:
            lat_str, lng_str = m1.group(1), m1.group(2)

        # ================================
        # Pattern 2: dạng ?q=LAT,LNG hoặc &q=LAT,LNG
        # ================================
        if not lat_str:
            m2 = re.search(r'[?&]q=([0-9.\-]+),([0-9.\-]+)', map_link)
            if m2:
                lat_str, lng_str = m2.group(1), m2.group(2)

        # ================================
        # Pattern 3: dạng trung gian weird (Google đôi khi encode)
        # ================================
        if not lat_str:
            m3 = re.search(r'([0-9.\-]+),([0-9.\-]+)', map_link)
            if m3:
                # Chỉ chấp nhận khi khớp trong đoạn q= hoặc layer=
                if "maps" in map_link:
                    lat_str, lng_str = m3.group(1), m3.group(2)

        if not lat_str:
            # Không extract được tọa độ
            return "", map_link, ""

        # Chuyển đổi sang float
        try:
            lat = float(lat_str)
            lng = float(lng_str)
        except:
            return "", map_link, ""

        # Kiểm tra hợp lệ
        if not (-90 <= lat <= 90 and -180 <= lng <= 180):
            return "", map_link, ""

        # Tọa độ dạng decimal
        map_coords = f"{lat},{lng}"

        # Chuyển sang DMS
        try:
            map_dms = utils.format_dms(lat, lng)
        except:
            map_dms = ""

    except Exception:
        # Không tìm thấy iframe
        return "", "", ""

    return map_coords, map_link, map_dms


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
                By.CSS_SELECTOR,
                "div.address"
            ))
        )
        item["location"] = addr_el.text.strip()
    except Exception:
        item["location"] = ""


    item["description"] = _extract_description(driver, wait)
    item["images"] = _extract_images(driver)


    item["specs"] = specs_map
    item["posted_date"] = specs_map['Ngày đăng']
    
    phone_text, contact_name = _extract_phone(driver, wait, human_sleep)
    item["agent_phone"] = phone_text
    item["agent_name"] = contact_name

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

