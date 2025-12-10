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
    # m = re.search(r"(https://file4\.batdongsan\.com\.vn)/(?:resize|crop)/[^/]+/(.+)", url)
    # if m:
    #     return m.group(1) + "/" + m.group(2)
    return url


def _scroll_detail(driver, steps: int, human_sleep: Callable[[float, float], None]):
    for _ in range(steps):
        driver.execute_script("window.scrollBy(0, 1000);")
        human_sleep(0.5, 2.0)


def _extract_specs(driver):
    specs_map = {}
    try:
        # Tất cả các mục thông số
        spec_items = driver.find_elements(By.CSS_SELECTOR, 'div[data-testid="param-item"]')
        for spec in spec_items:
            try:
                # Key
                key_el = spec.find_element(By.CSS_SELECTOR, "div.a4ep88f span")
                key = key_el.text.strip()
                
                # Value
                val_el = spec.find_element(By.TAG_NAME, "strong")
                val = val_el.text.strip()
                
                specs_map[key] = val
            except Exception:
                continue
    except Exception:
        specs_map = {}
    return specs_map


def _extract_images(driver) -> list[str]:
    images = []
    try:
        # Lấy tất cả ảnh trong owl-carousel
        imgs = driver.find_elements(
            By.CSS_SELECTOR,
            ".owl-carousel .owl-item img"
        )

        for img in imgs:
            src = img.get_attribute("src") or ""

            # Bỏ ảnh rỗng hoặc base64 blur
            if not src or src.startswith("data:image"):
                continue

            clean_src = clean_image_url(src)

            if clean_src and clean_src not in images:
                images.append(clean_src)

    except Exception:
        pass

    return images


def _extract_description(driver, wait):
    try:
        desc_el = wait.until(
            EC.presence_of_element_located((
                By.CSS_SELECTOR,
                ".reals-description .blk-content.content"
            ))
        )
        return desc_el.get_attribute("innerText").strip()  # GIỮ XUỐNG DÒNG
    except Exception:
        return ""

def _extract_config(driver):
    config = {}
    try:
        config_items = driver.find_elements(By.CSS_SELECTOR, ".re__pr-short-info-item.js__pr-config-item")
        for ci in config_items:
            try:
                t = ci.find_element(By.CSS_SELECTOR, ".title").text.strip()
                v = ci.find_element(By.CSS_SELECTOR, ".value").text.strip()
                config[t] = v
            except Exception:
                continue
    except Exception:
        config = {}
    return config


def _extract_phone(driver, wait, human_sleep):
    phone_text = ""
    contact_name = ""

    # ────────────────────────────────────────────────
    # 1) TÌM & CLICK NÚT HIỆN SỐ
    # ────────────────────────────────────────────────
    try:
        # Nút hiện số thuộc class detailTelProfile
        btn = wait.until(
            EC.presence_of_element_located((
                By.CSS_SELECTOR,
                "a.detailTelProfile"
            ))
        )

        # Scroll vào view
        driver.execute_script(
            "arguments[0].scrollIntoView({behavior:'smooth',block:'center'});",
            btn
        )
        human_sleep(0.4, 0.8)

        # CLICK
        try:
            btn.click()
        except:
            # fallback click JS
            driver.execute_script(
                "arguments[0].dispatchEvent(new MouseEvent('click', {bubbles:true}));",
                btn
            )

        # ────────────────────────────────────────────────
        # 2) ĐÓNG ALERT (NẾU CÓ)
        # ────────────────────────────────────────────────
        human_sleep(0.3, 0.5)
        try:
            alert = driver.switch_to.alert
            alert.dismiss()     # đóng thông báo
        except:
            pass  # không có alert thì bỏ qua

        # ────────────────────────────────────────────────
        # 3) CHỜ SỐ ĐIỆN THOẠI HIỆN ĐẦY ĐỦ (tel:xxxxx)
        # ────────────────────────────────────────────────
        def phone_loaded(d):
            href = btn.get_attribute("href") or ""
            return href.startswith("tel:")

        wait.until(phone_loaded)

        # Lấy số từ href
        href_val = btn.get_attribute("href")
        if href_val and href_val.startswith("tel:"):
            phone_text = href_val.replace("tel:", "").strip()

    except Exception:
        # fallback: tìm trong page_source
        m = re.search(r"(0\d{8,10}|\+84\d{8,10})", driver.page_source.replace(" ", ""))
        phone_text = m.group(0) if m else ""

    # ────────────────────────────────────────────────
    # 4) LẤY CONTACT NAME
    # ────────────────────────────────────────────────
    try:
        # tên nằm trong strong trong profile-name
        name_el = driver.find_element(
            By.CSS_SELECTOR,
            ".profile-info .profile-name strong"
        )
        contact_name = name_el.text.strip()
    except:
        contact_name = ""

    return phone_text, contact_name




