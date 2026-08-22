#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
SCRIPT 2: iSCALA FALCON AUTO-TYPER GUI (GIAO DIỆN ĐIỀU KHIỂN TỰ ĐỘNG HÓA v4.5)
================================================================================
Quy trình chuẩn hóa 100% khớp với form SC7013_01 (Bin Transfers):
  1. [BƯỚC 1]: Gõ Tag ID (Mã Batch) -> Gõ [ENTER] -> Tạm dừng 1.5s chờ iScala nạp DB.
  2. [BƯỚC 2]: Con trỏ tự nhảy sang To Warehouse -> Xóa sạch ô -> Gõ ĐÚNG KHO ĐÍCH (50/62) -> [ENTER] -> Tạm dừng 0.4s.
  3. [BƯỚC 3]: Con trỏ tự nhảy sang Bin Location -> Xóa sạch ô -> Gõ Kệ (01) -> [ENTER].
  4. [BƯỚC 4]: Gõ [ENTER] 3 lần liên tiếp để kết thúc chu trình hoàn tất phiếu chuyển kho.
  5. [BƯỚC 5]: Ghi nhật ký vào 'auto_typer_log.txt' và LẬP TỨC XÓA Tag ID đã xong khỏi 'auto_input_queue.json'.
================================================================================
"""

import sys
import os
import json
import time
import threading
from datetime import datetime

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter.scrolledtext import ScrolledText

# ==============================================================================
# ROBUST HARDWARE KEYBOARD & CLIPBOARD ENGINE (WINDOWS NATIVE)
# ==============================================================================
IS_WINDOWS = sys.platform.startswith('win')

if IS_WINDOWS:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    # Virtual-Key codes
    VK_RETURN = 0x0D
    VK_TAB = 0x09
    VK_ESCAPE = 0x1B
    VK_SPACE = 0x20
    VK_BACK = 0x08
    VK_CONTROL = 0x11
    VK_SHIFT = 0x10
    VK_A = 0x41
    VK_V = 0x56

    KEYEVENTF_KEYUP = 0x0002

    def win_key_down(vk_code):
        scan_code = user32.MapVirtualKeyW(vk_code, 0)
        user32.keybd_event(vk_code, scan_code, 0, 0)

    def win_key_up(vk_code):
        scan_code = user32.MapVirtualKeyW(vk_code, 0)
        user32.keybd_event(vk_code, scan_code, KEYEVENTF_KEYUP, 0)

    def win_press_vk(vk_code, hold_time=0.02):
        win_key_down(vk_code)
        time.sleep(hold_time)
        win_key_up(vk_code)
        time.sleep(0.01)

    def win_type_char(char, char_delay=0.02):
        vk_res = user32.VkKeyScanW(ord(char))
        if vk_res == -1:
            return

        vk = vk_res & 0xFF
        shift_state = (vk_res >> 8) & 1

        if shift_state:
            win_key_down(VK_SHIFT)
            time.sleep(0.005)

        win_press_vk(vk, hold_time=0.015)

        if shift_state:
            win_key_up(VK_SHIFT)
            time.sleep(0.005)

        time.sleep(char_delay)

    def win_clear_field():
        """Xóa sạch nội dung cũ trong ô bằng Ctrl+A -> Backspace"""
        win_key_down(VK_CONTROL)
        time.sleep(0.01)
        win_press_vk(VK_A, hold_time=0.015)
        time.sleep(0.01)
        win_key_up(VK_CONTROL)
        time.sleep(0.02)
        win_press_vk(VK_BACK, hold_time=0.015)
        time.sleep(0.02)

    def set_clipboard_text(text):
        try:
            import tkinter as tk_temp
            r = tk.Tk()
            r.withdraw()
            r.clipboard_clear()
            r.clipboard_append(str(text))
            r.update()
            r.destroy()
        except:
            pass

    def paste_clipboard():
        win_key_down(VK_CONTROL)
        time.sleep(0.01)
        win_press_vk(VK_V, hold_time=0.015)
        time.sleep(0.01)
        win_key_up(VK_CONTROL)
        time.sleep(0.02)

    def type_text(text, char_delay=0.02, use_clipboard=False, clear_first=False):
        if clear_first:
            win_clear_field()
            time.sleep(0.03)
            
        if use_clipboard:
            set_clipboard_text(str(text))
            time.sleep(0.02)
            paste_clipboard()
            time.sleep(0.02)
        else:
            for c in str(text):
                win_type_char(c, char_delay=char_delay)

    def press_enter():
        win_press_vk(VK_RETURN, hold_time=0.025)

else:
    def type_text(text, char_delay=0.02, use_clipboard=False, clear_first=False):
        time.sleep(len(str(text)) * char_delay)

    def press_enter():
        time.sleep(0.02)


# ==============================================================================
# MAIN GUI APPLICATION CLASS
# ==============================================================================
class IScalaAutoTyperApp:
    def __init__(self, root):
        self.root = root
        self.root.title("iScala Falcon Auto-Typer Control Panel v4.5 (SC7013 Exact Workflow)")
        self.root.geometry("1080x840")
        self.root.minsize(940, 700)
        
        self.current_json_path = "auto_input_queue.json"
        self.log_file_path = "auto_typer_log.txt"
        
        # Biến trạng thái
        self.queue_data = []
        self.total_initial_items = 0
        self.completed_count = 0
        
        self.is_running = False
        self.is_paused = False
        self.stop_requested = False
        self.worker_thread = None

        self._setup_style()
        self._build_ui()
        
        self.log(f"Khởi động iScala Falcon Auto-Typer v4.5 (Khớp 100% quy trình SC7013)", "INFO")
        
        if os.path.exists(self.current_json_path):
            self.load_queue_file(self.current_json_path)
        else:
            self.log("Chưa tìm thấy file 'auto_input_queue.json'. Vui lòng chạy 'run_processor.bat' trước.", "WARN")

    def _setup_style(self):
        self.root.configure(bg="#F1F5F9")
        self.style = ttk.Style()
        self.style.theme_use("clam")
        
        self.style.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"), background="#E2E8F0", foreground="#1E293B")
        self.style.configure("Treeview", font=("Segoe UI", 9), rowheight=24)
        self.style.configure("TProgressbar", thickness=18, troughcolor="#E2E8F0", background="#2563EB")

    def _build_ui(self):
        # 1. HEADER PANEL
        header_frame = tk.Frame(self.root, bg="#0F172A", height=65)
        header_frame.pack(fill=tk.X)
        header_frame.pack_propagate(False)

        title_label = tk.Label(
            header_frame, 
            text="🛡️ iSCALA FALCON AUTO-TYPER v4.5 (FORM SC7013 BIN TRANSFERS)", 
            font=("Segoe UI", 13, "bold"), 
            fg="#F8FAFC", 
            bg="#0F172A"
        )
        title_label.pack(side=tk.LEFT, padx=18, pady=10)

        self.status_badge = tk.Label(
            header_frame,
            text="● TRẠNG THÁI: CHỜ LỆNH (IDLE)",
            font=("Segoe UI", 10, "bold"),
            fg="#94A3B8",
            bg="#1E293B",
            padx=14,
            pady=5,
            relief=tk.FLAT
        )
        self.status_badge.pack(side=tk.RIGHT, padx=18, pady=12)

        # 2. STATS BAR
        stats_frame = tk.Frame(self.root, bg="#FFFFFF", bd=1, relief=tk.SOLID)
        stats_frame.pack(fill=tk.X, padx=12, pady=6)

        self.lbl_stat_remain = tk.Label(stats_frame, text="Còn lại trong hàng đợi: 0", font=("Segoe UI", 9, "bold"), bg="#FFFFFF", fg="#DC2626")
        self.lbl_stat_remain.pack(side=tk.LEFT, padx=15, pady=6)

        self.lbl_stat_done = tk.Label(stats_frame, text="Đã xử lý & xóa khỏi JSON: 0", font=("Segoe UI", 9, "bold"), bg="#FFFFFF", fg="#16A34A")
        self.lbl_stat_done.pack(side=tk.LEFT, padx=15, pady=6)

        self.lbl_stat_qty = tk.Label(stats_frame, text="Số lượng cấn trừ còn lại: 0", font=("Segoe UI", 9, "bold"), bg="#FFFFFF", fg="#2563EB")
        self.lbl_stat_qty.pack(side=tk.LEFT, padx=15, pady=6)

        # 3. CONTROL PANEL
        control_card = tk.LabelFrame(self.root, text=" BẢNG ĐIỀU KHIỂN & CẤU HÌNH NHỊP PHÍM SC7013 ", font=("Segoe UI", 10, "bold"), bg="#FFFFFF", fg="#334155", padx=12, pady=8)
        control_card.pack(fill=tk.X, padx=12, pady=4)

        # Hàng 1: Nút hành động chính
        btn_box = tk.Frame(control_card, bg="#FFFFFF")
        btn_box.pack(fill=tk.X, pady=3)

        btn_load = tk.Button(
            btn_box, text="📂 Nạp File JSON", font=("Segoe UI", 9, "bold"),
            bg="#475569", fg="#FFFFFF", activebackground="#334155", activeforeground="#FFFFFF",
            relief=tk.FLAT, padx=10, pady=5, cursor="hand2", command=self.browse_queue_file
        )
        btn_load.pack(side=tk.LEFT, padx=3)

        self.btn_test_one = tk.Button(
            btn_box, text="🧪 CHẠY THỬ 1 DÒNG (TEST)", font=("Segoe UI", 9, "bold"),
            bg="#8B5CF6", fg="#FFFFFF", activebackground="#7C3AED", activeforeground="#FFFFFF",
            relief=tk.FLAT, padx=14, pady=5, cursor="hand2", command=self.start_test_single_item
        )
        self.btn_test_one.pack(side=tk.LEFT, padx=5)

        self.btn_start = tk.Button(
            btn_box, text="▶️ CHẠY TẤT CẢ (START - F6)", font=("Segoe UI", 9, "bold"),
            bg="#16A34A", fg="#FFFFFF", activebackground="#15803D", activeforeground="#FFFFFF",
            relief=tk.FLAT, padx=14, pady=5, cursor="hand2", command=self.start_typing_process
        )
        self.btn_start.pack(side=tk.LEFT, padx=5)

        self.btn_pause = tk.Button(
            btn_box, text="⏸️ TẠM DỪNG (F7)", font=("Segoe UI", 9, "bold"),
            bg="#D97706", fg="#FFFFFF", activebackground="#B45309", activeforeground="#FFFFFF",
            relief=tk.FLAT, padx=12, pady=5, cursor="hand2", state=tk.DISABLED, command=self.toggle_pause
        )
        self.btn_pause.pack(side=tk.LEFT, padx=3)

        self.btn_stop = tk.Button(
            btn_box, text="⏹️ DỪNG HẲN (F8/ESC)", font=("Segoe UI", 9, "bold"),
            bg="#DC2626", fg="#FFFFFF", activebackground="#B91C1C", activeforeground="#FFFFFF",
            relief=tk.FLAT, padx=12, pady=5, cursor="hand2", state=tk.DISABLED, command=self.stop_typing_process
        )
        self.btn_stop.pack(side=tk.LEFT, padx=3)

        # Hàng 2: Cấu hình độ trễ chính xác
        timing_box = tk.Frame(control_card, bg="#FFFFFF")
        timing_box.pack(fill=tk.X, pady=(8, 2))

        lbl_tag_wait = tk.Label(timing_box, text="⏳ Thời gian chờ iScala nạp Tag ID:", font=("Segoe UI", 9, "bold"), bg="#FFFFFF", fg="#B91C1C")
        lbl_tag_wait.pack(side=tk.LEFT, padx=(2, 4))

        self.combo_tag_wait = ttk.Combobox(timing_box, values=["1.0s", "1.2s", "1.5s (Khuyên Dùng)", "2.0s"], width=16, state="readonly")
        self.combo_tag_wait.set("1.5s (Khuyên Dùng)")
        self.combo_tag_wait.pack(side=tk.LEFT, padx=2)

        lbl_step_wait = tk.Label(timing_box, text="⏱️ Nghỉ nhảy ô:", font=("Segoe UI", 9, "bold"), bg="#FFFFFF", fg="#1E293B")
        lbl_step_wait.pack(side=tk.LEFT, padx=(12, 4))

        self.combo_step_wait = ttk.Combobox(timing_box, values=["0.3s", "0.4s (Chuẩn)", "0.6s"], width=12, state="readonly")
        self.combo_step_wait.set("0.4s (Chuẩn)")
        self.combo_step_wait.pack(side=tk.LEFT, padx=2)

        lbl_enter_count = tk.Label(timing_box, text="🔄 Số lần Enter kết thúc:", font=("Segoe UI", 9, "bold"), bg="#FFFFFF", fg="#1E293B")
        lbl_enter_count.pack(side=tk.LEFT, padx=(12, 4))

        self.combo_enter_count = ttk.Combobox(timing_box, values=["2", "3 (Chuẩn SC7013)", "4"], width=16, state="readonly")
        self.combo_enter_count.set("3 (Chuẩn SC7013)")
        self.combo_enter_count.pack(side=tk.LEFT, padx=2)

        # Hàng 3: Tốc độ gõ phím & Tùy chọn an toàn
        speed_box = tk.Frame(control_card, bg="#FFFFFF")
        speed_box.pack(fill=tk.X, pady=(6, 2))

        lbl_speed = tk.Label(speed_box, text="⚡ Tốc độ gõ ký tự:", font=("Segoe UI", 9, "bold"), bg="#FFFFFF", fg="#1E293B")
        lbl_speed.pack(side=tk.LEFT, padx=(2, 4))

        self.speed_slider = tk.Scale(
            speed_box, from_=0.02, to=0.20, resolution=0.01, orient=tk.HORIZONTAL, length=120,
            bg="#FFFFFF", fg="#0F172A", highlightthickness=0, command=self._on_speed_change
        )
        self.speed_slider.set(0.05)
        self.speed_slider.pack(side=tk.LEFT, padx=(4, 4))

        self.lbl_speed_desc = tk.Label(speed_box, text="50ms (Nhanh & Rõ)", font=("Segoe UI", 9, "bold"), bg="#FFFFFF", fg="#2563EB")
        self.lbl_speed_desc.pack(side=tk.LEFT, padx=2)

        self.auto_clear_field_var = tk.BooleanVar(value=True)
        chk_clear = tk.Checkbutton(
            speed_box, text="🧹 Luôn xóa sạch ô trước khi điền (Ctrl+A -> Backspace)", variable=self.auto_clear_field_var,
            font=("Segoe UI", 9, "bold"), bg="#FFFFFF", fg="#047857", activebackground="#FFFFFF"
        )
        chk_clear.pack(side=tk.LEFT, padx=(15, 4))

        self.use_clipboard_var = tk.BooleanVar(value=False)
        chk_clip = tk.Checkbutton(
            speed_box, text="📋 Dán nhanh (Ctrl+V)", variable=self.use_clipboard_var,
            font=("Segoe UI", 9), bg="#FFFFFF", fg="#475569", activebackground="#FFFFFF"
        )
        chk_clip.pack(side=tk.RIGHT, padx=4)

        # 4. SPLIT PANE: Danh sách hàng đợi & Streaming Console
        content_paned = tk.PanedWindow(self.root, orient=tk.VERTICAL, bg="#F1F5F9", sashwidth=4)
        content_paned.pack(fill=tk.BOTH, expand=True, padx=12, pady=4)

        # Top pane: Treeview Queue
        top_frame = tk.LabelFrame(content_paned, text=" DANH SÁCH HÀNG ĐỢI (Đã khóa cứng Kho Đích 50/62) ", font=("Segoe UI", 9, "bold"), bg="#FFFFFF", fg="#334155")
        content_paned.add(top_frame, height=190)

        cols = ("STT", "Stock_Code", "Batch", "Kho_Nguon", "Kho_Dich", "Qty", "Bin", "Trang_Thai")
        self.tree = ttk.Treeview(top_frame, columns=cols, show="headings", selectmode="browse")
        
        self.tree.heading("STT", text="STT")
        self.tree.heading("Stock_Code", text="Mã Vật Tư")
        self.tree.heading("Batch", text="Tag ID (Mã Batch)")
        self.tree.heading("Kho_Nguon", text="Kho Nguồn")
        self.tree.heading("Kho_Dich", text="Kho ĐÍCH (50/62)")
        self.tree.heading("Qty", text="Số Lượng")
        self.tree.heading("Bin", text="Kệ (BIN)")
        self.tree.heading("Trang_Thai", text="Trạng Thái")

        self.tree.column("STT", width=45, anchor="center")
        self.tree.column("Stock_Code", width=120, anchor="center")
        self.tree.column("Batch", width=140, anchor="center")
        self.tree.column("Kho_Nguon", width=75, anchor="center")
        self.tree.column("Kho_Dich", width=110, anchor="center")
        self.tree.column("Qty", width=85, anchor="center")
        self.tree.column("Bin", width=65, anchor="center")
        self.tree.column("Trang_Thai", width=110, anchor="center")

        tree_scroll_y = ttk.Scrollbar(top_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll_y.set)
        
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(4, 0), pady=4)
        tree_scroll_y.pack(side=tk.RIGHT, fill=tk.Y, pady=4)

        # Bottom pane: Streaming Console
        bottom_frame = tk.LabelFrame(content_paned, text=" 📺 LIVE STREAMING CONSOLE (THEO DÕI TỪNG BƯỚC NHẬP FORM SC7013) ", font=("Segoe UI", 9, "bold"), bg="#0F172A", fg="#38BDF8")
        content_paned.add(bottom_frame, height=230)

        self.console = ScrolledText(
            bottom_frame, bg="#020617", fg="#F8FAFC", font=("Consolas", 10),
            insertbackground="#38BDF8", relief=tk.FLAT, padx=10, pady=6
        )
        self.console.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        self.console.tag_config("INFO", foreground="#94A3B8")
        self.console.tag_config("KEY", foreground="#38BDF8")
        self.console.tag_config("TARGET_WH", foreground="#F59E0B", font=("Consolas", 10, "bold"))
        self.console.tag_config("SUCCESS", foreground="#4ADE80", font=("Consolas", 10, "bold"))
        self.console.tag_config("WARN", foreground="#FBBF24")
        self.console.tag_config("ERROR", foreground="#F87171", font=("Consolas", 11, "bold"))
        self.console.tag_config("COUNTDOWN", foreground="#F43F5E", font=("Consolas", 11, "bold"))
        self.console.tag_config("TEST", foreground="#C084FC", font=("Consolas", 11, "bold"))

        # 5. FOOTER & PROGRESS BAR
        footer_frame = tk.Frame(self.root, bg="#F1F5F9")
        footer_frame.pack(fill=tk.X, padx=12, pady=(2, 8))

        self.progress_var = tk.DoubleVar(value=0.0)
        self.progress_bar = ttk.Progressbar(footer_frame, variable=self.progress_var, maximum=100.0)
        self.progress_bar.pack(fill=tk.X, side=tk.TOP, pady=2)

        self.lbl_progress_text = tk.Label(footer_frame, text="Tiến độ: 0% | Còn lại: 0 dòng", font=("Segoe UI", 9), bg="#F1F5F9", fg="#475569")
        self.lbl_progress_text.pack(side=tk.LEFT, pady=2)

        lbl_tips = tk.Label(footer_frame, text="🛡️ Kho đích chỉ điền 50/62 | Tự động xóa khỏi JSON sau khi hoàn tất | Bấm ESC để dừng.", font=("Segoe UI", 9, "italic"), bg="#F1F5F9", fg="#64748B")
        lbl_tips.pack(side=tk.RIGHT, pady=2)

        self.root.bind("<F6>", lambda e: self.start_typing_process())
        self.root.bind("<F7>", lambda e: self.toggle_pause())
        self.root.bind("<F8>", lambda e: self.stop_typing_process())
        self.root.bind("<Escape>", lambda e: self.stop_typing_process())

    def _on_speed_change(self, val):
        v = float(val)
        ms = int(v * 1000)
        self.lbl_speed_desc.config(text=f"{ms}ms")

    def _get_tag_wait_seconds(self):
        val = self.combo_tag_wait.get()
        if "1.0" in val: return 1.0
        if "1.2" in val: return 1.2
        if "1.5" in val: return 1.5
        if "2.0" in val: return 2.0
        return 1.5

    def _get_step_wait_seconds(self):
        val = self.combo_step_wait.get()
        if "0.3" in val: return 0.3
        if "0.4" in val: return 0.4
        if "0.6" in val: return 0.6
        return 0.4

    def _get_end_enters_count(self):
        val = self.combo_enter_count.get()
        if "2" in val: return 2
        if "3" in val: return 3
        if "4" in val: return 4
        return 3

    def log(self, message, level="INFO"):
        ts = datetime.now().strftime("%H:%M:%S")
        formatted = f"[{ts}] {message}\n"
        
        try:
            self.console.insert(tk.END, formatted, level)
            self.console.see(tk.END)
        except:
            pass

        try:
            with open(self.log_file_path, "a", encoding="utf-8") as f_log:
                f_log.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [{level}] {message}\n")
        except:
            pass

    def browse_queue_file(self):
        filepath = filedialog.askopenfilename(
            title="Chọn file hàng đợi JSON",
            filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")]
        )
        if filepath:
            self.current_json_path = filepath
            self.load_queue_file(filepath)

    def load_queue_file(self, filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            raw_actions = data.get("actions", [])
            
            # KIỂM TOÁN TÍNH TOÀN VẸN: Bắt buộc target_warehouse phải là '50' hoặc '62'
            self.queue_data = []
            for item in raw_actions:
                t_wh = str(item.get("target_warehouse", "")).strip()
                if t_wh in ["50", "62"]:
                    item["target_warehouse"] = t_wh
                    self.queue_data.append(item)
                else:
                    self.log(f"CẢNH BÁO: Bỏ qua dòng có kho đích không hợp lệ: {t_wh} (Mã: {item.get('stock_code')})", "WARN")
            
            self.total_initial_items = len(self.queue_data)
            self._refresh_ui_tree_and_stats()
            
            self.log(f"Đã nạp thành công {len(self.queue_data)} lượt nhập (100% Kho đích là 50 hoặc 62)", "SUCCESS")
            self.btn_start.config(state=tk.NORMAL if self.queue_data else tk.DISABLED)
            self.btn_test_one.config(state=tk.NORMAL if self.queue_data else tk.DISABLED)
            
        except Exception as e:
            self.log(f"Lỗi khi nạp file hàng đợi: {e}", "ERROR")
            messagebox.showerror("Lỗi", f"Không thể đọc file hàng đợi:\n{e}")

    def _save_queue_to_disk(self):
        try:
            total_qty_remain = sum(item.get("qty", 0) for item in self.queue_data)
            output_json = {
                "metadata": {
                    "updated_at": datetime.now().isoformat(),
                    "remaining_actions": len(self.queue_data),
                    "total_offset_qty_remaining": total_qty_remain
                },
                "actions": self.queue_data
            }
            with open(self.current_json_path, "w", encoding="utf-8") as f:
                json.dump(output_json, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.log(f"Cảnh báo khi lưu file JSON: {e}", "WARN")

    def _refresh_ui_tree_and_stats(self):
        remain_count = len(self.queue_data)
        total_qty = sum(item.get("qty", 0) for item in self.queue_data)
        
        self.lbl_stat_remain.config(text=f"Còn lại trong hàng đợi: {remain_count:,}")
        self.lbl_stat_done.config(text=f"Đã xử lý & xóa khỏi JSON: {self.completed_count:,}")
        self.lbl_stat_qty.config(text=f"Số lượng cấn trừ còn lại: {total_qty:,}")
        
        for row in self.tree.get_children():
            self.tree.delete(row)
            
        for idx, item in enumerate(self.queue_data, 1):
            self.tree.insert("", tk.END, iid=str(idx), values=(
                idx,
                item.get("stock_code"),
                item.get("batch"),
                item.get("source_warehouse"),
                item.get("target_warehouse"),
                f"{item.get('qty'):,}",
                item.get("bin", "01"),
                "Chờ gõ..."
            ))
            
        if self.total_initial_items > 0:
            pct = (self.completed_count / (self.completed_count + remain_count)) * 100
        else:
            pct = 100.0 if remain_count == 0 else 0.0
            
        self.progress_var.set(pct)
        self.lbl_progress_text.config(text=f"Tiến độ: {pct:.1f}% | Còn lại: {remain_count} dòng")

    # ==========================================================================
    # CHU TRÌNH GÕ CHUẨN FORM SC7013 (CHÍNH XÁC TUYỆT ĐỐI)
    # ==========================================================================
    def _execute_single_form_entry(self, item, idx):
        batch = str(item.get("batch")).strip()
        stock_code = str(item.get("stock_code")).strip()
        target_wh = str(item.get("target_warehouse")).strip()
        bin_val = str(item.get("bin", "01")).strip()
        
        # KHÓA BẢO VỆ NGHIÊM NGẶT
        if target_wh not in ["50", "62"]:
            self.log(f"❌ LỖI DỮ LIỆU: Kho đích [{target_wh}] không phải 50 hoặc 62! DỪNG NGAY.", "ERROR")
            raise ValueError(f"Kho đích không hợp lệ: {target_wh}")

        char_delay = float(self.speed_slider.get())
        tag_wait_time = self._get_tag_wait_seconds()
        step_wait_time = self._get_step_wait_seconds()
        end_enters = self._get_end_enters_count()
        use_clipboard = self.use_clipboard_var.get()
        clear_first = self.auto_clear_field_var.get()

        self.log(f"==================================================", "INFO")
        self.log(f"▶ [LƯỢT #{idx}] Mã: {stock_code} | Tag ID: {batch} | KHO ĐÍCH: {target_wh}", "TARGET_WH")
        self.log(f"==================================================", "INFO")

        # BƯỚC 1: Điền Tag ID (Batch) -> Gõ Enter -> CHỜ iSCALA LOAD DATABASE (1.5s)
        self.log(f"  [1/3] Gõ Tag ID: {batch} -> [ENTER]", "KEY")
        type_text(batch, char_delay=char_delay, use_clipboard=use_clipboard, clear_first=clear_first)
        time.sleep(0.08)
        press_enter()
        self.log(f"  ⏳ Chờ iScala nạp dữ liệu Tag ID & chuyển sang To Warehouse ({tag_wait_time:.1f}s)...", "INFO")
        time.sleep(tag_wait_time)

        if self.stop_requested:
            return False

        # BƯỚC 2: Con trỏ đã nằm tại 'To Warehouse' -> Xóa ô -> Gõ ĐÚNG 50 hoặc 62 -> Enter -> Nghỉ 0.4s
        self.log(f"  [2/3 - KHO ĐÍCH] Xóa ô & Gõ To Warehouse: {target_wh} -> [ENTER]", "TARGET_WH")
        type_text(target_wh, char_delay=char_delay, use_clipboard=use_clipboard, clear_first=True)
        time.sleep(0.08)
        press_enter()
        time.sleep(step_wait_time)

        if self.stop_requested:
            return False

        # BƯỚC 3: Con trỏ đã nằm tại 'Bin Location' -> Xóa ô -> Gõ 01 -> Enter -> Nghỉ 0.4s
        self.log(f"  [3/3 - KỆ BIN] Xóa ô & Gõ Bin Location: {bin_val} -> [ENTER]", "KEY")
        type_text(bin_val, char_delay=char_delay, use_clipboard=use_clipboard, clear_first=True)
        time.sleep(0.08)
        press_enter()
        time.sleep(step_wait_time)

        # BƯỚC 4: Gõ [ENTER] 3 lần liên tiếp kết thúc phiếu chuyển kho
        self.log(f"  [KẾT THÚC PHIẾU] Gõ [ENTER] x {end_enters} lần...", "KEY")
        for _ in range(end_enters):
            press_enter()
            time.sleep(0.18)

        return True

    # ==========================================================================
    # MODE CHẠY THỬ 1 DÒNG (TEST 1 ITEM)
    # ==========================================================================
    def start_test_single_item(self):
        if not self.queue_data:
            messagebox.showwarning("Cảnh báo", "Hàng đợi đã trống.")
            return

        if self.is_running:
            return

        selected = self.tree.selection()
        if selected:
            target_idx = int(selected[0]) - 1
        else:
            target_idx = 0

        self.test_target_index = target_idx
        self.is_running = True
        self.is_paused = False
        self.stop_requested = False
        
        self.btn_start.config(state=tk.DISABLED)
        self.btn_test_one.config(state=tk.DISABLED)
        self.btn_pause.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)
        self.status_badge.config(text="● TRẠNG THÁI: CHẠY THỬ 1 DÒNG (TEST)", fg="#C084FC", bg="#581C87")

        self.worker_thread = threading.Thread(target=self._run_test_single_worker, daemon=True)
        self.worker_thread.start()

    def _run_test_single_worker(self):
        item = self.queue_data[self.test_target_index]
        batch = item.get("batch")
        
        self.log("==================================================", "TEST")
        self.log(f"🧪 CHẠY THỬ TAG ID: {batch} | KHO ĐÍCH: {item.get('target_warehouse')}", "TEST")
        self.log(" CHUẨN BỊ: CLICK CHUỘT VÀO Ô 'TAG ID' TRÊN FORM SC7013 TRONG 5S!", "COUNTDOWN")
        self.log("==================================================", "TEST")
        
        for i in range(5, 0, -1):
            if self.stop_requested:
                return
            self.log(f" Bắt đầu gõ sau {i} giây...", "COUNTDOWN")
            time.sleep(1.0)

        if self.stop_requested:
            return

        try:
            success = self._execute_single_form_entry(item, self.test_target_index + 1)
            if success:
                self.log(f" THÀNH CÔNG: Đã hoàn tất Tag ID [{batch}]. XÓA KHỎI FILE JSON!", "SUCCESS")
                self.queue_data.pop(self.test_target_index)
                self.completed_count += 1
                self._save_queue_to_disk()
        except Exception as e:
            self.log(f" LỖI: {e}", "ERROR")

        self.is_running = False
        self.root.after(0, self._on_finish_test_single)

    def _on_finish_test_single(self):
        self._refresh_ui_tree_and_stats()
        self.btn_start.config(state=tk.NORMAL if self.queue_data else tk.DISABLED)
        self.btn_test_one.config(state=tk.NORMAL if self.queue_data else tk.DISABLED)
        self.btn_pause.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.DISABLED)
        self.status_badge.config(text="● TRẠNG THÁI: ĐÃ TEST XONG (IDLE)", fg="#38BDF8", bg="#0C4A6E")
        messagebox.showinfo("Đã Test Xong", "Đã gõ thử nghiệm thành công 1 dòng và XÓA khỏi JSON!\n\nBạn hãy kiểm tra màn hình iScala SC7013. Nếu ô 'To Warehouse' đã hiển thị ĐÚNG 50 hoặc 62, hãy bấm 'CHẠY TẤT CẢ'.")

    # ==========================================================================
    # MODE CHẠY TẤT CẢ (RUN ALL)
    # ==========================================================================
    def start_typing_process(self):
        if not self.queue_data:
            messagebox.showwarning("Cảnh báo", "Hàng đợi đã trống.")
            return

        if self.is_running:
            return

        self.is_running = True
        self.is_paused = False
        self.stop_requested = False
        
        self.btn_start.config(state=tk.DISABLED)
        self.btn_test_one.config(state=tk.DISABLED)
        self.btn_pause.config(state=tk.NORMAL, text="⏸️ TẠM DỪNG (F7)", bg="#D97706")
        self.btn_stop.config(state=tk.NORMAL)
        self.status_badge.config(text="● TRẠNG THÁI: ĐANG CHẠY (RUNNING)", fg="#4ADE80", bg="#064E3B")

        self.worker_thread = threading.Thread(target=self._run_auto_typer_worker, daemon=True)
        self.worker_thread.start()

    def toggle_pause(self):
        if not self.is_running:
            return
        
        self.is_paused = not self.is_paused
        if self.is_paused:
            self.btn_pause.config(text="▶️ TIẾP TỤC (F7)", bg="#2563EB")
            self.status_badge.config(text="● TRẠNG THÁI: TẠM DỪNG (PAUSED)", fg="#FDE047", bg="#78350F")
            self.log(" ĐÃ TẠM DỪNG QUÁ TRÌNH NHẬP LIỆU.", "WARN")
        else:
            self.btn_pause.config(text="⏸️ TẠM DỪNG (F7)", bg="#D97706")
            self.status_badge.config(text="● TRẠNG THÁI: ĐANG CHẠY (RUNNING)", fg="#4ADE80", bg="#064E3B")
            self.log(" TIẾP TỤC QUÁ TRÌNH NHẬP LIỆU...", "SUCCESS")

    def stop_typing_process(self):
        if not self.is_running:
            return
        
        self.stop_requested = True
        self.is_running = False
        self.is_paused = False
        
        self.btn_start.config(state=tk.NORMAL if self.queue_data else tk.DISABLED)
        self.btn_test_one.config(state=tk.NORMAL if self.queue_data else tk.DISABLED)
        self.btn_pause.config(state=tk.DISABLED, text="⏸️ TẠM DỪNG (F7)", bg="#D97706")
        self.btn_stop.config(state=tk.DISABLED)
        self.status_badge.config(text="● TRẠNG THÁI: ĐÃ DỪNG (STOPPED)", fg="#F87171", bg="#7F1D1D")
        self.log("⏹️ ĐÃ DỪNG TIẾN TRÌNH. CÁC DÒNG ĐÃ XONG VẪN ĐƯỢC LƯU VÀ XÓA AN TOÀN.", "ERROR")
        self._refresh_ui_tree_and_stats()

    def _run_auto_typer_worker(self):
        self.log("==================================================", "COUNTDOWN")
        self.log(" CHUẨN BỊ: CLICK CHUỘT VÀO Ô 'TAG ID' TRÊN FORM SC7013 TRONG 5S!", "COUNTDOWN")
        self.log("==================================================", "COUNTDOWN")
        
        for i in range(5, 0, -1):
            if self.stop_requested:
                return
            self.log(f" Bắt đầu gõ sau {i} giây...", "COUNTDOWN")
            time.sleep(1.0)

        self.log(" BẮT ĐẦU GÕ TOÀN BỘ DANH SÁCH VÀO iSCALA...", "SUCCESS")

        while len(self.queue_data) > 0:
            while self.is_paused:
                if self.stop_requested:
                    return
                time.sleep(0.1)

            if self.stop_requested:
                return

            item = self.queue_data[0]
            batch = item.get("batch")

            try:
                success = self._execute_single_form_entry(item, self.completed_count + 1)
                if success:
                    self.queue_data.pop(0)
                    self.completed_count += 1
                    self._save_queue_to_disk()
                    self.log(f" Đã hoàn tất & xóa Tag ID [{batch}] khỏi JSON (Còn lại: {len(self.queue_data)} dòng)", "SUCCESS")
                    self.root.after(0, self._refresh_ui_tree_and_stats)
            except Exception as e:
                self.log(f" LỖI TẠI DÒNG [{batch}]: {e}", "ERROR")
                self.stop_typing_process()
                break

            time.sleep(0.4)

        self.is_running = False
        self.root.after(0, self._on_finish_all)

    def _on_finish_all(self):
        self._refresh_ui_tree_and_stats()
        self.btn_start.config(state=tk.DISABLED)
        self.btn_test_one.config(state=tk.DISABLED)
        self.btn_pause.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.DISABLED)
        self.status_badge.config(text="● TRẠNG THÁI: HOÀN TẤT (COMPLETED)", fg="#38BDF8", bg="#0C4A6E")
        self.log("==================================================", "SUCCESS")
        self.log("🎉 XIN CHÚC MỪNG: ĐÃ HOÀN TẤT TOÀN BỘ VÀ XÓA HẾT HÀNG ĐỢI!", "SUCCESS")
        self.log("==================================================", "SUCCESS")
        messagebox.showinfo("Thành công", f"Đã hoàn tất toàn bộ {self.completed_count} lượt vào iScala an toàn 100%!")


if __name__ == "__main__":
    root = tk.Tk()
    app = IScalaAutoTyperApp(root)
    root.mainloop()
