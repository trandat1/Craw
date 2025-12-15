"""Module chung chứa logic scraping, có thể dùng cho cả CLI và Web interface."""
import time
import re
import unicodedata
from datetime import datetime
from urllib.parse import urlencode, urlparse, parse_qs, urlunparse, urljoin
from typing import Optional, Dict, Any, Callable

from .. import config
from ..browser import init_driver
from .collectors.detail import open_detail_and_extract
from .collectors.listing import collect_list_items
from .storage import load_previous_results, load_today_results, save_results
from .utils import human_sleep
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from . import utils

def find_and_click_next_page(driver):
    """Tìm và click nút trang kế tiếp theo HTML phân trang mới của Chợ Tốt."""
    prev_url = driver.current_url

    try:
        # Lấy trang hiện tại (nằm trong <span class="Paging_activePTY__jIVHK">)
        current_page_el = driver.find_element(By.CSS_SELECTOR, ".Paging_activePTY__jIVHK")
        current_page = int(current_page_el.text.strip())
    except:
        current_page = 1

    # Tạo selector tìm page+1
    next_page_selector = f'a[href*="page={current_page + 1}"]'

    next_elem = None
    try:
        next_elem = driver.find_element(By.CSS_SELECTOR, next_page_selector)
    except:
        pass

    # Nếu không có link page=next → thử nút next arrow
    if not next_elem:
        try:
            next_elem = driver.find_element(By.CSS_SELECTOR, ".Paging_rightIcon__3p8MS")
        except:
            print(f"[Pagination] No next page after page {current_page}")
            return False

    # Click hoặc load href
    try:
        if next_elem.tag_name == "a":
            next_href = next_elem.get_attribute("href")
            full_url = urljoin(prev_url, next_href)
            driver.get(full_url)
        else:
            next_elem.click()
    except Exception as e:
        print("[Pagination] Error moving to next page:", e)
        return False

    # Chờ page thay đổi
    for _ in range(30):
        time.sleep(0.5)
        if driver.current_url != prev_url:
            return True

    return False

