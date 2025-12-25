from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Tuple
import requests
from urllib.parse import urlparse
from .. import config

def _update_sets_from_items(
    items: Iterable[dict[str, Any]],
    scraped_hrefs: set[str],
) -> None:
    """Update sets từ items, hỗ trợ cả format cũ và format mới (example.json)."""
    for it in items:
        # Format cũ: pid và href ở root level
        href = it.get("href")
        
        # Format mới: real_estate_code (từ pid) và href trong other_info
        if not href:
            other_info = it.get("other_info", {})
            if isinstance(other_info, dict):
                href = other_info.get("href")
        
        if href:
            scraped_hrefs.add(str(href))


def load_previous_results(
    output_dir: str,
    today: datetime,
) -> Tuple[set[str], set[str], list[dict[str, Any]]]:
    scraped_hrefs = set()
    all_results = []

    for root, dirs, files in os.walk(output_dir):
        for file in files:
            if not file.endswith(".json"):
                continue

            file_path = os.path.join(root, file)
            file_date_str = file[:-5]

            try:
                file_date = datetime.strptime(file_date_str, "%Y-%m-%d")
            except ValueError:
                continue

            if file_date > today:
                continue

            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                # Hỗ trợ cả format cũ (list) và format mới (object với key "data")
                if isinstance(data, list):
                    _update_sets_from_items(data, scraped_hrefs)
                    all_results.extend(data)
                elif isinstance(data, dict) and "data" in data:
                    items = data["data"]
                    if isinstance(items, list):
                        _update_sets_from_items(items, scraped_hrefs)
                        all_results.extend(items)
            except:
                continue

    return scraped_hrefs, all_results




def load_today_results(
    results_file: str,
    scraped_hrefs: set[str],
) -> list[dict[str, Any]]:
    if not os.path.exists(results_file):
        return []
    try:
        with open(results_file, "r", encoding="utf-8") as f:
            today_data = json.load(f)
            # Hỗ trợ cả format cũ (list) và format mới (object với key "data")
            if isinstance(today_data, list):
                _update_sets_from_items(today_data, scraped_hrefs)
                return today_data
            elif isinstance(today_data, dict) and "data" in today_data:
                items = today_data["data"]
                if isinstance(items, list):
                    _update_sets_from_items(items, scraped_hrefs)
                    return items
    except Exception:
        pass
    return []

