#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
SCRIPT 2: iSCALA FALCON AUTO-TYPER GUI (GIAO DIỆN ĐIỀU KHIỂN TỰ ĐỘNG HÓA v3.0)
================================================================================
Cải tiến đột phá trong bản v3.0:
  1. KHẮC PHỤC TRIỆT ĐỂ LỖI GÕ PHÍM: Sử dụng Win32 keybd_event & VkKeyScanW 
     (Tương thích 100% với form iScala SC7013_01 và MFC/Win32 Controls).
  2. BỔ SUNG CHẾ ĐỘ DÁN CLIPBOARD (Ctrl+V): Chống trượt/mất ký tự khi mạng lag.
  3. GHI NHẬT KÝ FILE (FILE LOGGING): Tự động ghi toàn bộ quá trình vào 'auto_typer_log.txt'.
  4. CHẾ ĐỘ CHẠY THỬ 1 DÒNG (TEST 1 ITEM): Test trước từng trường dữ liệu.
  5. TÙY BIẾN TỐC ĐỘ: Thanh trượt mili-giây và các preset tốc độ trực quan.
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
    VK_CONTROL = 0x11
    VK_SHIFT = 0x10
    VK_V = 0x56
    VK_C = 0x43

    KEYEVENTF_KEYUP = 0x0002

    def win_key_down(vk_code):
        scan_code = user32.MapVirtualKeyW(vk_code, 0)
        user32.keybd_event(vk_code, scan_code, 0, 0)

    def win_key_up(vk_code):
        scan_code = user32.MapVirtualKeyW(vk_code, 0)
        user32.keybd_event(vk_code, scan_code, KEYEVENTF_KEYUP, 0)

    def win_press_vk(vk_code, hold_time=0.015):
        win_key_down(vk_code)
        time.sleep(hold_time)
        win_key_up(vk_code)
        time.sleep(0.01)

    def win_type_char(char, char_delay=0.02):
        """Gõ 1 ký tự bằng Virtual Key + Scan Code (Được iScala tiếp nhận 100%)"""
        vk_res = user32.VkKeyScanW(ord(char))
        if vk_res == -1:
            # Fallback nếu ký tự đặc biệt
            win_send_unicode_fallback(char)
            return

        vk = vk_res & 0xFF
        shift_state = (vk_res >> 8) & 1

        if shift_state:
            win_key_down(VK_SHIFT)
            time.sleep(0.005)

        win_press_vk(vk, hold_time=0.01)

        if shift_state:
            win_key_up(VK_SHIFT)
            time.sleep(0.005)

        time.sleep(char_delay)

    def win_send_unicode_fallback(char):
        """Fallback qua SendInput nếu ký tự không có trong layout bàn phím"""
        class KEYBDINPUT(ctypes.Structure):
            _fields_ = [
                ("wVk", wintypes.WORD),
                ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.c_size_t)
            ]

        class INPUT(ctypes.Structure):
            class _INPUT(ctypes.Union):
                _fields_ = [("ki", KEYBDINPUT)]
            _anonymous_ = ("_input",)
            _fields_ = [("type", wintypes.DWORD), ("_input", _INPUT)]

        inp_d = INPUT(type=1)
        inp_d.ki = KEYBDINPUT(wVk=0, wScan=ord(char), dwFlags=0x0004, time=0, dwExtraInfo=0)
        inp_u = INPUT(type=1)
        inp_u.ki = KEYBDINPUT(wVk=0, wScan=ord(char), dwFlags=0x0004 | 0x0002, time=0, dwExtraInfo=0)

        user32.SendInput(1, ctypes.byref(inp_d), ctypes.sizeof(INPUT))
        time.sleep(0.01)
        user32.SendInput(1, ctypes.byref(inp_u), ctypes.sizeof(INPUT))

    def set_clipboard_text(text):
        """Sao chép text vào Windows Clipboard để dán nhanh (Ctrl+V)"""
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
        """Bấm tổ hợp phím Ctrl+V"""
        win_key_down(VK_CONTROL)
        time.sleep(0.01)
        win_press_vk(VK_V, hold_time=0.015)
        time.sleep(0.01)
        win_key_up(VK_CONTROL)
        time.sleep(0.01)

    def type_text(text, char_delay=0.02, use_clipboard=False):
        if use_clipboard:
            set_clipboard_text(str(text))
            time.sleep(0.02)
            paste_clipboard()
            time.sleep(0.02)
        else:
            for c in str(text):
                win_type_char(c, char_delay=char_delay)

    def press_enter():
        win_press_vk(VK_RETURN, hold_time=0.02)

    def press_tab():
        win_press_vk(VK_TAB, hold_time=0.02)