def find_exact_url_from_sidebar(driver, wait, location_filter, base_url):
    """
    Tìm URL chính xác từ sidebar khi URL chuyển về dạng generic.
    
    Quy trình:
    1. Phát hiện URL generic (ví dụ: /nha-dat-ban-ha-noi)
    2. Quay lại URL gốc (base_url) để tìm trong sidebar
    3. Tìm link khớp với location filter trong sidebar
    4. Hỗ trợ tìm theo nhiều cấp độ (tỉnh → quận → phường) nếu cần
    
    Args:
        driver: Selenium driver
        wait: WebDriverWait
        location_filter: Chuỗi location filter (có thể có nhiều cấp: "Hà Nội", "Hà Nội Đống Đa", "Hà Nội Đống Đa Khâm Thiên")
        base_url: URL gốc trước khi search (ví dụ: https://batdongsan.com.vn/ban-can-ho-chung-cu-mini)
    
    Returns:
        URL chính xác hoặc None nếu không tìm thấy
    """
    try:
        def normalize_text(text):
            """Loại bỏ dấu và đưa về lowercase."""
            text = unicodedata.normalize('NFD', text)
            text = text.encode('ascii', 'ignore').decode('utf-8')
            return text.lower().strip()

        current_url = driver.current_url

        # Kiểm tra URL generic
        if "/nha-dat-ban" not in current_url and "/nha-dat-cho-thue" not in current_url:
            return None

        print(f"[Filter] Phát hiện URL generic: {current_url}")
        print(f"[Filter] Quay lại URL gốc: {base_url} để tìm URL chính xác...")

        # Quay lại base URL
        driver.get(base_url)
        human_sleep(3, 5)

        parsed = urlparse(base_url)
        property_type_path = parsed.path
        property_keywords = property_type_path.replace("/ban-", "").replace("/cho-thue-", "").replace("-", " ").split()

        # Parse location
        location_normalized = normalize_text(location_filter)
        location_words = set(location_normalized.split())

        # Lấy sidebar box
        sidebar_boxes = driver.find_elements(By.CSS_SELECTOR, ".re__product-count-box")
        if not sidebar_boxes:
            print("[Filter] Không tìm thấy sidebar box")
            return None

        # Chọn box theo loại BĐS
        target_box = None
        for box in sidebar_boxes:
            try:
                title = box.find_element(By.CSS_SELECTOR, ".re__sidebar-box-title")
                title_text = title.text.lower()
                matches = sum(1 for kw in property_keywords if kw in title_text)

                if matches >= 2 or "bán" in title_text or "cho thuê" in title_text:
                    target_box = box
                    print(f"[Filter] Tìm thấy sidebar box phù hợp: {title.text}")
                    break
            except:
                continue

        if not target_box:
            print("[Filter] Không tìm thấy sidebar box phù hợp, dùng box đầu tiên")
            target_box = sidebar_boxes[0]

        # -----------------------------------------------------------
        # FIX: MỞ RỘNG "XEM THÊM" (link bị ẩn nên cần mở)
        # -----------------------------------------------------------
        try:
            view_more_btn = target_box.find_element(
                By.CSS_SELECTOR,
                ".re__sidebar-box-content .re__view-more"
            )

            if view_more_btn.is_displayed():
                driver.execute_script("arguments[0].click();", view_more_btn)
                human_sleep(1, 2)
                print("[Filter] Đã click 'Xem thêm'")
        except Exception as e:
            print("[Filter] Không thể click 'Xem thêm':", e)

        # Lấy link location
        location_links = target_box.find_elements(By.CSS_SELECTOR, "a.re__link-se")
        if not location_links:
            print("[Filter] Không tìm thấy link location")
            return None

        matched_link = None
        best_score = 0

        for link in location_links:
            link_text = link.text
            link_href = link.get_attribute("href")

            # Clean: bỏ (xxx)
            link_clean = re.sub(r'\s*\(\d+\)\s*', '', link_text).strip()
            link_norm = normalize_text(link_clean)
            link_words = set(link_norm.split())

            score = 0

            # 1) Khớp tuyệt đối
            if link_norm == location_normalized:
                score = 100

            else:
                # 2) Khớp theo tập từ
                if link_words == location_words:
                    score = 95
                else:
                    common = link_words.intersection(location_words)
                    cnt = len(common)

                    if cnt >= 2:
                        score = 80 + (cnt - 2) * 5
                    elif cnt == 1:
                        score = 20  # tăng nhẹ để phân biệt
                    else:
                        score = 0

            if score > best_score:
                best_score = score
                matched_link = link
                print(f"[Filter] → Match: {link_clean} | score={score} | href={link_href}")

        # Đủ điểm để chấp nhận
        if matched_link and best_score >= 50:
            href = matched_link.get_attribute("href")
            if href.startswith("http"):
                exact_url = href
            else:
                exact_url = f"https://batdongsan.com.vn{href}"
            print(f"[Filter] Tìm thấy URL chính xác: {exact_url}")
            return exact_url

        print("[Filter] Không tìm được link phù hợp")
        return None

    except Exception as e:
        print(f"[Filter] Lỗi trong find_exact_url_from_sidebar: {e}")
        return None