def convert_paths(obj):
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, dict):
        return {k: convert_paths(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [convert_paths(x) for x in obj]
    return obj


def _parse_number_from_text(text: str) -> float | None:
    """Parse số từ text (ví dụ: '100 m²' -> 100.0, '5 tỷ' -> 5000000000)."""
    if not text or not isinstance(text, str):
        return None
    
    # Loại bỏ dấu phẩy, chấm (trừ dấu chấm thập phân)
    text_clean = text.replace(",", "").strip()
    
    # Tìm số
    match = re.search(r'(\d+(?:\.\d+)?)', text_clean)
    if not match:
        return None
    
    number = float(match.group(1))
    
    # Xử lý đơn vị (tỷ, triệu)
    if 'tỷ' in text_clean.lower() or 'ty' in text_clean.lower():
        number *= 1000000000
    elif 'triệu' in text_clean.lower() or 'trieu' in text_clean.lower():
        number *= 1000000
    
    return number


def _extract_area_number(area_text: str) -> float | None:
    if not area_text:
        return None

    text = str(area_text).strip()

    # Trường hợp có dấu chấm phân tách nghìn (ví dụ VN)
    if re.search(r'\d+\.\d{3}\b', text):  # match kiểu 8.800 hoặc 12.500, 120.000
        clean = text.replace('.', '').replace(',', '.')
        match = re.search(r'(\d+(?:\.\d+)?)', clean)
        return float(match.group(1)) if match else None

    # Trường hợp số thập phân: 8.8 hoặc 8,8
    text = text.replace(',', '.')
    match = re.search(r'(\d+(?:\.\d+)?)', text)
    return float(match.group(1)) if match else None



def _extract_bedroom_bathroom_floor(specs: dict, config: dict) -> tuple[int | None, int | None, int | None]:
    """Extract số phòng ngủ, phòng tắm, số tầng từ specs và config."""

    def _parse_int_from_text(text: Any) -> int | None:
        if text is None:
            return None
        value_str = str(text)
        match = re.search(r'(\d+)', value_str)
        if match:
            return int(match.group(1))
        value_lower = value_str.lower()
        word_map = {
            "một": 1,
            "mot": 1,
            "hai": 2,
            "ba": 3,
            "bốn": 4,
            "bon": 4,
            "năm": 5,
            "nam": 5,
            "sáu": 6,
            "sau": 6,
            "bảy": 7,
            "bay": 7,
            "tám": 8,
            "tam": 8,
            "chín": 9,
            "chin": 9
        }
        for word, num in word_map.items():
            if word in value_lower:
                return num
        return None

    bedroom = None
    bathroom = None
    floor = None

    def _update_counts(key: str, value: Any, allow_override: bool = False):
        nonlocal bedroom, bathroom, floor
        key_lower = str(key).lower()
        num = _parse_int_from_text(value)
        if num is None:
            return

        if ('số phòng ngủ' in key_lower or 'so phong ngu' in key_lower or 'bedroom' in key_lower) and (bedroom is None or allow_override):
            bedroom = num
        elif ('số phòng tắm' in key_lower or 'phong tam' in key_lower or 'bathroom' in key_lower or 'wc' in key_lower or "số phòng vệ sinh") and (bathroom is None or allow_override):
            bathroom = num
        elif ('tổng số tầng' in key_lower or 'lau' in key_lower or 'lầu' in key_lower or 'floor' in key_lower) and (floor is None or allow_override):
            floor = num

    for key, value in specs.items():
        _update_counts(key, value, allow_override=False)

    for key, value in config.items():
        _update_counts(key, value, allow_override=True)

    return bedroom, bathroom, floor


def _determine_sale_type(href: str) -> str:
    """Xác định sale_type từ URL (sell hoặc rent)."""
    if not href:
        return "sell"
    href_lower = str(href).lower()
    if "cho-thue" in href_lower or "cho-thuê" in href_lower:
        return "rent"
    return "sell"


def transform_to_example_format(item: dict[str, Any]) -> dict[str, Any]:
    """
    Transform item từ format hiện tại sang format example.json.
    Các trường không có trong mapping sẽ được đưa vào other_info.
    
    Nếu item đã ở format mới (có real_estate_code và không có pid ở root), 
    trả về item đó mà không transform lại.
    """
    # Kiểm tra xem item đã ở format mới chưa
    # Format mới có: real_estate_type_id, real_estate_code, sale_type, etc.
    # Format cũ có: pid, href ở root level
    if "real_estate_code" in item and "real_estate_type_id" in item:
        # Item đã ở format mới, không cần transform lại
        return item
    
    from .mapping import get_mapping, find_ward_key_loose
    
    specs = item.get("specs", {})
    config = item.get("config", {})
    href = item.get("href", "")
    title = item.get("title", "")
    location = item.get("location", "")
    
    # Extract các giá trị
    area_number = _extract_area_number(item.get("area", ""))
    price_number = _parse_number_from_text(item.get("price", ""))
    bedroom, bathroom, floor = _extract_bedroom_bathroom_floor(specs, config)
    
    # lat_long sẽ là map_coords (format "lat,lng")
    lat_long = item.get("map_coords", "")
    if lat_long and "," in lat_long:
        # Đảm bảo format đúng
        parts = lat_long.split(",")
        if len(parts) == 2:
            try:
                lat = float(parts[0].strip())
                lng = float(parts[1].strip())
                lat_long = f"{lat},{lng}"
            except:
                lat_long = None
        else:
            lat_long = None
    else:
        lat_long = None
    
    # Xác định price_unit (1 = tổng, 2 = theo tháng)
    price_unit = 1
    price_text = str(item.get("price", "")).lower()
    if "tháng" in price_text or "/tháng" in price_text:
        price_unit = 2
    
    # Tạo other_info chứa các trường không map được
    other_info = {}
    
    # Copy các trường không được map trực tiếp (comment lại các trường tạm thời không dùng)
    for key in ["pid", "href"]:
        if key in item and item[key]:
            other_info[key] = item[key]
    
    # Comment lại các trường có thể sử dụng trong tương lai
    # if item.get("thumbnail"):
    #     other_info["thumbnail"] = item["thumbnail"]
    # if item.get("price_per_m2"):
    #     other_info["price_per_m2"] = item["price_per_m2"]
    # if item.get("map_link"):
    #     other_info["map_link"] = item["map_link"]
    # if specs:
    #     other_info["specs"] = specs
    # if config:
    #     other_info["config"] = config
    
    # Map real_estate_type_id từ URL hoặc title
    real_estate_type_id = None
    href_lower = str(href).lower() if href else ""
    title_lower = str(title).lower() if title else ""
    
    # Tìm trong URL trước
    for key in ["nha-mat-pho-mat-tien", "nha-ngo-hem", "nha-biet-thu", "nha-pho-lien-ke", "nha-vuon", 
                "nha-thanh-ly", "nha-o-xa-hoi", "can-ho-chung-cu", "can-ho-duplex", "can-ho-penthouse", "can-ho-tap-the-cu-xa", 'dat-nen-dat-tho-cu',
                "dat-nen-du-an", "dat-nong-nghiep", "dat-cong-nghiep", "dat-thuong-mai-dich-vu", "dat-thanh-ly",
                "condotel", "homestay", "farmstay", "khach-san", "resort", "van-phong", "shophouse",
                "kho-nha-xuong","phong-tro", "mat-bang-kinh-doanh"
                ]:
        if key in href_lower:
            # Map từ slug
            real_estate_type_id = get_mapping("real_estate_type_id", key)
            if real_estate_type_id:
                break
    
    # Nếu không tìm thấy trong URL, tìm trong title
    if not real_estate_type_id:
        for key in ["chung cư", "căn hộ", "nhà riêng", "biệt thự", "nhà mặt phố",
                    "shophouse", "đất", "condotel", "kho", "nhà xưởng", "trang trại"]:
            if key in title_lower:
                real_estate_type_id = get_mapping("real_estate_type_id", key)
                if real_estate_type_id:
                    break
    
    # Map demand_id từ sale_type
    sale_type = _determine_sale_type(href)
    demand_id = get_mapping("demand_id", sale_type)
    if not demand_id:
        # Mặc định: 1 = bán, 2 = cho thuê
        demand_id = 1 if sale_type == "sell" else 2
    
    # Parse location để lấy province_id, district_id, ward_id
    province_id = None
    district_id = None
    ward_id = None
    
    if location:
        location_parts = [part.strip() for part in location.split(",") if part.strip()]
        # Thường format: "Phường/Xã, Quận/Huyện, Tỉnh/Thành phố"
        # Hoặc: "Đường, Phường/Xã, Quận/Huyện, Tỉnh/Thành phố"
        
        # Tìm từ cuối lên (tỉnh/thành phố thường ở cuối)
        for part in reversed(location_parts):
            part_clean = part.strip()
            if not province_id:
                province_id = get_mapping("province_id", part_clean)

        if not district_id and len(location_parts) >=2:
            district_id = find_ward_key_loose("district_mapping.json", name = location_parts[-2].replace("TP.","Thành phố").strip(), province_id=province_id)

        if len(location_parts) >=3:
            if not ward_id and district_id and province_id:
                ward_id = find_ward_key_loose("ward_mapping.json",name = location_parts[-3].strip(), province_id=province_id, district_id=district_id)
    
    # Map các infomation_* từ specs và config
    infomation_legal_docs_id = None
    infomation_hourse_status_id = None
    infomation_usage_condition_id = None
    infomation_location_type_id = None
    land_info_utilities_id = None
    land_info_security_id = None
    land_info_road_type_id = None
    
    # Tìm trong specs và config
    all_specs = {**specs, **config}
    for key, value in all_specs.items():
        key_lower = str(key).lower()
        value_str = str(value).lower()
        
        # Map giấy tờ pháp lý (ID 18=Sổ đỏ, 19=Sổ hồng, 20=Đang chờ sổ, 21=Hợp đồng mua bán)
        if not infomation_legal_docs_id and any(kw in key_lower for kw in ["giấy tờ", "pháp lý", "sổ đỏ", "sổ hồng", "phap ly", "giay to", "Đã có sổ", "da co so", "đang chờ sổ", "dang cho so", "Hợp đồng", "hop dong", "mua bán"]):
            # Thử map từ mapping file trước
            mapped_id = get_mapping("infomation_legal_docs_id ", value_str) or get_mapping("infomation_legal_docs_id", value_str)
            if mapped_id:
                infomation_legal_docs_id = mapped_id
            else:
                # Map trực tiếp từ giá trị
                if "sổ đỏ" in value_str or "so do" in value_str or "đã có sổ" in value_str or "da co so" in value_str:
                    infomation_legal_docs_id = 18
                elif "sổ hồng" in value_str or "so hong" in value_str:
                    infomation_legal_docs_id = 19
                elif "đang chờ sổ" in value_str or "dang cho so" in value_str or "chờ sổ" in value_str:
                    infomation_legal_docs_id = 20
                elif "hợp đồng" in value_str or "hop dong" in value_str or "mua bán" in value_str:
                    infomation_legal_docs_id = 21
        
        # Map tình trạng nhà
        if not infomation_hourse_status_id and any(kw in key_lower for kw in ["tình trạng", "tinh trang"]):
            infomation_hourse_status_id = get_mapping("infomation_hourse_status_id ", value_str) or get_mapping("infomation_hourse_status_id", value_str)
        
        # Map điều kiện sử dụng
        if not infomation_usage_condition_id and any(kw in key_lower for kw in ["điều kiện", "dieu kien", "sử dụng", "su dung"]):
            infomation_usage_condition_id = get_mapping("infomation_usage_condition_id", value_str)
        
        # Map loại vị trí
        if not infomation_location_type_id and any(kw in key_lower for kw in ["vị trí", "vi tri", "loại", "loai"]):
            infomation_location_type_id = get_mapping("infomation_location_type_id ", value_str) or get_mapping("infomation_location_type_id", value_str)
        
        # Map tiện ích
        if not land_info_utilities_id and any(kw in key_lower for kw in ["tiện ích", "tien ich", "tiện nghi", "tien nghi"]):
            land_info_utilities_id = get_mapping("land_info_utilities_id", value_str)
        
        # Map an ninh
        if not land_info_security_id and any(kw in key_lower for kw in ["an ninh", "an ninh", "bảo vệ", "bao ve"]):
            land_info_security_id = get_mapping("land_info_security_id", value_str)
        
        # Map loại đường
        if not land_info_road_type_id and any(kw in key_lower for kw in ["đường", "duong", "mặt tiền", "mat tien"]):
            land_info_road_type_id = get_mapping("land_info_road_type_id", value_str)
    
    # Tạo output theo format example.json
    output = {
        "real_estate_type_id": real_estate_type_id,
        "sale_type": sale_type,
        "demand_id": demand_id,
        "project_id": None,
        "province_id": province_id,
        "district_id": district_id,
        "ward_id": ward_id,
        "address_detail": item.get("location", ""),
        "lat_long": lat_long,
        # "real_estate_code": item.get("pid", ""),
        "year_built": None,  # Có thể có trong specs/config
        "handover_year": None,  # Có thể có trong specs/config
        "area": area_number,
        "area_unit": "m2" if area_number else None,
        "price": int(price_number) if price_number else 0,
        "price_unit": price_unit if price_unit and price_number > 0 else 3,
        "bedroom": bedroom,
        "bathroom": bathroom,
        "floor": floor,
        "length": None, 
        "width": None,  
        "lane_width": None,  
        "title": item.get("title", ""),
        "content": item.get("description", ""),
        "contact_type": 2,
        "contact_name": item.get("agent_name", ""),
        "contact_phone_number": item.get("agent_phone", "") if len(item.get("agent_phone", "")) < 15 else "",
        "paper_no": None, 
        "lot_no": None,  
        "status": 1,
        "brokerage_cooperation": None,
        "images": item.get("images", []) or [],
        "infomation_legal_docs_id": infomation_legal_docs_id if infomation_legal_docs_id is not None else None,
        "infomation_hourse_status_id": infomation_hourse_status_id if infomation_hourse_status_id is not None else [],
        "infomation_usage_condition_id": infomation_usage_condition_id if infomation_usage_condition_id is not None else [],
        "infomation_location_type_id": infomation_location_type_id if infomation_location_type_id is not None else [],
        "land_info_utilities_id": land_info_utilities_id if land_info_utilities_id is not None else [],
        "land_info_security_id": land_info_security_id if land_info_security_id is not None else [],
        "land_info_road_type_id": land_info_road_type_id if land_info_road_type_id is not None else None,
        "other_info": other_info if other_info else {}
    }
    

    important_fields = {"real_estate_type_id", "demand_id", "province_id", "district_id", "ward_id"}
    cleaned_output = {}
    for key, value in output.items():
        if value is not None or key in important_fields:
            cleaned_output[key] = value

    # Loại bỏ các trường array nếu rỗng (theo yêu cầu)
    optional_array_fields = [
        "infomation_hourse_status_id",
        "infomation_usage_condition_id",
        "infomation_location_type_id",
        "land_info_utilities_id",
        "land_info_security_id"
    ]
    for field in optional_array_fields:
        if field in cleaned_output and isinstance(cleaned_output[field], list) and not cleaned_output[field]:
            cleaned_output.pop(field)

    # Loại bỏ other_info nếu trống
    if "other_info" in cleaned_output and not cleaned_output["other_info"]:
        cleaned_output.pop("other_info")
    return cleaned_output

def save_results(
    results: list[dict[str, Any]],
    results_file: str,
    scraped_hrefs: set[str],
) -> None:
    unique: dict[str, dict[str, Any]] = {}
    for item in results:
        # Hỗ trợ cả format cũ và format mới để tạo key unique
        key = None
        
        # Format cũ: pid hoặc href ở root level
        if "pid" in item:
            key = item.get("pid")
        elif "href" in item:
            key = item.get("href")
        
        # Format mới: real_estate_code hoặc href trong other_info
        if not key:
            key = item.get("real_estate_code")
        if not key:
            other_info = item.get("other_info", {})
            if isinstance(other_info, dict):
                key = other_info.get("href") or other_info.get("pid")
        
        if not key:
            # fallback to object id to avoid overwriting
            key = f"tmp-{id(item)}"
        
        unique[str(key)] = item

    final = list(unique.values())
    
    # Transform sang format example.json
    transformed_data = [transform_to_example_format(item) for item in final]
               
    # Wrap trong object với key "data"
    output = {"data": transformed_data}
    
    with open(results_file, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    _update_sets_from_items(final, scraped_hrefs)
    print(f"Saved {len(final)} items to {results_file}")