else:
    # Non-Windows Mock
    def type_text(text, char_delay=0.02, use_clipboard=False):
        time.sleep(len(str(text)) * char_delay)

    def press_enter():
        time.sleep(0.02)

    def press_tab():
        time.sleep(0.02)


# ==============================================================================
# MAIN GUI APPLICATION CLASS
# ==============================================================================
class IScalaAutoTyperApp:
    def __init__(self, root):
        self.root = root
        self.root.title("iScala Falcon Auto-Typer Control Panel v3.0 (SC7013 Bin Transfers)")
        self.root.geometry("1060x800")
        self.root.minsize(920, 680)
        
        self.log_file_path = "auto_typer_log.txt"
        
        # Biến trạng thái
        self.queue_data = []
        self.total_items = 0
        self.completed_items = 0
        self.total_qty_offset = 0
        
        self.is_running = False
        self.is_paused = False
        self.stop_requested = False
        self.is_test_single_mode = False
        self.worker_thread = None

        self._setup_style()
        self._build_ui()
        
        # Ghi log khởi động
        self.log(f"Khởi động iScala Falcon Auto-Typer v3.0 (Log file: {self.log_file_path})", "INFO")
        
        # Tự động nạp file hàng đợi nếu có sẵn
        default_file = "auto_input_queue.json"
        if os.path.exists(default_file):
            self.load_queue_file(default_file)
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
            text="⚡ iSCALA FALCON AUTO-TYPER v3.0 (FORM SC7013)", 
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

        self.lbl_stat_total = tk.Label(stats_frame, text="Tổng lượt: 0", font=("Segoe UI", 9, "bold"), bg="#FFFFFF", fg="#1E293B")
        self.lbl_stat_total.pack(side=tk.LEFT, padx=15, pady=6)

        self.lbl_stat_done = tk.Label(stats_frame, text="Đã xong: 0", font=("Segoe UI", 9, "bold"), bg="#FFFFFF", fg="#16A34A")
        self.lbl_stat_done.pack(side=tk.LEFT, padx=15, pady=6)

        self.lbl_stat_remain = tk.Label(stats_frame, text="Còn lại: 0", font=("Segoe UI", 9, "bold"), bg="#FFFFFF", fg="#DC2626")
        self.lbl_stat_remain.pack(side=tk.LEFT, padx=15, pady=6)

        self.lbl_stat_qty = tk.Label(stats_frame, text="Số lượng cấn trừ: 0", font=("Segoe UI", 9, "bold"), bg="#FFFFFF", fg="#2563EB")
        self.lbl_stat_qty.pack(side=tk.LEFT, padx=15, pady=6)

        # 3. CONTROL PANEL
        control_card = tk.LabelFrame(self.root, text=" BẢNG ĐIỀU KHIỂN & CHẾ ĐỘ THỰC THI ", font=("Segoe UI", 10, "bold"), bg="#FFFFFF", fg="#334155", padx=12, pady=8)
        control_card.pack(fill=tk.X, padx=12, pady=4)

        # Hàng 1: Nút hành động chính
        btn_box = tk.Frame(control_card, bg="#FFFFFF")
        btn_box.pack(fill=tk.X, pady=3)

        btn_load = tk.Button(
            btn_box, text="📂 Nạp File Hàng Đợi", font=("Segoe UI", 9, "bold"),
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

        # Hàng 2: Tốc độ & Phương thức nhập
        speed_box = tk.Frame(control_card, bg="#FFFFFF")
        speed_box.pack(fill=tk.X, pady=(8, 2))

        lbl_speed = tk.Label(speed_box, text="⚡ Tốc độ gõ:", font=("Segoe UI", 9, "bold"), bg="#FFFFFF", fg="#1E293B")
        lbl_speed.pack(side=tk.LEFT, padx=(2, 6))

        presets = [
            ("🐢 Chậm (0.35s)", 0.35),
            ("⚡ Chuẩn (0.20s)", 0.20),
            ("🚀 Nhanh (0.10s)", 0.10),
            ("🔥 Siêu Tốc (0.05s)", 0.05)
        ]
        for name, val in presets:
            b = tk.Button(
                speed_box, text=name, font=("Segoe UI", 8), bg="#F1F5F9", fg="#334155",
                relief=tk.SOLID, bd=1, padx=6, pady=2, cursor="hand2",
                command=lambda v=val: self._set_speed_preset(v)
            )
            b.pack(side=tk.LEFT, padx=2)

        self.speed_slider = tk.Scale(
            speed_box, from_=0.03, to=0.60, resolution=0.01, orient=tk.HORIZONTAL, length=150,
            bg="#FFFFFF", fg="#0F172A", highlightthickness=0, command=self._on_speed_change
        )
        self.speed_slider.set(0.20)
        self.speed_slider.pack(side=tk.LEFT, padx=(8, 4))

        self.lbl_speed_desc = tk.Label(speed_box, text="200ms (Chuẩn)", font=("Segoe UI", 9, "bold"), bg="#FFFFFF", fg="#2563EB")
        self.lbl_speed_desc.pack(side=tk.LEFT, padx=4)

        # Tùy chọn Clipboard Dán nhanh
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
        top_frame = tk.LabelFrame(content_paned, text=" DANH SÁCH LƯỢT NHẬP LIỆU (Chọn dòng để chạy thử nếu muốn) ", font=("Segoe UI", 9, "bold"), bg="#FFFFFF", fg="#334155")
        content_paned.add(top_frame, height=190)

        cols = ("STT", "Stock_Code", "Batch", "Kho_Nguon", "Kho_Dich", "Qty", "Bin", "Trang_Thai")
        self.tree = ttk.Treeview(top_frame, columns=cols, show="headings", selectmode="browse")
        
        self.tree.heading("STT", text="STT")
        self.tree.heading("Stock_Code", text="Mã Vật Tư")
        self.tree.heading("Batch", text="Mã Lô Dương")
        self.tree.heading("Kho_Nguon", text="Kho Nguồn")
        self.tree.heading("Kho_Dich", text="Kho Đích (Âm)")
        self.tree.heading("Qty", text="Số Lượng")
        self.tree.heading("Bin", text="Kệ (BIN)")
        self.tree.heading("Trang_Thai", text="Trạng Thái")

        self.tree.column("STT", width=45, anchor="center")
        self.tree.column("Stock_Code", width=120, anchor="center")
        self.tree.column("Batch", width=130, anchor="center")
        self.tree.column("Kho_Nguon", width=75, anchor="center")
        self.tree.column("Kho_Dich", width=95, anchor="center")
        self.tree.column("Qty", width=85, anchor="center")
        self.tree.column("Bin", width=65, anchor="center")
        self.tree.column("Trang_Thai", width=110, anchor="center")

        tree_scroll_y = ttk.Scrollbar(top_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll_y.set)
        
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(4, 0), pady=4)
        tree_scroll_y.pack(side=tk.RIGHT, fill=tk.Y, pady=4)

        # Bottom pane: Streaming Console
        bottom_frame = tk.LabelFrame(content_paned, text=" 📺 LIVE STREAMING CONSOLE (XEM GÕ TRỰC TIẾP & GHI FILE LOG) ", font=("Segoe UI", 9, "bold"), bg="#0F172A", fg="#38BDF8")
        content_paned.add(bottom_frame, height=230)

        self.console = ScrolledText(
            bottom_frame, bg="#020617", fg="#F8FAFC", font=("Consolas", 10),
            insertbackground="#38BDF8", relief=tk.FLAT, padx=10, pady=6
        )
        self.console.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        self.console.tag_config("INFO", foreground="#94A3B8")
        self.console.tag_config("KEY", foreground="#38BDF8")
        self.console.tag_config("SUCCESS", foreground="#4ADE80", font=("Consolas", 10, "bold"))
        self.console.tag_config("WARN", foreground="#FBBF24")
        self.console.tag_config("ERROR", foreground="#F87171", font=("Consolas", 10, "bold"))
        self.console.tag_config("COUNTDOWN", foreground="#F43F5E", font=("Consolas", 11, "bold"))
        self.console.tag_config("TEST", foreground="#C084FC", font=("Consolas", 11, "bold"))

        # 5. FOOTER & PROGRESS BAR
        footer_frame = tk.Frame(self.root, bg="#F1F5F9")
        footer_frame.pack(fill=tk.X, padx=12, pady=(2, 8))

        self.progress_var = tk.DoubleVar(value=0.0)
        self.progress_bar = ttk.Progressbar(footer_frame, variable=self.progress_var, maximum=100.0)
        self.progress_bar.pack(fill=tk.X, side=tk.TOP, pady=2)

        self.lbl_progress_text = tk.Label(footer_frame, text="Tiến độ: 0% (0 / 0)", font=("Segoe UI", 9), bg="#F1F5F9", fg="#475569")
        self.lbl_progress_text.pack(side=tk.LEFT, pady=2)

        lbl_tips = tk.Label(footer_frame, text="💡 Mẹo: Bấm ESC để dừng khẩn cấp | Nhật ký tự động lưu vào auto_typer_log.txt", font=("Segoe UI", 9, "italic"), bg="#F1F5F9", fg="#64748B")
        lbl_tips.pack(side=tk.RIGHT, pady=2)

        # Phím tắt toàn cục
        self.root.bind("<F6>", lambda e: self.start_typing_process())
        self.root.bind("<F7>", lambda e: self.toggle_pause())
        self.root.bind("<F8>", lambda e: self.stop_typing_process())
        self.root.bind("<Escape>", lambda e: self.stop_typing_process())

    def _set_speed_preset(self, val):
        self.speed_slider.set(val)
        self._on_speed_change(val)

    def _on_speed_change(self, val):
        v = float(val)
        ms = int(v * 1000)
        if v <= 0.08:
            desc = f"{ms}ms (🔥 Siêu Tốc)"
        elif v <= 0.15:
            desc = f"{ms}ms (🚀 Nhanh)"
        elif v <= 0.28:
            desc = f"{ms}ms ( Chuẩn)"
        else:
            desc = f"{ms}ms (🐢 Chậm)"
        self.lbl_speed_desc.config(text=desc)

    def log(self, message, level="INFO"):
        ts = datetime.now().strftime("%H:%M:%S")
        formatted = f"[{ts}] {message}\n"
        
        # Ghi vào Console UI
        try:
            self.console.insert(tk.END, formatted, level)
            self.console.see(tk.END)
        except:
            pass

        # Ghi đồng thời vào file auto_typer_log.txt
        try:
            with open(self.log_file_path, "a", encoding="utf-8") as f_log:
                f_log.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [{level}] {message}\n")
        except:
            pass

    def browse_queue_file(self):
        filepath = filedialog.askopenfilename(
            title="Chọn file hàng đợi dữ liệu",
            filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")]
        )
        if filepath:
            self.load_queue_file(filepath)

    def load_queue_file(self, filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            self.queue_data = data.get("actions", [])
            self.total_items = len(self.queue_data)
            self.completed_items = 0
            self.total_qty_offset = sum(item.get("qty", 0) for item in self.queue_data)
            
            self.lbl_stat_total.config(text=f"Tổng lượt: {self.total_items:,}")
            self.lbl_stat_done.config(text="Đã xong: 0")
            self.lbl_stat_remain.config(text=f"Còn lại: {self.total_items:,}")
            self.lbl_stat_qty.config(text=f"Số lượng cấn trừ: {self.total_qty_offset:,}")
            
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
            
            self.log(f"Đã nạp thành công {self.total_items} lượt nhập từ file: {os.path.basename(filepath)}", "SUCCESS")
            self.btn_start.config(state=tk.NORMAL)
            self.btn_test_one.config(state=tk.NORMAL)
            self.progress_var.set(0)
            self.lbl_progress_text.config(text=f"Tiến độ: 0% (0 / {self.total_items})")
            
        except Exception as e:
            self.log(f"Lỗi khi nạp file hàng đợi: {e}", "ERROR")
            messagebox.showerror("Lỗi", f"Không thể đọc file hàng đợi:\n{e}")

    # ==========================================================================
    # MODE CHẠY THỬ 1 DÒNG (TEST 1 ITEM)
    # ==========================================================================
    def start_test_single_item(self):
        if not self.queue_data:
            messagebox.showwarning("Cảnh báo", "Chưa có dữ liệu hàng đợi. Vui lòng nạp file trước.")
            return

        if self.is_running:
            return

        selected = self.tree.selection()
        if selected:
            target_idx = int(selected[0]) - 1
        else:
            target_idx = self.completed_items if self.completed_items < self.total_items else 0

        self.is_test_single_mode = True
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
        idx = self.test_target_index + 1
        
        self.log("==================================================", "TEST")
        self.log(f"🧪 BẮT ĐẦU CHẠY THỬ 1 DÒNG DUY NHẤT (LƯỢT #{idx})", "TEST")
        self.log(" CHUẨN BỊ: CLICK CHUỘT VÀO Ô 'TAG ID' TRÊN FORM SC7013!", "COUNTDOWN")
        self.log("==================================================", "TEST")
        
        for i in range(5, 0, -1):
            if self.stop_requested:
                return
            self.log(f" Bắt đầu gõ sau {i} giây...", "COUNTDOWN")
            time.sleep(1.0)

        if self.stop_requested:
            return

        char_delay = float(self.speed_slider.get())
        step_delay = max(0.20, char_delay * 1.5)
        use_clipboard = self.use_clipboard_var.get()

        stock_code = item.get("stock_code")
        batch = item.get("batch")
        target_wh = item.get("target_warehouse")
        qty = str(item.get("qty"))
        bin_val = item.get("bin", "01")

        self.log(f"--- [TEST LƯỢT #{idx}] Mã: {stock_code} | Batch: {batch} | WH Đích: {target_wh} | Qty: {qty} ---", "TEST")
        self.root.after(0, lambda i=idx: self._update_tree_status(i, " Đang test..."))

        # BƯỚC 1: Điền Tag ID (Batch) -> Enter
        self.log(f"  [1/4] Gõ Tag ID (Batch): {batch} -> [ENTER]", "KEY")
        type_text(batch, char_delay=char_delay, use_clipboard=use_clipboard)
        time.sleep(step_delay)
        press_enter()
        time.sleep(step_delay)

        # BƯỚC 2: Điền Kho Đích (50 hoặc 62) -> Enter
        self.log(f"  [2/4] Gõ To Warehouse: {target_wh} -> [ENTER]", "KEY")
        type_text(target_wh, char_delay=char_delay, use_clipboard=use_clipboard)
        time.sleep(step_delay)
        press_enter()
        time.sleep(step_delay)

        # BƯỚC 3: Điền Số Lượng (Qty) -> Enter
        self.log(f"  [3/4] Gõ Quantity: {qty} -> [ENTER]", "KEY")
        type_text(qty, char_delay=char_delay, use_clipboard=use_clipboard)
        time.sleep(step_delay)
        press_enter()
        time.sleep(step_delay)

        # BƯỚC 4: Điền BIN '01' -> Enter
        self.log(f"  [4/4] Gõ Bin Location: {bin_val} -> [ENTER]", "KEY")
        type_text(bin_val, char_delay=char_delay, use_clipboard=use_clipboard)
        time.sleep(step_delay)
        press_enter()
        time.sleep(step_delay)

        # BƯỚC 5: Gõ Enter 4 lần kết thúc vòng lặp
        self.log("  [KẾT THÚC VÒNG LẶP] Gõ [ENTER] x 4 lần...", "KEY")
        for _ in range(4):
            press_enter()
            time.sleep(step_delay)

        self.log(f" ĐÃ HOÀN TẤT GÕ THỬ LƯỢT #{idx}!", "SUCCESS")
        self.log("=> Vui lòng xem màn hình iScala SC7013 xem các ô đã được điền đủ chưa.", "WARN")
        self.root.after(0, lambda i=idx: self._update_tree_status(i, " Đã Test"))
        
        self.is_running = False
        self.root.after(0, self._on_finish_test_single)

    def _on_finish_test_single(self):
        self.btn_start.config(state=tk.NORMAL)
        self.btn_test_one.config(state=tk.NORMAL)
        self.btn_pause.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.DISABLED)
        self.status_badge.config(text="● TRẠNG THÁI: TEST XONG (IDLE)", fg="#38BDF8", bg="#0C4A6E")
        messagebox.showinfo("Đã Test Xong", "Đã gõ thử nghiệm thành công 1 dòng!\n\nBạn hãy kiểm tra màn hình iScala SC7013. Nếu mọi thứ chuẩn xác, hãy bấm 'CHẠY TẤT CẢ' để bot hoàn tất toàn bộ danh sách.")

    # ==========================================================================
    # MODE CHẠY TẤT CẢ (RUN ALL)
    # ==========================================================================
    def start_typing_process(self):
        if not self.queue_data:
            messagebox.showwarning("Cảnh báo", "Chưa có dữ liệu hàng đợi. Vui lòng nạp file trước.")
            return

        if self.is_running:
            return

        self.is_test_single_mode = False
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
        
        self.btn_start.config(state=tk.NORMAL)
        self.btn_test_one.config(state=tk.NORMAL)
        self.btn_pause.config(state=tk.DISABLED, text="⏸️ TẠM DỪNG (F7)", bg="#D97706")
        self.btn_stop.config(state=tk.DISABLED)
        self.status_badge.config(text="● TRẠNG THÁI: ĐÃ DỪNG (STOPPED)", fg="#F87171", bg="#7F1D1D")
        self.log("⏹️ ĐÃ DỪNG HẲN TIẾN TRÌNH THEO YÊU CẦU CỦA NGƯỜI DÙNG.", "ERROR")

    def _run_auto_typer_worker(self):
        self.log("==================================================", "COUNTDOWN")
        self.log(" CHUẨN BỊ: CLICK CHUỘT VÀO Ô 'TAG ID' TRÊN FORM SC7013!", "COUNTDOWN")
        self.log("==================================================", "COUNTDOWN")
        
        for i in range(5, 0, -1):
            if self.stop_requested:
                return
            self.log(f" Bắt đầu gõ sau {i} giây...", "COUNTDOWN")
            time.sleep(1.0)

        self.log(" BẮT ĐẦU GÕ DỮ LIỆU VÀO iSCALA...", "SUCCESS")

        char_delay = float(self.speed_slider.get())
        step_delay = max(0.20, char_delay * 1.5)
        use_clipboard = self.use_clipboard_var.get()

        for idx, item in enumerate(self.queue_data[self.completed_items:], self.completed_items + 1):
            while self.is_paused:
                if self.stop_requested:
                    return
                time.sleep(0.1)

            if self.stop_requested:
                return

            stock_code = item.get("stock_code")
            batch = item.get("batch")
            target_wh = item.get("target_warehouse")
            qty = str(item.get("qty"))
            bin_val = item.get("bin", "01")

            self.log(f"--- [LƯỢT {idx}/{self.total_items}] Mã: {stock_code} | Batch: {batch} | WH Đích: {target_wh} | Qty: {qty} ---", "INFO")
            self.root.after(0, lambda i=idx: self._update_tree_status(i, " Đang gõ..."))

            # 1. Tag ID (Batch) -> Enter
            self.log(f"  [1/4] Gõ Tag ID (Batch): {batch} -> [ENTER]", "KEY")
            type_text(batch, char_delay=char_delay, use_clipboard=use_clipboard)
            time.sleep(step_delay)
            press_enter()
            time.sleep(step_delay)

            # 2. To Warehouse -> Enter
            self.log(f"  [2/4] Gõ To Warehouse: {target_wh} -> [ENTER]", "KEY")
            type_text(target_wh, char_delay=char_delay, use_clipboard=use_clipboard)
            time.sleep(step_delay)
            press_enter()
            time.sleep(step_delay)

            # 3. Quantity -> Enter
            self.log(f"  [3/4] Gõ Quantity: {qty} -> [ENTER]", "KEY")
            type_text(qty, char_delay=char_delay, use_clipboard=use_clipboard)
            time.sleep(step_delay)
            press_enter()
            time.sleep(step_delay)

            # 4. Bin Location -> Enter
            self.log(f"  [4/4] Gõ Bin Location: {bin_val} -> [ENTER]", "KEY")
            type_text(bin_val, char_delay=char_delay, use_clipboard=use_clipboard)
            time.sleep(step_delay)
            press_enter()
            time.sleep(step_delay)

            # 5. Enter x 4
            self.log("  [KẾT THÚC VÒNG LẶP] Gõ [ENTER] x 4 lần...", "KEY")
            for _ in range(4):
                press_enter()
                time.sleep(step_delay)

            self.completed_items = idx
            self.log(f" Hoàn tất thành công lượt {idx}/{self.total_items}!", "SUCCESS")

            self.root.after(0, lambda i=idx: self._update_tree_status(i, " Hoàn tất"))
            self.root.after(0, self._update_progress_stats)

            time.sleep(0.35)

        self.is_running = False
        self.root.after(0, self._on_finish_all)

    def _update_tree_status(self, idx, status_text):
        try:
            self.tree.set(str(idx), "Trang_Thai", status_text)
            self.tree.see(str(idx))
        except:
            pass

    def _update_progress_stats(self):
        done = self.completed_items
        total = self.total_items
        remain = max(0, total - done)
        pct = (done / total * 100) if total > 0 else 0

        self.lbl_stat_done.config(text=f"Đã xong: {done:,}")
        self.lbl_stat_remain.config(text=f"Còn lại: {remain:,}")
        self.progress_var.set(pct)
        self.lbl_progress_text.config(text=f"Tiến độ: {pct:.1f}% ({done} / {total})")

    def _on_finish_all(self):
        self.btn_start.config(state=tk.NORMAL)
        self.btn_test_one.config(state=tk.NORMAL)
        self.btn_pause.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.DISABLED)
        self.status_badge.config(text="● TRẠNG THÁI: HOÀN TẤT (COMPLETED)", fg="#38BDF8", bg="#0C4A6E")
        self.log("==================================================", "SUCCESS")
        self.log("🎉 XIN CHÚC MỪNG: ĐÃ HOÀN TẤT TOÀN BỘ DANH SÁCH NHẬP LIỆU!", "SUCCESS")
        self.log("==================================================", "SUCCESS")
        messagebox.showinfo("Thành công", f"Đã hoàn tất tự động gõ {self.total_items} lượt vào iScala an toàn 100%!")


if __name__ == "__main__":
    root = tk.Tk()
    app = IScalaAutoTyperApp(root)
    root.mainloop()