def apply_search_filters(driver, wait, location_filter, base_url=None):
    """
    Áp dụng filter địa điểm vào ô tìm kiếm và tìm URL chính xác nếu cần.
    
    Args:
        driver: Selenium driver
        wait: WebDriverWait
        location_filter: Chuỗi location filter
        base_url: URL gốc trước khi search (để tìm URL chính xác)
    
    Returns:
        Tuple (success: bool, final_url: str) - final_url là URL sau khi search (có thể đã được điều chỉnh)
    """
    if not location_filter or not location_filter.strip():
        return False, None
    
    try:
        # Tìm ô tìm kiếm
        search_input = wait.until(
            EC.presence_of_element_located((By.ID, "SuggestionSearch"))
        )

        # Xóa nội dung cũ và nhập filter
        search_input.clear()
        search_input.send_keys(location_filter)
        human_sleep(1, 2)
        
        # Tìm và click nút tìm kiếm
        search_button = driver.find_element(By.ID, "btnSearch")
        search_button.click()
        
        # Chờ trang load
        human_sleep(3, 5)
        
        final_url = driver.current_url
        print(f"[Filter] URL sau khi search: {final_url}")
        
        # Kiểm tra xem URL có phải là generic không
        # Nếu là generic (ví dụ: /nha-dat-ban-ha-noi), cần tìm URL chính xác từ sidebar
        # Lưu ý: Trang bán đất (/ban-dat) không cần áp dụng logic này vì đã hoạt động đúng
        if base_url and ("/nha-dat-ban" in final_url or "/nha-dat-cho-thue" in final_url or "/ban-nha" in final_url):
            # Bỏ qua logic này cho trang bán đất
            # if "/ban-dat" in base_url:
            #     print(f"[Filter] Trang bán đất, bỏ qua logic tìm URL chính xác từ sidebar")
            # else:
            
                print(f"[Filter] URL là generic, đang tìm URL chính xác từ sidebar...")
                exact_url = find_exact_url_from_sidebar(driver, wait, location_filter, base_url)
                if exact_url:
                    final_url = exact_url
                    print(f"[Filter] Sử dụng URL chính xác từ sidebar: {final_url}")
                
                else:
                    return False, None
                #     print(f"[Filter] Không tìm thấy URL chính xác, giữ nguyên URL: {final_url}")
        else:
            print(f"[Filter] URL đã đúng, không cần điều chỉnh: {final_url}")
        
        print(f"[Filter] Đã áp dụng filter địa điểm: {location_filter}, final URL: {final_url}")
        return True, final_url
        
    except Exception as e:
        print(f"[Filter] Lỗi khi áp dụng filter địa điểm: {e}")
        return False, None


def build_url_with_filters(base_url, filters):
    """Xây dựng URL với các filter dạng query params."""
    if not filters:
        return base_url
    
    # Parse URL hiện tại
    parsed = urlparse(base_url)
    query_params = parse_qs(parsed.query)
    
    # Thêm các filter vào query params
    # gtn: giá từ
    if filters.get("price_from"):
        query_params["gtn"] = [filters["price_from"]]
    
    # gcn: giá đến
    if filters.get("price_to"):
        query_params["gcn"] = [filters["price_to"]]
    
    # dtnn: diện tích từ
    if filters.get("area_from"):
        query_params["dtnn"] = [filters["area_from"]]
    
    # dtln: diện tích đến
    if filters.get("area_to"):
        query_params["dtln"] = [filters["area_to"]]
    
    # h: hướng nhà
    if filters.get("direction"):
        query_params["h"] = [filters["direction"]]
    
    # frontage: mặt tiền (0-6: 0=Tất cả, 1=Dưới 5m, 2=5-7m, 3=7-10m, 4=10-12m, 5=12-15m, 6=Trên 12m)
    if filters.get("frontage") is not None and filters.get("frontage") != "":
        query_params["frontage"] = [str(filters["frontage"])]
    
    # road: đường vào (0-6: 0=Tất cả, 1=Dưới 5m, 2=5-7m, 3=7-10m, 4=10-12m, 5=12-15m, 6=Trên 12m)
    if filters.get("road") is not None and filters.get("road") != "":
        query_params["road"] = [str(filters["road"])]
    
    # rs: số phòng ngủ (có thể nhiều giá trị, ví dụ: rs=1,2)
    if filters.get("rooms"):
        rooms_value = filters["rooms"]
        # Nếu là string có dấu phẩy, giữ nguyên; nếu không, chuyển thành string
        if isinstance(rooms_value, str):
            query_params["rs"] = [rooms_value]
        else:
            query_params["rs"] = [str(rooms_value)]
    
    # bcdir: hướng ban công (1=Đông, 2=Tây, 3=Nam, 4=Bắc, 5=Đông Bắc, 6=Tây Bắc, 7=Tây Nam, 8=Đông Nam)
    if filters.get("bcdir") is not None and filters.get("bcdir") != "":
        query_params["bcdir"] = [str(filters["bcdir"])]
    
    # Xây dựng lại URL
    new_query = urlencode(query_params, doseq=True)
    new_parsed = parsed._replace(query=new_query)
    return urlunparse(new_parsed)


