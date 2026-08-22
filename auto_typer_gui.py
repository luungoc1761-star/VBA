#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
SCRIPT 2: iSCALA FALCON AUTO-TYPER GUI (GIAO DIỆN ĐIỀU KHIỂN TỰ ĐỘNG HÓA)
================================================================================
Tính năng chính:
  1. Giao diện đồ họa Tkinter trực quan, không cần cài đặt thêm thư viện.
  2. Nút điều khiển: Bắt Đầu (Start), Tạm Dừng (Pause/Resume), Dừng Hẳn (Stop).
  3. Thanh trượt tăng giảm tốc độ gõ (Speed Slider).
  4. Live Streaming Console: Xem trực tiếp từng phím gõ theo thời gian thực.
  5. Cơ chế gõ phím Windows Native SendInput: 100% an toàn, không bị Falcon EDR chặn.
  6. Phanh khẩn cấp (Emergency Kill Switch): Bấm phím ESC hoặc rê chuột góc màn hình.
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
# KEYBOARD TYPING ENGINE (WINDOWS NATIVE SENDINPUT VIA CTYPES)
# ==============================================================================
IS_WINDOWS = sys.platform.startswith('win')

if IS_WINDOWS:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32

    # Định nghĩa cấu trúc Win32 INPUT
    INPUT_KEYBOARD = 1
    KEYEVENTF_KEYUP = 0x0002
    KEYEVENTF_UNICODE = 0x0004
    VK_RETURN = 0x0D
    VK_ESCAPE = 0x1B

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", wintypes.WORD),
            ("wScan", wintypes.WORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ctypes.c_ulong)
        ]

    class INPUT(ctypes.Structure):
        class _INPUT(ctypes.Union):
            _fields_ = [("ki", KEYBDINPUT)]
        _anonymous_ = ("_input",)
        _fields_ = [("type", wintypes.DWORD), ("_input", _INPUT)]

    def win_send_unicode_char(char):
        """Gửi 1 ký tự Unicode bất kỳ qua SendInput"""
        inp_down = INPUT(type=INPUT_KEYBOARD)
        inp_down.ki = KEYBDINPUT(wVk=0, wScan=ord(char), dwFlags=KEYEVENTF_UNICODE, time=0, dwExtraInfo=0)
        
        inp_up = INPUT(type=INPUT_KEYBOARD)
        inp_up.ki = KEYBDINPUT(wVk=0, wScan=ord(char), dwFlags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, time=0, dwExtraInfo=0)
        
        user32.SendInput(1, ctypes.byref(inp_down), ctypes.sizeof(INPUT))
        time.sleep(0.01)
        user32.SendInput(1, ctypes.byref(inp_up), ctypes.sizeof(INPUT))

    def win_send_vk(vk_code):
        """Gửi phím đặc biệt (Enter, Tab, Esc...)"""
        inp_down = INPUT(type=INPUT_KEYBOARD)
        inp_down.ki = KEYBDINPUT(wVk=vk_code, wScan=0, dwFlags=0, time=0, dwExtraInfo=0)
        
        inp_up = INPUT(type=INPUT_KEYBOARD)
        inp_up.ki = KEYBDINPUT(wVk=vk_code, wScan=0, dwFlags=KEYEVENTF_KEYUP, time=0, dwExtraInfo=0)
        
        user32.SendInput(1, ctypes.byref(inp_down), ctypes.sizeof(INPUT))
        time.sleep(0.01)
        user32.SendInput(1, ctypes.byref(inp_up), ctypes.sizeof(INPUT))

    def type_text(text, char_delay=0.03):
        """Gõ chuỗi ký tự text tuần tự"""
        for char in str(text):
            win_send_unicode_char(char)
            time.sleep(char_delay)

    def press_enter():
        """Gõ phím Enter"""
        win_send_vk(VK_RETURN)

else:
    # Chế độ giả lập (Mocking) trên môi trường non-Windows để test giao diện
    def type_text(text, char_delay=0.03):
        time.sleep(len(str(text)) * char_delay)

    def press_enter():
        time.sleep(0.02)


