import json
import os


# Format:
# name: Tên file ảnh trong assets (không cần đuôi .png)
# target_lv: Cấp độ mục tiêu
# type_name: Tên hiển thị (để in log)

RUNTIME_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "build_order_runtime.json")
DEFAULT_RUNTIME_CONFIG = {
    "start_index": 0,
}

BUILD_SEQUENCE = [
    # --- Giai đoạn khởi đầu ---
    {"name": "kho_luong", "target_lv": 1, "type_name": "Kho Lương"},
    {"name": "kho", "target_lv": 1, "type_name": "Kho"},
    {"name": "y_quan", "target_lv": 1, "type_name": "Y Quán"},
    {"name": "dai_su_quan", "target_lv": 1, "type_name": "Đại Sứ Quán"},

    # --- Giai đoạn... ---
    {"name": "thanh_chinh", "target_lv": 2, "type_name": "Thành Chính"},
    {"name": "thanh_chinh", "target_lv": 3, "type_name": "Thành Chính"},
    {"name": "binh_doanh", "target_lv": 2, "type_name": "Binh Doanh"},
    {"name": "tiem_ren", "target_lv": 1, "type_name": "Tiệm Rèn"},

    # ...
    {"name": "thanh_chinh", "target_lv": 4, "type_name": "Thành Chính"},
    {"name": "thanh_chinh", "target_lv": 5, "type_name": "Thành Chính"},
    {"name": "thao_truong", "target_lv": 1, "type_name": "Thao Trường"},
    {"name": "tiem_ren", "target_lv": 2, "type_name": "Tiệm Rèn"},
    {"name": "tiem_ren", "target_lv": 3, "type_name": "Tiệm Rèn"},
    {"name": "kho", "target_lv": 2, "type_name": "Kho"},
    {"name": "kho", "target_lv": 3, "type_name": "Kho"},
    {"name": "kho_luong", "target_lv": 2, "type_name": "Kho Lương"},
    {"name": "kho_luong", "target_lv": 3, "type_name": "Kho Lương"},

    {"name": "thanh_chinh", "target_lv": 6, "type_name": "Thành Chính"},
    {"name": "thanh_chinh", "target_lv": 7, "type_name": "Thành Chính"},
    {"name": "cho", "target_lv": 1, "type_name": "Chợ"},

    {"name": "thanh_chinh", "target_lv": 8, "type_name": "Thành Chính"},
    {"name": "thanh_chinh", "target_lv": 9, "type_name": "Thành Chính"},
    {"name": "thanh_chinh", "target_lv": 10, "type_name": "Thành Chính"},
    {"name": "tuong_dien", "target_lv": 1, "type_name": "Tướng Diện"},
    {"name": "tiem_ren", "target_lv": 4, "type_name": "Tiệm Rèn"},
    {"name": "tiem_ren", "target_lv": 5, "type_name": "Tiệm Rèn"},
    {"name": "binh_doanh", "target_lv": 3, "type_name": "Binh Doanh"},
    {"name": "binh_doanh", "target_lv": 4, "type_name": "Binh Doanh"},
    {"name": "binh_doanh", "target_lv": 5, "type_name": "Binh Doanh"},
    {"name": "tuong_dien", "target_lv": 2, "type_name": "Tướng Diện"},
    {"name": "tuong_dien", "target_lv": 3, "type_name": "Tướng Diện"},
    {"name": "tuong_dien", "target_lv": 4, "type_name": "Tướng Diện"},
    {"name": "tuong_dien", "target_lv": 5, "type_name": "Tướng Diện"},
    {"name": "tiem_ren", "target_lv": 6, "type_name": "Tiệm Rèn"},
    {"name": "tiem_ren", "target_lv": 7, "type_name": "Tiệm Rèn"},
    {"name": "binh_doanh", "target_lv": 6, "type_name": "Binh Doanh"},
    {"name": "binh_doanh", "target_lv": 7, "type_name": "Binh Doanh"},
    {"name": "tiem_ren", "target_lv": 8, "type_name": "Tiệm Rèn"},
    {"name": "tiem_ren", "target_lv": 9, "type_name": "Tiệm Rèn"},
    {"name": "tiem_ren", "target_lv": 10, "type_name": "Tiệm Rèn"},
    {"name": "tuong_dien", "target_lv": 6, "type_name": "Tướng Diện"},
    {"name": "tuong_dien", "target_lv": 7, "type_name": "Tướng Diện"},
    {"name": "tuong_dien", "target_lv": 8, "type_name": "Tướng Diện"},
    {"name": "tuong_dien", "target_lv": 9, "type_name": "Tướng Diện"},
    {"name": "tuong_dien", "target_lv": 10, "type_name": "Tướng Diện"},
    {"name": "binh_doanh", "target_lv": 8, "type_name": "Binh Doanh"},
    {"name": "binh_doanh", "target_lv": 9, "type_name": "Binh Doanh"},
    {"name": "binh_doanh", "target_lv": 10, "type_name": "Binh Doanh"},
    {"name": "kho", "target_lv": 4, "type_name": "Kho"},
    {"name": "kho", "target_lv": 5, "type_name": "Kho"},
    {"name": "kho_luong", "target_lv": 4, "type_name": "Kho Lương"},
    {"name": "kho_luong", "target_lv": 5, "type_name": "Kho Lương"},

    {"name": "thanh_chinh", "target_lv": 11, "type_name": "Thành Chính"},
    {"name": "thanh_chinh", "target_lv": 12, "type_name": "Thành Chính"},
    {"name": "thanh_chinh", "target_lv": 13, "type_name": "Thành Chính"},
    {"name": "thanh_chinh", "target_lv": 14, "type_name": "Thành Chính"},
    {"name": "thanh_chinh", "target_lv": 15, "type_name": "Thành Chính"},
    {"name": "tiem_ren", "target_lv": 11, "type_name": "Tiệm Rèn"},
    {"name": "tiem_ren", "target_lv": 12, "type_name": "Tiệm Rèn"},
    {"name": "tiem_ren", "target_lv": 13, "type_name": "Tiệm Rèn"},
    {"name": "tiem_ren", "target_lv": 14, "type_name": "Tiệm Rèn"},
    {"name": "tuong_dien", "target_lv": 11, "type_name": "Tướng Diện"},
    {"name": "tuong_dien", "target_lv": 12, "type_name": "Tướng Diện"},
    {"name": "tuong_dien", "target_lv": 13, "type_name": "Tướng Diện"},
    {"name": "tuong_dien", "target_lv": 14, "type_name": "Tướng Diện"},
    {"name": "tuong_dien", "target_lv": 15, "type_name": "Tướng Diện"},
    {"name": "kho", "target_lv": 6, "type_name": "Kho"},
    {"name": "kho", "target_lv": 7, "type_name": "Kho"},
    {"name": "kho_luong", "target_lv": 6, "type_name": "Kho Lương"},
    {"name": "kho_luong", "target_lv": 7, "type_name": "Kho Lương"},

    {"name": "thanh_chinh", "target_lv": 16, "type_name": "Thành Chính"},
    {"name": "thanh_chinh", "target_lv": 17, "type_name": "Thành Chính"},
    {"name": "thanh_chinh", "target_lv": 18, "type_name": "Thành Chính"},
    {"name": "tiem_ren", "target_lv": 15, "type_name": "Tiệm Rèn"},
    {"name": "tiem_ren", "target_lv": 16, "type_name": "Tiệm Rèn"},
    {"name": "tiem_ren", "target_lv": 17, "type_name": "Tiệm Rèn"},
    {"name": "tiem_ren", "target_lv": 18, "type_name": "Tiệm Rèn"},

    {"name": "thanh_chinh", "target_lv": 19, "type_name": "Thành Chính"},
    {"name": "thanh_chinh", "target_lv": 20, "type_name": "Thành Chính"},
    {"name": "tiem_ren", "target_lv": 19, "type_name": "Tiệm Rèn"},
    {"name": "tiem_ren", "target_lv": 20, "type_name": "Tiệm Rèn"},
    {"name": "binh_doanh", "target_lv": 11, "type_name": "Binh Doanh"},
    {"name": "binh_doanh", "target_lv": 12, "type_name": "Binh Doanh"},
    {"name": "binh_doanh", "target_lv": 13, "type_name": "Binh Doanh"},
    {"name": "binh_doanh", "target_lv": 14, "type_name": "Binh Doanh"},
    {"name": "binh_doanh", "target_lv": 15, "type_name": "Binh Doanh"},
    {"name": "tuong_dien", "target_lv": 16, "type_name": "Tướng Diện"},
    {"name": "tuong_dien", "target_lv": 17, "type_name": "Tướng Diện"},
    {"name": "tuong_dien", "target_lv": 18, "type_name": "Tướng Diện"},
    {"name": "tuong_dien", "target_lv": 19, "type_name": "Tướng Diện"},
    {"name": "tuong_dien", "target_lv": 20, "type_name": "Tướng Diện"},
    {"name": "binh_doanh", "target_lv": 16, "type_name": "Binh Doanh"},
    {"name": "binh_doanh", "target_lv": 17, "type_name": "Binh Doanh"},
    {"name": "binh_doanh", "target_lv": 18, "type_name": "Binh Doanh"},
    {"name": "binh_doanh", "target_lv": 19, "type_name": "Binh Doanh"},
    {"name": "binh_doanh", "target_lv": 20, "type_name": "Binh Doanh"},
]


def _read_json_with_fallback(path):
    for enc in ("utf-8-sig", "utf-8"):
        try:
            with open(path, "r", encoding=enc) as f:
                return json.load(f)
        except Exception:
            continue
    raise RuntimeError(f"Khong doc duoc file json: {path}")


def load_build_order_runtime_config(path=RUNTIME_CONFIG_PATH):
    cfg = dict(DEFAULT_RUNTIME_CONFIG)
    if not os.path.exists(path):
        return cfg

    try:
        data = _read_json_with_fallback(path)
        if isinstance(data, dict):
            raw_start = data.get("start_index", cfg["start_index"])
            try:
                cfg["start_index"] = max(0, int(raw_start))
            except Exception:
                cfg["start_index"] = 0
    except Exception as exc:
        print(f"[BUILD-ORDER] Khong doc duoc config runtime '{path}': {exc}. Dung mac dinh.")

    return cfg


def resolve_build_sequence():
    runtime_cfg = load_build_order_runtime_config()
    total = len(BUILD_SEQUENCE)
    start_index = min(runtime_cfg.get("start_index", 0), total)
    return BUILD_SEQUENCE, start_index, runtime_cfg