def scrape_url(
    driver,
    wait,
    base_url,
    scraped_hrefs,
    all_results,
    results_file,
    filters: Optional[Dict[str, Any]] = None,
    status_callback: Optional[Dict[str, Any]] = None
):
    """Scrape một URL cụ thể với filter tùy chọn."""
    print(f"\n{'='*60}")
    print(f"Starting scrape for URL: {base_url}")
    print(f"{'='*60}\n")
    
    try:
        # ===============================================================
        # 1) LOAD TRANG GỐC
        # ===============================================================
        driver.get(base_url)
        human_sleep(3, 6)

        # ===============================================================
        # 2) NẾU CÓ LOCATION → TÌM LOCATION TRƯỚC
        # ===============================================================
        if filters and filters.get("location"):
            applied, location_url = apply_search_filters(driver, wait, filters["location"], base_url)
            human_sleep(2, 4)

            if applied and location_url:
                # cập nhật base_url bằng URL sau khi tìm kiếm location (có thể đã được điều chỉnh từ sidebar)
                base_url = location_url
                print("[URL] Base URL mới sau location:", base_url)
                
                # Nếu URL đã được điều chỉnh, load lại trang với URL chính xác
                if location_url != driver.current_url:
                    driver.get(location_url)
                    human_sleep(3, 5)
            else:
                print("[Filter] Không thể áp dụng filter location, bỏ qua URL này.")
                return None

        # ===============================================================
        # 3) XÂY DỰNG URL CUỐI CÙNG VỚI QUERY FILTER KHÁC
        # ===============================================================
        
        url_with_filters = build_url_with_filters(base_url, filters)
        print("[URL] URL cuối cùng để scrape:", url_with_filters)

        # ===============================================================
        # 4) LOAD URL ĐÃ BAO GỒM LOCATION + FILTERS
        # ===============================================================
        driver.get(url_with_filters)
        human_sleep(3, 6)

        # ===============================================================
        # 5) BẮT ĐẦU SCRAPE
        # ===============================================================
        page_idx = 0
        max_pages = filters.get("max_pages", config.MAX_PAGES) if filters else config.MAX_PAGES
        max_items_per_page = filters.get("max_items_per_page", config.MAX_ITEMS_PER_PAGE) if filters else config.MAX_ITEMS_PER_PAGE
        
        while page_idx < max_pages:
            page_idx += 1
            if status_callback:
                status_callback["current_page"] = page_idx
                status_callback["progress"] = f"Đang xử lý trang {page_idx}/{max_pages}"
            
            print(f"=== PROCESS PAGE {page_idx} ===")
            human_sleep(1, 3)
            current_list_url = driver.current_url

            collected, total_cards, skipped_pid, skipped_href = collect_list_items(
                driver,
                scraped_hrefs,
                max_items_per_page,
                config.LIST_SCROLL_STEPS,
            )

            if not collected:
                print(
                    f"No new items found on this page (cards={total_cards}, skipped_pid={skipped_pid}, skipped_href={skipped_href})."
                )
                if page_idx >= max_pages:
                    print("Reached max pages, stopping.")
                    break
                print("Attempting to move to next page despite duplicates...")
                if not find_and_click_next_page(driver):
                    print("No further pages available, stopping.")
                    break
                continue

            print(f"Collected {len(collected)} new items meta on list page.")

            for i, item in enumerate(collected, start=1):
                if status_callback:
                    status_callback["total_items"] = len(all_results) + i
                    status_callback["progress"] = f"Trang {page_idx}/{max_pages} - Item {i}/{len(collected)}"
                
                print(f"[Page {page_idx}] Item {i}/{len(collected)} - PID {item.get('pid')}")
                human_sleep(2, 5)
                try:
                    full = open_detail_and_extract(
                        driver,
                        wait,
                        item,
                        current_list_url=current_list_url,
                        screenshot_dir=config.SCREENSHOT_DIR,
                        detail_scroll_steps=config.DETAIL_SCROLL_STEPS,
                        human_sleep=human_sleep,
                    )
                    # Lọc theo ngày
                    if filters:
                        posted_date_from = utils.normalize_date(filters.get("posted_date_from"))
                        expiration_date  = utils.normalize_date(full.get("expiration_date", ""))
                        if expiration_date and expiration_date < posted_date_from:
                            continue


                    all_results.append(full)
                
                    if full.get("href"):
                        scraped_hrefs.add(full.get("href"))
                    print(f"  -> phone: {full.get('agent_phone')}, images: {len(full.get('images', []))}")
                except Exception as e:
                    print("  -> error on detail:", e)
                human_sleep(1, 3)

            save_results(all_results, results_file, scraped_hrefs)
            
            if status_callback:
                status_callback["progress"] = f"Đã lưu {len(all_results)} items. Nghỉ {config.PAGE_COOLDOWN_SECONDS/60:.1f} phút..."
            
            print(f"Sleeping {config.PAGE_COOLDOWN_SECONDS/60:.1f} minutes before next page...")
            time.sleep(config.PAGE_COOLDOWN_SECONDS)
            
            if page_idx >= max_pages:
                break
            if not find_and_click_next_page(driver):
                break

    except Exception as e:
        print(f"Error scraping URL {base_url}: {e}")
        raise



