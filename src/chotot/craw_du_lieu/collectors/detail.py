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


def _extract_images(driver):
    images = []
    try:
        imgs = driver.find_elements(
            By.XPATH,
            "//div[contains(@class,'slick-list')]//img"
        )

        for img in imgs:
            # Lấy src chính, hoặc fallback sang data-nimg, data-src
            src = img.get_attribute("src")

            # Bỏ ảnh base64 1x1 (ảnh blur)
            if src.startswith("data:image"):
                # Thử lấy từ background-image nếu có blur
                style = img.get_attribute("style")
                if "background-image" in style:
                    # trích URL từ trong style
                    bg_url = style.split('url("')[1].split('")')[0]
                    src = bg_url

            clean_src = clean_image_url(src)

            if clean_src and clean_src not in images:
                images.append(clean_src)

    except Exception:
        pass

    return images

def _extract_description(driver, wait):
    try:
    # 1. Click nút "Xem thêm" nếu có
        try:
            xem_them_btn = driver.find_element(
                By.XPATH,
                "//a[contains(normalize-space(text()), 'Xem thêm')]"
            )
            driver.execute_script("arguments[0].click();", xem_them_btn)

            # 1.1 Chờ class collapse -> expand (không bắt buộc nhưng an toàn)
            try:
                wait.until(
                    EC.presence_of_element_located((
                        By.XPATH,
                        "//div[contains(@class,'adBodyExpand')]"
                    ))
                )
            except:
                pass

            time.sleep(0.3)

        except:
            pass  # Không có nút "Xem thêm"

        # 2. Lấy mô tả chi tiết
        desc_el = wait.until(
            EC.presence_of_element_located((
                By.XPATH,
                "//p[@itemprop='description']"
            ))
        )

        return desc_el.text.strip()

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

    try:
        # ────────────────────────────────────────────────
        # 1) Tìm và click nút hiện số (không dùng class)
        # ────────────────────────────────────────────────
        btn = driver.find_element(
            By.XPATH,
            "//button[.//span[contains(text(), 'Hiện số')]]"
        )

        driver.execute_script("arguments[0].scrollIntoView({behavior:'smooth',block:'center'});", btn)
        human_sleep(0.4, 0.8)

        try:
            btn.click()
        except:
            driver.execute_script(
                "arguments[0].dispatchEvent(new MouseEvent('click',{bubbles:true}));",
                btn
            )

        # Chờ số điện thoại hiển thị (sau khi click sẽ là số thật)
        try:
            wait.until(lambda d: re.search(r"\d{7,}", btn.text or "") is not None)
            phone_text = (btn.text or "").strip()
        except:
            # fallback: tìm trong page source
            m = re.search(r"(0\d{8,10}|\+84\d{8,10})", driver.page_source.replace(" ", ""))
            phone_text = m.group(0) if m else ""

    except Exception:
        phone_text = ""

    # ────────────────────────────────────────────────
    # 2) Lấy contact name
    # ────────────────────────────────────────────────
    try:
        # Name nằm trong thẻ <b> bên trong vùng SellerInfo
        name_el = driver.find_element(
            By.XPATH,
            "//div[contains(@class,'SellerInfo')]/descendant::b[1]"
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
            (By.CSS_SELECTOR, "div.re__pr-map iframe")
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
        title_el = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "h1.re__pr-title")))
        item["title"] = title_el.text.strip()
    except Exception:
        item["title"] = ""

    specs_map = _extract_specs(driver)

    try:
        addr_el = wait.until(
            EC.presence_of_element_located((
                By.XPATH,
                "//svg[contains(@data-type,'monochrome')]/following-sibling::span[1]"
            ))
        )
        item["location"] = addr_el.text.strip()
    except Exception:
        item["location"] = ""


    item["description"] = _extract_description(driver, wait)
    item["images"] = _extract_images(driver)
    try:
        date_el = driver.find_element(By.XPATH, "//span[contains(text(), 'Cập nhật')]")
        date_text = date_el.text
        item["posted_date"] = utils.convert_time(date_text)
        
    except Exception:
        item["posted_date"] = ""

    item["specs"] = specs_map
    phone_text, contact_name = _extract_phone(driver, wait, human_sleep)
    item["agent_phone"] = phone_text
    item["agent_name"] = contact_name

    human_sleep(2, 4)
    try:
        driver.get(current_list_url)
        human_sleep(2, 4)
    except Exception:
        pass

    return item

