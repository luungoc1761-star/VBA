#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
SCRIPT 1: BATCH DATA PROCESSOR (LỌC & TÍNH TOÁN DỮ LIỆU CẤN TRỪ TỒN KHO)
================================================================================
Nhiệm vụ:
  1. Đọc file nguồn 'Stock Balance With Batch.xlsx'.
  2. Lọc các dòng âm tại Kho 50 và Kho 62.
  3. Lọc nguồn tồn dương tại Kho 61 và Kho 01 (theo đúng Stock Code).
  4. Lựa chọn các batch có số lượng nhỏ nhất trước (Smallest Qty First).
  5. Cộng dồn các batch nguyên vẹn cho đến khi đủ số lượng âm cần trừ.
     Nếu batch tiếp theo phải tách lẻ thì tạm bỏ qua (không tách batch).
  6. Xuất ra:
     - auto_input_queue.json (Dữ liệu hàng đợi cho Auto-Typer GUI)
     - auto_input_queue.xlsx (Bảng Excel chi tiết cấn trừ)
     - report_unmatched_shortage.xlsx (Báo cáo danh sách chưa cấn trừ xong)
================================================================================
"""

import sys
import os
import json
from datetime import datetime
import pandas as pd
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def process_stock_data(input_file="Stock Balance With Batch.xlsx"):
    log(f"Bắt đầu xử lý file dữ liệu: {input_file}")
    if not os.path.exists(input_file):
        log(f"LỖI: Không tìm thấy file '{input_file}'. Vui lòng kiểm tra lại đường dẫn.")
        return False

    # 1. Đọc dữ liệu từ file Excel (bỏ 4 dòng tiêu đề đầu)
    log("Đang đọc và phân tích cấu trúc bảng tính...")
    try:
        df = pd.read_excel(input_file, skiprows=4)
    except Exception as e:
        log(f"Lỗi khi đọc file Excel: {e}")
        return False

    # Chuẩn hóa tên cột
    df.columns = [str(c).strip() for c in df.columns]
    
    # Kiểm tra các cột bắt buộc
    required_cols = ['Stock Code', 'Warehouse', 'BATCH', 'Qty']
    for col in required_cols:
        if col not in df.columns:
            log(f"LỖI: Thiếu cột bắt buộc '{col}' trong file nguồn!")
            return False

    # Chuẩn hóa kiểu dữ liệu
    df['Stock Code'] = df['Stock Code'].astype(str).str.strip()
    df['Warehouse'] = df['Warehouse'].astype(str).str.strip().replace({'1': '01', '1.0': '01'})
    df['BATCH'] = df['BATCH'].astype(str).str.strip()
    df['BIN'] = df['BIN'].fillna('').astype(str).str.strip() if 'BIN' in df.columns else ''
    df['Qty_num'] = pd.to_numeric(df['Qty'], errors='coerce').fillna(0)
    if 'CREATEDATE' in df.columns:
        df['CREATEDATE'] = pd.to_datetime(df['CREATEDATE'], errors='coerce')

    # 2. Phân loại nhóm Âm và Dương theo quy tắc nghiệp vụ
    # Nhóm Âm: Kho 50 và Kho 62, Qty < 0
    neg_mask = (df['Qty_num'] < 0) & (df['Warehouse'].isin(['50', '62']))
    neg_df = df[neg_mask].copy()

    # Nhóm Dương: Kho 61 và Kho 01, Qty > 0
    pos_mask = (df['Qty_num'] > 0) & (df['Warehouse'].isin(['61', '01']))
    pos_df = df[pos_mask].copy()

    log(f"-> Tổng số dòng âm (Kho 50 & 62): {len(neg_df):,} dòng | Tổng số lượng âm: {abs(neg_df['Qty_num'].sum()):,.0f}")
    log(f"-> Tổng số dòng dương khả dụng (Kho 61 & 01): {len(pos_df):,} dòng | Tổng tồn dương: {pos_df['Qty_num'].sum():,.0f}")

    # 3. Gom nhóm theo Stock Code và Target Warehouse
    neg_grouped = neg_df.groupby(['Stock Code', 'Warehouse'])['Qty_num'].sum().reset_index()
    neg_grouped = neg_grouped.sort_values(by=['Stock Code', 'Warehouse'])

    available_pos = pos_df.copy()
    queue_actions = []
    skipped_records = []
    
    step_counter = 1

    for _, neg_row in neg_grouped.iterrows():
        sc = neg_row['Stock Code']
        target_wh = neg_row['Warehouse']  # '50' hoặc '62'
        target_qty = abs(neg_row['Qty_num'])

        # Lấy các batch dương của Stock Code này trong Kho 61 và 01
        cand_pos = available_pos[available_pos['Stock Code'] == sc].sort_values(by='Qty_num', ascending=True)

        cur_sum = 0
        allocated_batches = []

        for _, pos_row in cand_pos.iterrows():
            b_qty = pos_row['Qty_num']
            b_name = pos_row['BATCH']
            source_wh = pos_row['Warehouse']

            if cur_sum + b_qty <= target_qty:
                # Lấy trọn vẹn batch này
                cur_sum += b_qty
                allocated_batches.append({
                    "step": step_counter,
                    "stock_code": sc,
                    "target_warehouse": target_wh,
                    "batch": b_name,
                    "source_warehouse": source_wh,
                    "qty": int(b_qty),
                    "bin": "01",
                    "status": "READY"
                })
                step_counter += 1
                # Xóa batch này khỏi kho khả dụng để không bị dùng trùng
                available_pos = available_pos[available_pos['BATCH'] != b_name]
            else:
                # Nếu lấy batch này sẽ bị vượt số âm (cần tách lẻ) -> Theo quy tắc: TẠM BỎ QUA
                pass

        queue_actions.extend(allocated_batches)
        rem_missing = target_qty - cur_sum

        if rem_missing > 0:
            skipped_records.append({
                "Stock Code": sc,
                "Kho Bị Âm": target_wh,
                "Tổng Số Lượng Âm": int(target_qty),
                "Đã Bù Trọn Vẹn": int(cur_sum),
                "Còn Thiếu (Chờ Tách Lẻ/Nhập Thêm)": int(rem_missing),
                "Tỷ Lệ Bù (%)": round(cur_sum / target_qty * 100, 1) if target_qty > 0 else 0,
                "Lý Do": "Các lô dương còn lại có số lượng lớn hơn phần thiếu (Cần tách lẻ) hoặc hết tồn"
            })

    total_offset_qty = sum(a['qty'] for a in queue_actions)
    total_neg_qty = abs(neg_df['Qty_num'].sum())

    log(f"-> Đã tạo thành công: {len(queue_actions)} lượt nhập liệu hợp lệ")
    log(f"-> Tổng số lượng giải quyết ngay: {total_offset_qty:,.0f} / {total_neg_qty:,.0f} ({total_offset_qty/total_neg_qty*100:.1f}%)")
    log(f"-> Số mã vật tư còn phần thiếu cần tách lẻ/theo dõi: {len(skipped_records)}")

    # 4. Xuất file auto_input_queue.json
    output_json = {
        "metadata": {
            "created_at": datetime.now().isoformat(),
            "source_file": input_file,
            "total_actions": int(len(queue_actions)),
            "total_offset_qty": int(total_offset_qty),
            "total_negative_qty": int(total_neg_qty),
            "offset_percentage": float(round(total_offset_qty / total_neg_qty * 100, 2)) if total_neg_qty > 0 else 0.0
        },
        "actions": queue_actions
    }
    with open("auto_input_queue.json", "w", encoding="utf-8") as f:
        json.dump(output_json, f, ensure_ascii=False, indent=2)
    log(" Đã xuất file hàng đợi: auto_input_queue.json")

    # 5. Xuất file auto_input_queue.xlsx đẹp mắt
    excel_queue_data = []
    for item in queue_actions:
        excel_queue_data.append({
            "STT": item["step"],
            "Mã Vật Tư (Stock Code)": item["stock_code"],
            "Mã Lô Dương (Batch)": item["batch"],
            "Kho Nguồn": item["source_warehouse"],
            "Kho Cấn Trừ (Target WH)": item["target_warehouse"],
            "Số Lượng Cấn Trừ (Qty)": item["qty"],
            "Vị Trí Kệ (BIN)": item["bin"],
            "Quy Trình Gõ Form iScala": f"Gõ [{item['batch']}] -> Enter -> Gõ [{item['target_warehouse']}] -> Enter -> Gõ [{item['qty']}] -> Enter -> Gõ [01] -> Enter x 4"
        })
    queue_df = pd.DataFrame(excel_queue_data)
    
    with pd.ExcelWriter("auto_input_queue.xlsx", engine="openpyxl") as writer:
        queue_df.to_excel(writer, sheet_name="Danh Sach Nhap Lieu", index=False)
        
        # Định dạng cột và màu sắc
        ws = writer.sheets["Danh Sach Nhap Lieu"]
        header_fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
        header_font = Font(name="Segoe UI", size=11, bold=True, color="FFFFFF")
        thin_border = Border(
            left=Side(style='thin', color='D9D9D9'),
            right=Side(style='thin', color='D9D9D9'),
            top=Side(style='thin', color='D9D9D9'),
            bottom=Side(style='thin', color='D9D9D9')
        )
        
        for col_num, col in enumerate(ws.columns, 1):
            max_len = 0
            for cell in col:
                cell.font = Font(name="Segoe UI", size=10)
                cell.border = thin_border
                cell.alignment = Alignment(vertical="center")
                if cell.row == 1:
                    cell.fill = header_fill
                    cell.font = header_font
                    cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
                val_str = str(cell.value or '')
                max_len = max(max_len, len(val_str))
            col_letter = get_column_letter(col_num)
            ws.column_dimensions[col_letter].width = max(max_len + 4, 12)
            
    log(" Đã xuất file bảng tính: auto_input_queue.xlsx")

    # 6. Xuất file report_unmatched_shortage.xlsx
    skipped_df = pd.DataFrame(skipped_records)
    summary_df = pd.DataFrame([
        {"Chỉ Tiêu": "Tổng số dòng âm tại Kho 50 & 62", "Giá Trị": f"{len(neg_df):,} dòng"},
        {"Chỉ Tiêu": "Tổng số lượng âm cần xử lý", "Giá Trị": f"{total_neg_qty:,.0f}"},
        {"Chỉ Tiêu": "Số lượt nhập tự động (Lô nguyên vẹn)", "Giá Trị": f"{len(queue_actions)} lượt"},
        {"Chỉ Tiêu": "Số lượng âm đã giải quyết ngay", "Giá Trị": f"{total_offset_qty:,.0f}"},
        {"Chỉ Tiêu": "Số lượng còn thiếu (Chờ tách lẻ / nhập thêm)", "Giá Trị": f"{total_neg_qty - total_offset_qty:,.0f}"},
        {"Chỉ Tiêu": "Tỷ lệ cấn trừ ngay không cần tách lẻ", "Giá Trị": f"{total_offset_qty/total_neg_qty*100:.2f}%"}
    ])

    with pd.ExcelWriter("report_unmatched_shortage.xlsx", engine="openpyxl") as writer:
        summary_df.to_excel(writer, sheet_name="Tong Quan", index=False)
        skipped_df.to_excel(writer, sheet_name="Danh Sach Cho Tach Le", index=False)
    log(" Đã xuất file báo cáo: report_unmatched_shortage.xlsx")
    log("=== HOÀN TẤT XỬ LÝ DỮ LIỆU THÀNH CÔNG ===")
    return True

if __name__ == "__main__":
    file_target = sys.argv[1] if len(sys.argv) > 1 else "Stock Balance With Batch.xlsx"
    process_stock_data(file_target)