def run_scraper(
    base_urls,
    filters: Optional[Dict[str, Any]] = None,
    debugger_address: Optional[str] = None,
    status_callback: Optional[Dict[str, Any]] = None
):
    """
    Hàm chính để chạy scraper.
    
    Args:
        base_urls: List các URL hoặc string URL đơn
        filters: Dict chứa các filter (location, price_from, price_to, area_from, area_to, direction, frontage, road, max_pages, max_items_per_page)
        debugger_address: Địa chỉ Chrome debugger (mặc định từ config)
        status_callback: Dict để cập nhật trạng thái (cho web interface)
    
    Returns:
        Dict chứa total_items và results_file
    """
    today, _, results_file = config.prepare_output_paths(datetime.now(), filters)
    
    scraped_pids, scraped_hrefs, _ = load_previous_results(config.OUTPUT_DIR, today)
    all_results = load_today_results(results_file, scraped_hrefs)
    # if filters:
    #     scraped_pids, scraped_hrefs, _ = load_previous_results(config.OUTPUT_DIR_FILTER, today)
    #     all_results = load_today_results(results_file, scraped_pids, scraped_hrefs)

    if all_results:
        print(
            f"Loaded {len(scraped_pids)} pids, {len(scraped_hrefs)} hrefs "
            f"and {len(all_results)} items from {results_file}"
        )
    
    driver, wait = init_driver(
        debugger_address or config.DEBUGGER_ADDRESS,
        config.PAGE_LOAD_TIMEOUT,
        config.WAIT_TIMEOUT
    )
    
    try:
        # Xử lý base_urls có thể là string hoặc list
        if isinstance(base_urls, str):
            base_urls = [base_urls]
        elif not isinstance(base_urls, list):
            raise ValueError(f"base_urls phải là string hoặc list, nhận được: {type(base_urls)}")
        
        for url_idx, base_url in enumerate(base_urls, start=1):
            if status_callback:
                status_callback["current_url"] = base_url
                status_callback["progress"] = f"URL {url_idx}/{len(base_urls)}: {base_url}"
            
            print(f"\n{'#'*60}")
            print(f"URL {url_idx}/{len(base_urls)}: {base_url}")
            print(f"{'#'*60}")
            
            try:
                scrape_url(
                    driver,
                    wait,
                    base_url,
                    scraped_pids,
                    scraped_hrefs,
                    all_results,
                    results_file,
                    filters=filters,
                    status_callback=status_callback
                )
            except Exception as e:
                print(f"Error processing URL {base_url}: {e}")
                if status_callback:
                    status_callback["error"] = str(e)
                print("Continuing with next URL...")
                continue
            
            # Nghỉ giữa các URLs (trừ URL cuối cùng)
            if url_idx < len(base_urls):
                print(f"\nCompleted URL {url_idx}/{len(base_urls)}. Sleeping before next URL...")
                time.sleep(config.PAGE_COOLDOWN_SECONDS)
                
    except KeyboardInterrupt:
        print("\nScraping interrupted by user. Saving current results...")
        save_results(all_results, results_file, scraped_pids, scraped_hrefs)
    finally:
        driver.quit()
    
    return {
        "total_items": len(all_results),
        "results_file": str(results_file),
        "url":base_url
    }