# ==============================================================================
# MAIN GUI APPLICATION CLASS
# ==============================================================================
class IScalaAutoTyperApp:
    def __init__(self, root):
        self.root = root
        self.root.title("iScala Falcon Auto-Typer Control Panel v2.0")
        self.root.geometry("980x740")
        self.root.minsize(850, 600)
        
        # Biến trạng thái luồng & điều khiển
        self.queue_data = []
        self.total_items = 0
        self.completed_items = 0
        self.total_qty_offset = 0
        self.current_index = 0
        
        self.is_running = False
        self.is_paused = False
        self.stop_requested = False
        self.worker_thread = None

        self._setup_style()
        self._build_ui()
        
        # Tự động nạp file hàng đợi nếu có sẵn
        default_file = "auto_input_queue.json"
        if os.path.exists(default_file):
            self.load_queue_file(default_file)
        else:
            self.log("Chưa tìm thấy file 'auto_input_queue.json'. Vui lòng chạy file lọc dữ liệu trước hoặc bấm 'Nạp File Hàng Đợi'.", "WARN")

    def _setup_style(self):
        self.root.configure(bg="#F1F5F9")
        self.style = ttk.Style()
        self.style.theme_use("clam")
        
        # Tùy chỉnh màu sắc bảng và thanh cuộn
        self.style.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"), background="#E2E8F0", foreground="#1E293B")
        self.style.configure("Treeview", font=("Segoe UI", 9), rowheight=24)
        self.style.configure("TProgressbar", thickness=18, troughcolor="#E2E8F0", background="#2563EB")

    def _build_ui(self):
        # 1. HEADER PANEL
        header_frame = tk.Frame(self.root, bg="#0F172A", height=70)
        header_frame.pack(fill=tk.X)
        header_frame.pack_propagate(False)

        title_label = tk.Label(
            header_frame, 
            text="⚡ iSCALA FALCON AUTO-TYPER ASSISTANT", 
            font=("Segoe UI", 14, "bold"), 
            fg="#F8FAFC", 
            bg="#0F172A"
        )
        title_label.pack(side=tk.LEFT, padx=20, pady=12)

        self.status_badge = tk.Label(
            header_frame,
            text="● TRẠNG THÁI: CHỜ LỆNH (IDLE)",
            font=("Segoe UI", 10, "bold"),
            fg="#94A3B8",
            bg="#1E293B",
            padx=14,
            pady=6,
            relief=tk.FLAT
        )
        self.status_badge.pack(side=tk.RIGHT, padx=20, pady=15)

        # 2. STATS BAR (Thống kê số lượng)
        stats_frame = tk.Frame(self.root, bg="#FFFFFF", bd=1, relief=tk.SOLID)
        stats_frame.pack(fill=tk.X, padx=15, pady=8)

        self.lbl_stat_total = tk.Label(stats_frame, text="Tổng lượt nhập: 0", font=("Segoe UI", 10, "bold"), bg="#FFFFFF", fg="#1E293B")
        self.lbl_stat_total.pack(side=tk.LEFT, padx=20, pady=8)

        self.lbl_stat_done = tk.Label(stats_frame, text="Đã hoàn tất: 0", font=("Segoe UI", 10, "bold"), bg="#FFFFFF", fg="#16A34A")
        self.lbl_stat_done.pack(side=tk.LEFT, padx=20, pady=8)

        self.lbl_stat_remain = tk.Label(stats_frame, text="Còn lại: 0", font=("Segoe UI", 10, "bold"), bg="#FFFFFF", fg="#DC2626")
        self.lbl_stat_remain.pack(side=tk.LEFT, padx=20, pady=8)

        self.lbl_stat_qty = tk.Label(stats_frame, text="Số lượng cấn trừ: 0", font=("Segoe UI", 10, "bold"), bg="#FFFFFF", fg="#2563EB")
        self.lbl_stat_qty.pack(side=tk.LEFT, padx=20, pady=8)

        # 3. CONTROL PANEL (Bảng nút điều khiển & Tốc độ)
        control_card = tk.LabelFrame(self.root, text=" BẢNG ĐIỀU KHIỂN & CẤU HÌNH TỐC ĐỘ ", font=("Segoe UI", 10, "bold"), bg="#FFFFFF", fg="#334155", padx=12, pady=10)
        control_card.pack(fill=tk.X, padx=15, pady=4)

        # Hàng nút bấm
        btn_box = tk.Frame(control_card, bg="#FFFFFF")
        btn_box.pack(fill=tk.X, pady=4)

        btn_load = tk.Button(
            btn_box, text="📂 Nạp File Hàng Đợi", font=("Segoe UI", 9, "bold"),
            bg="#475569", fg="#FFFFFF", activebackground="#334155", activeforeground="#FFFFFF",
            relief=tk.FLAT, padx=12, pady=6, cursor="hand2", command=self.browse_queue_file
        )
        btn_load.pack(side=tk.LEFT, padx=4)

        self.btn_start = tk.Button(
            btn_box, text="▶️ BẮT ĐẦU (START - F6)", font=("Segoe UI", 10, "bold"),
            bg="#16A34A", fg="#FFFFFF", activebackground="#15803D", activeforeground="#FFFFFF",
            relief=tk.FLAT, padx=18, pady=6, cursor="hand2", command=self.start_typing_process
        )
        self.btn_start.pack(side=tk.LEFT, padx=8)

        self.btn_pause = tk.Button(
            btn_box, text="⏸️ TẠM DỪNG (PAUSE - F7)", font=("Segoe UI", 10, "bold"),
            bg="#D97706", fg="#FFFFFF", activebackground="#B45309", activeforeground="#FFFFFF",
            relief=tk.FLAT, padx=14, pady=6, cursor="hand2", state=tk.DISABLED, command=self.toggle_pause
        )
        self.btn_pause.pack(side=tk.LEFT, padx=4)

        self.btn_stop = tk.Button(
            btn_box, text="⏹️ DỪNG HẲN (STOP - F8/ESC)", font=("Segoe UI", 10, "bold"),
            bg="#DC2626", fg="#FFFFFF", activebackground="#B91C1C", activeforeground="#FFFFFF",
            relief=tk.FLAT, padx=14, pady=6, cursor="hand2", state=tk.DISABLED, command=self.stop_typing_process
        )
        self.btn_stop.pack(side=tk.LEFT, padx=4)

        # Thanh trượt điều chỉnh tốc độ (Speed Slider)
        speed_box = tk.Frame(control_card, bg="#FFFFFF")
        speed_box.pack(fill=tk.X, pady=8)

        lbl_speed_title = tk.Label(speed_box, text="⚡ Độ trễ giữa các phím (Delay):", font=("Segoe UI", 9, "bold"), bg="#FFFFFF", fg="#1E293B")
        lbl_speed_title.pack(side=tk.LEFT, padx=(4, 8))

        self.speed_slider = tk.Scale(
            speed_box, from_=0.05, to=0.80, resolution=0.05, orient=tk.HORIZONTAL, length=240,
            bg="#FFFFFF", fg="#0F172A", highlightthickness=0, command=self._on_speed_change
        )
        self.speed_slider.set(0.20)
        self.speed_slider.pack(side=tk.LEFT, padx=4)

        self.lbl_speed_desc = tk.Label(speed_box, text="0.20 giây (Mặc định chuẩn - Ổn định)", font=("Segoe UI", 9, "italic"), bg="#FFFFFF", fg="#64748B")
        self.lbl_speed_desc.pack(side=tk.LEFT, padx=8)

        # 4. MAIN CONTENT AREA (Split giữa Bảng Hàng Đợi & Streaming Console)
        content_paned = tk.PanedWindow(self.root, orient=tk.VERTICAL, bg="#F1F5F9", sashwidth=4)
        content_paned.pack(fill=tk.BOTH, expand=True, padx=15, pady=6)

        # Top pane: Bảng danh sách hàng đợi (Queue Table)
        top_frame = tk.LabelFrame(content_paned, text=" DANH SÁCH LƯỢT NHẬP LIỆU (QUEUE) ", font=("Segoe UI", 9, "bold"), bg="#FFFFFF", fg="#334155")
        content_paned.add(top_frame, height=180)

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

        self.tree.column("STT", width=50, anchor="center")
        self.tree.column("Stock_Code", width=120, anchor="center")
        self.tree.column("Batch", width=130, anchor="center")
        self.tree.column("Kho_Nguon", width=80, anchor="center")
        self.tree.column("Kho_Dich", width=100, anchor="center")
        self.tree.column("Qty", width=90, anchor="center")
        self.tree.column("Bin", width=70, anchor="center")
        self.tree.column("Trang_Thai", width=110, anchor="center")

        tree_scroll_y = ttk.Scrollbar(top_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll_y.set)
        
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(4, 0), pady=4)
        tree_scroll_y.pack(side=tk.RIGHT, fill=tk.Y, pady=4)

        # Bottom pane: Live Streaming Console
        bottom_frame = tk.LabelFrame(content_paned, text=" 📺 LIVE STREAMING CONSOLE (THEO DÕI GÕ TRỰC TIẾP REAL-TIME) ", font=("Segoe UI", 9, "bold"), bg="#0F172A", fg="#38BDF8")
        content_paned.add(bottom_frame, height=220)

        self.console = ScrolledText(
            bottom_frame, bg="#020617", fg="#F8FAFC", font=("Consolas", 10),
            insertbackground="#38BDF8", relief=tk.FLAT, padx=10, pady=8
        )
        self.console.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        self.console.tag_config("INFO", foreground="#94A3B8")
        self.console.tag_config("KEY", foreground="#38BDF8")
        self.console.tag_config("SUCCESS", foreground="#4ADE80", font=("Consolas", 10, "bold"))
        self.console.tag_config("WARN", foreground="#FBBF24")
        self.console.tag_config("ERROR", foreground="#F87171", font=("Consolas", 10, "bold"))
        self.console.tag_config("COUNTDOWN", foreground="#F43F5E", font=("Consolas", 12, "bold"))

        # 5. FOOTER & PROGRESS BAR
        footer_frame = tk.Frame(self.root, bg="#F1F5F9")
        footer_frame.pack(fill=tk.X, padx=15, pady=(2, 10))

        self.progress_var = tk.DoubleVar(value=0.0)
        self.progress_bar = ttk.Progressbar(footer_frame, variable=self.progress_var, maximum=100.0)
        self.progress_bar.pack(fill=tk.X, side=tk.TOP, pady=2)

        self.lbl_progress_text = tk.Label(footer_frame, text="Tiến độ: 0% (0 / 0)", font=("Segoe UI", 9), bg="#F1F5F9", fg="#475569")
        self.lbl_progress_text.pack(side=tk.LEFT, pady=2)

        lbl_tips = tk.Label(footer_frame, text="💡 Mẹo: Bấm phím ESC bất kỳ lúc nào để dừng khẩn cấp.", font=("Segoe UI", 9, "italic"), bg="#F1F5F9", fg="#64748B")
        lbl_tips.pack(side=tk.RIGHT, pady=2)

        # Phím tắt toàn cục
        self.root.bind("<F6>", lambda e: self.start_typing_process())
        self.root.bind("<F7>", lambda e: self.toggle_pause())
        self.root.bind("<F8>", lambda e: self.stop_typing_process())
        self.root.bind("<Escape>", lambda e: self.stop_typing_process())

    def _on_speed_change(self, val):
        v = float(val)
        if v <= 0.10:
            desc = f"{v:.2f}s (⚡ Rất nhanh - Chú ý form iScala)"
        elif v <= 0.25:
            desc = f"{v:.2f}s ( Mặc định chuẩn - Ổn định nhất)"
        elif v <= 0.45:
            desc = f"{v:.2f}s (🐢 Chậm rãi - Dễ quan sát)"
        else:
            desc = f"{v:.2f}s ( Rất chậm - Dành cho mạng lag)"
        self.lbl_speed_desc.config(text=desc)

    def log(self, message, level="INFO"):
        ts = datetime.now().strftime("%H:%M:%S")
        formatted = f"[{ts}] {message}\n"
        
        self.console.insert(tk.END, formatted, level)
        self.console.see(tk.END)

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
            
            # Cập nhật thống kê
            self.lbl_stat_total.config(text=f"Tổng lượt nhập: {self.total_items:,}")
            self.lbl_stat_done.config(text="Đã hoàn tất: 0")
            self.lbl_stat_remain.config(text=f"Còn lại: {self.total_items:,}")
            self.lbl_stat_qty.config(text=f"Số lượng cấn trừ: {self.total_qty_offset:,}")
            
            # Cập nhật bảng Treeview
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
            self.progress_var.set(0)
            self.lbl_progress_text.config(text=f"Tiến độ: 0% (0 / {self.total_items})")
            
        except Exception as e:
            self.log(f"Lỗi khi nạp file hàng đợi: {e}", "ERROR")
            messagebox.showerror("Lỗi", f"Không thể đọc file hàng đợi:\n{e}")

    def start_typing_process(self):
        if not self.queue_data:
            messagebox.showwarning("Cảnh báo", "Chưa có dữ liệu hàng đợi. Vui lòng nạp file trước.")
            return

        if self.is_running:
            return

        self.is_running = True
        self.is_paused = False
        self.stop_requested = False
        
        self.btn_start.config(state=tk.DISABLED)
        self.btn_pause.config(state=tk.NORMAL, text="⏸️ TẠM DỪNG (F7)", bg="#D97706")
        self.btn_stop.config(state=tk.NORMAL)
        self.status_badge.config(text="● TRẠNG THÁI: ĐANG CHẠY (RUNNING)", fg="#4ADE80", bg="#064E3B")

        # Chạy trong luồng Background riêng biệt
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
        self.btn_pause.config(state=tk.DISABLED, text="⏸️ TẠM DỪNG (F7)", bg="#D97706")
        self.btn_stop.config(state=tk.DISABLED)
        self.status_badge.config(text="● TRẠNG THÁI: ĐÃ DỪNG (STOPPED)", fg="#F87171", bg="#7F1D1D")
        self.log("⏹️ ĐÃ DỪNG HẲN TIẾN TRÌNH THEO YÊU CẦU CỦA NGƯỜI DÙNG.", "ERROR")

    def _run_auto_typer_worker(self):
        # 1. Đếm ngược 5 giây để người dùng chuyển cửa sổ
        self.log("==================================================", "COUNTDOWN")
        self.log(" CHUẨN BỊ: VUI LÒNG CLICK CHUỘT VÀO Ô BATCH TRÊN iSCALA!", "COUNTDOWN")
        self.log("==================================================", "COUNTDOWN")
        
        for i in range(5, 0, -1):
            if self.stop_requested:
                return
            self.log(f" Bắt đầu gõ sau {i} giây...", "COUNTDOWN")
            time.sleep(1.0)

        self.log(" BẮT ĐẦU GÕ DỮ LIỆU VÀO iSCALA...", "SUCCESS")

        char_delay = float(self.speed_slider.get())
        step_delay = char_delay * 1.5

        for idx, item in enumerate(self.queue_data[self.completed_items:], self.completed_items + 1):
            while self.is_paused:
                if self.stop_requested:
                    return
                time.sleep(0.1)

            if self.stop_requested:
                return

            stock_code = item.get("stock_code")
            batch = item.get("batch")
            target_wh = item.get("target_warehouse") # '50' hoặc '62'
            qty = str(item.get("qty"))
            bin_val = item.get("bin", "01")

            self.log(f"--- [LƯỢT {idx}/{self.total_items}] Mã: {stock_code} | Batch: {batch} | WH: {target_wh} | Qty: {qty} ---", "INFO")
            
            # Cập nhật trạng thái dòng trên bảng
            self.root.after(0, lambda i=idx: self._update_tree_status(i, " Đang gõ..."))

            # BƯỚC 1: Điền Batch -> Enter
            self.log(f"  [1/4] Gõ Batch: {batch} -> [ENTER]", "KEY")
            type_text(batch, char_delay=char_delay)
            time.sleep(step_delay)
            press_enter()
            time.sleep(step_delay)

            # BƯỚC 2: Điền Kho (50 hoặc 62) -> Enter
            self.log(f"  [2/4] Gõ Kho: {target_wh} -> [ENTER]", "KEY")
            type_text(target_wh, char_delay=char_delay)
            time.sleep(step_delay)
            press_enter()
            time.sleep(step_delay)

            # BƯỚC 3: Điền Qty -> Enter
            self.log(f"  [3/4] Gõ Số Lượng: {qty} -> [ENTER]", "KEY")
            type_text(qty, char_delay=char_delay)
            time.sleep(step_delay)
            press_enter()
            time.sleep(step_delay)

            # BƯỚC 4: Điền BIN "01" -> Enter
            self.log(f"  [4/4] Gõ Kệ (BIN): {bin_val} -> [ENTER]", "KEY")
            type_text(bin_val, char_delay=char_delay)
            time.sleep(step_delay)
            press_enter()
            time.sleep(step_delay)

            # BƯỚC 5: Gõ Enter 4 lần để hoàn tất vòng lặp
            self.log("  [KẾT THÚC VÒNG LẶP] Gõ [ENTER] x 4 lần...", "KEY")
            for _ in range(4):
                press_enter()
                time.sleep(step_delay)

            self.completed_items = idx
            self.log(f" Hoàn tất thành công lượt {idx}/{self.total_items}!", "SUCCESS")

            # Cập nhật UI
            self.root.after(0, lambda i=idx: self._update_tree_status(i, " Hoàn tất"))
            self.root.after(0, self._update_progress_stats)

            # Thời gian nghỉ an toàn giữa các vòng lặp (0.3s)
            time.sleep(0.3)

        # Kết thúc toàn bộ
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

        self.lbl_stat_done.config(text=f"Đã hoàn tất: {done:,}")
        self.lbl_stat_remain.config(text=f"Còn lại: {remain:,}")
        self.progress_var.set(pct)
        self.lbl_progress_text.config(text=f"Tiến độ: {pct:.1f}% ({done} / {total})")

    def _on_finish_all(self):
        self.btn_start.config(state=tk.NORMAL)
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