def _extract_map(driver, wait):
    map_coords = ""
    map_link = ""
    map_dms = ""

    try:
        iframe = wait.until(EC.presence_of_element_located(
            (By.CSS_SELECTOR, "div.reals-map div.blk-content content iframe")
        ))

        map_link = iframe.get_attribute("src") or iframe.get_attribute("data-src") or ""
        
        if not map_link:
            return "", "", ""

        # Pattern 1: Google Maps embed với !3d và !4d (ví dụ: ...!3d21.1136798508057!4d105.495305786485)
        match = re.search(r'!3d([0-9\.\-]+)!4d([0-9\.\-]+)', map_link)
        if match:
            lat_str, lng_str = match.group(1), match.group(2)
        else:
            # Pattern 2: Google Maps embed với q=lat,lng (ví dụ: ...?q=21.1136798508057,105.495305786485&key=...)
            match2 = re.search(r'q=([0-9\.\-]+),([0-9\.\-]+)', map_link)
            if match2:
                lat_str, lng_str = match2.group(1), match2.group(2)
            else:
                return "", map_link, ""

        # Chuyển đổi sang float và kiểm tra tính hợp lệ
        try:
            lat = float(lat_str)
            lng = float(lng_str)
            
            # Kiểm tra phạm vi hợp lệ (lat: -90 đến 90, lng: -180 đến 180)
            if -90 <= lat <= 90 and -180 <= lng <= 180:
                map_coords = f"{lat},{lng}"
                map_dms = utils.format_dms(lat, lng)
            else:
                # Tọa độ ngoài phạm vi hợp lệ
                return "", map_link, ""
        except (ValueError, TypeError):
            # Không thể chuyển đổi sang float
            return "", map_link, ""

    except Exception:
        # Không tìm thấy iframe hoặc lỗi khác
        pass

    return map_coords, map_link, map_dms



def _extract_pricing(driver, wait):
    pricing = {}
    return pricing

    # Chờ toàn bộ khối pricing load (Vue render xong)
    wait.until(EC.presence_of_element_located(
        (By.CSS_SELECTOR, ".re__chart-subsapo")
    ))

    cols = driver.find_elements(By.CSS_SELECTOR, ".re__chart-subsapo .re__chart-col")

    for col in cols:

        classes = col.get_attribute("class") or ""
        if "no-data" in classes:
            continue

        try:
            # Tìm trong scope của col, không phải toàn bộ document
            big_elem = col.find_element(By.CSS_SELECTOR, ".text-big strong")
            big = big_elem.text.strip()

            small_elem = col.find_element(By.CSS_SELECTOR, ".text-small")
            small = small_elem.text.strip()

            if small and big:
                pricing[small] = big

        except Exception as e:
            print("Vue/AJAX element not ready:", e)
            print(col.get_attribute("outerHTML"))
            continue

    return pricing



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
        title_el = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "h1.head-title")))
        item["title"] = title_el.text.strip()
    except Exception:
        item["title"] = ""

    specs_map = _extract_specs(driver)

    # Lấy địa chỉ
    try:
        addr_el = wait.until(
            EC.presence_of_element_located((
                By.XPATH,
                "//div[@class='reales-location']//div[contains(@style,'width:87%')]"
            ))
        )
        item["location"] = addr_el.text.strip().replace("\n", " ")
    except Exception:
        item["location"] = ""


    # Lấy ngày cập nhật
    try:
        date_el = wait.until(
            EC.presence_of_element_located((
                By.XPATH,
                "//div[@class='reales-location']//div[@class='col-right']//i"
            ))
        )
        # Ví dụ text: "Cập nhật: 10-12-2025"
        text = date_el.text.strip()
        item["posted_date"] = text.replace("Cập nhật:", "").strip()
    except Exception:
        item["posted_date"] = ""


    item["description"] = _extract_description(driver, wait)
    item["images"] = _extract_images(driver)


    item["specs"] = specs_map
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

