"""Module để load và sử dụng mapping từ file xlsx."""
import os
from pathlib import Path
from typing import Dict, Any, Optional

# Cache cho mappings
_mappings_cache: Dict[str, Dict[str, Any]] = {}


def _load_mappings():
    """Load tất cả mappings từ file xlsx và cache lại."""
    global _mappings_cache
    
    if _mappings_cache:
        return _mappings_cache
    
    try:
        from openpyxl import load_workbook
        
        # Tìm file xlsx
        project_root = Path(__file__).resolve().parents[1]
        xlsx_path = project_root / "output" / "map.xlsx"
        
        if not xlsx_path.exists():
            print(f"[Mapping] File {xlsx_path} không tồn tại")
            return {}
        
        wb = load_workbook(xlsx_path, data_only=True)
        
        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            mapping = {}
            
            # Bỏ qua row đầu tiên (header)
            rows = list(ws.iter_rows(values_only=True))
            if len(rows) < 2:
                continue
            
            # Tìm header row (có chứa "ID", "Value", "Slug")
            header_row_idx = None
            for idx, row in enumerate(rows):
                if row and any(cell and str(cell).upper() in ["ID", "VALUE", "SLUG"] for cell in row):
                    header_row_idx = idx
                    break
            
            if header_row_idx is None:
                continue
            
            # Parse data rows
            for row in rows[header_row_idx + 1:]:
                if not row or not any(cell for cell in row):
                    continue
                
                # Lấy ID, Value, Slug
                row_list = [cell for cell in row if cell is not None]
                if len(row_list) < 2:
                    continue
                
                try:
                    # ID có thể là số hoặc string
                    id_val = row_list[0]
                    if isinstance(id_val, float):
                        id_val = int(id_val) if id_val.is_integer() else id_val
                    elif isinstance(id_val, str) and id_val.replace('.', '').isdigit():
                        id_val = float(id_val)
                        id_val = int(id_val) if id_val.is_integer() else id_val
                    
                    value = str(row_list[1]).strip() if row_list[1] else None
                    slug = str(row_list[2]).strip() if len(row_list) > 2 and row_list[2] else None
                    
                    if value:
                        # Tạo mapping theo nhiều cách:
                        # 1. Value -> ID
                        # 2. Slug -> ID (nếu có)
                        # 3. Normalized value -> ID (loại bỏ dấu, lowercase)
                        mapping[value.lower()] = id_val
                        if slug:
                            mapping[slug.lower()] = id_val
                        
                        # Normalized version
                        import unicodedata
                        def normalize_text(text):
                            text = unicodedata.normalize('NFD', text)
                            text = text.encode('ascii', 'ignore').decode('utf-8')
                            return text.lower().strip()
                        
                        normalized = normalize_text(value)
                        if normalized != value.lower():
                            mapping[normalized] = id_val
                        
                        if slug:
                            normalized_slug = normalize_text(slug)
                            if normalized_slug != slug.lower():
                                mapping[normalized_slug] = id_val
                except Exception as e:
                    continue
            
            if mapping:
                _mappings_cache[sheet_name] = mapping
                print(f"[Mapping] Loaded {len(mapping)} entries from sheet '{sheet_name}'")
        
        wb.close()
        return _mappings_cache
        
    except ImportError:
        print("[Mapping] openpyxl chưa được cài đặt, không thể load mappings")
        return {}
    except Exception as e:
        print(f"[Mapping] Lỗi khi load mappings: {e}")
        return {}


def get_mapping(sheet_name: str, value: str) -> Optional[Any]:
    """
    Lấy ID từ mapping dựa trên value hoặc slug.
    
    Args:
        sheet_name: Tên sheet trong file xlsx (ví dụ: "real_estate_type_id")
        value: Giá trị cần tìm (có thể là value hoặc slug)
    
    Returns:
        ID tương ứng hoặc None nếu không tìm thấy
    """
    mappings = _load_mappings()
    
    # Thử với tên sheet gốc và tên sheet đã strip (để xử lý khoảng trắng)
    sheet_mapping = mappings.get(sheet_name, {})
    if not sheet_mapping:
        sheet_mapping = mappings.get(sheet_name.strip(), {})
    
    if not value:
        return None
    
    value_lower = value.lower().strip()
    
    # Tìm exact match
    if value_lower in sheet_mapping:
        return sheet_mapping[value_lower]
    
    # Tìm partial match
    for key, mapped_id in sheet_mapping.items():
        if value_lower in key or key in value_lower:
            return mapped_id
    
    return None


def get_all_mappings() -> Dict[str, Dict[str, Any]]:
    """Lấy tất cả mappings đã load."""
    return _load_mappings()

