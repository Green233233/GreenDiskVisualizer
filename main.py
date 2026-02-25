import sys
import os
import threading
import platform
import ctypes
import colorsys
import time
from typing import List, Dict

if getattr(sys, "frozen", False):
    try:
        if sys.stdout is None:
            sys.stdout = open(os.devnull, "w", encoding="utf-8")
        if sys.stderr is None:
            sys.stderr = open(os.devnull, "w", encoding="utf-8")
    except Exception:
        pass

import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk, messagebox

from models import ScanOptions, ScanResult
from scanner import list_disks, scan_path
from treemap import build_treemap, TreemapNode

# ── Theme ────────────────────────────────────────────────────────

THEME = {
    "bg_deep":     "#0b1622",
    "bg_surface":  "#132238",
    "bg_header":   "#1a3050",
    "accent":      "#4ecca3",
    "accent_dim":  "#2d8a72",
    "accent_light":"#6ee7b7",
    "text":        "#e4e8ec",
    "text_dim":    "#8899aa",
    "border":      "#1e3a54",
    "progress_bg": "#1a2a3a",
    "canvas_bg":   "#0e1a28",
    "error":       "#e74c3c",
}

_BASE_HUES = [162, 200, 30, 275, 345, 120, 75, 240, 50, 185]

# 自定义大圆点单选：圆点直径（像素）
_RADIO_DOT_SIZE = 28
_RADIO_DOT_RING = 2
_RADIO_DOT_INNER_R = 8  # 选中时内部实心圆半径

_EXPAND_THRESHOLD = 25 * 1024 ** 3  # 25 GB
_MAX_DEPTH_FULL = 5
_MAX_DEPTH_FAST = 2

_HEADER_HEIGHTS = [24, 21, 18, 16, 14]
_FONT_SIZES = [8, 7, 6, 6, 5]
_MIN_BLOCK_W = [60, 50, 40, 30, 24]
_MIN_BLOCK_H = [45, 38, 30, 24, 18]

_VERSION = "Alpha v0.2.1"


def _hsl_to_hex(h: float, s: float, l: float) -> str:
    r, g, b = colorsys.hls_to_rgb(h / 360.0, l, s)
    return f"#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}"


def _init_dpi_awareness() -> None:
    if platform.system() != "Windows":
        return
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass


def _hide_console() -> None:
    if platform.system() != "Windows":
        return
    try:
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 0)
    except Exception:
        pass


def _is_admin() -> bool:
    if platform.system() != "Windows":
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


# ── Application ──────────────────────────────────────────────────

class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        try:
            current_scaling = float(self.tk.call("tk", "scaling"))
            if current_scaling < 1.5:
                self.tk.call("tk", "scaling", 1.5)
        except Exception:
            pass

        self.withdraw()
        self._create_splash()
        self._update_splash_progress(0.05, "正在初始化...")
        self.after(50, self._init_main_ui)

    # ── Splash ───────────────────────────────────────────────────

    def _create_splash(self) -> None:
        splash = tk.Toplevel(self)
        splash.overrideredirect(True)
        splash.attributes("-topmost", True)
        splash.configure(bg=THEME["bg_deep"])

        sw, sh = 480, 300
        scr_w = splash.winfo_screenwidth()
        scr_h = splash.winfo_screenheight()
        splash.geometry(f"{sw}x{sh}+{(scr_w - sw) // 2}+{(scr_h - sh) // 2}")

        c = tk.Canvas(splash, width=sw, height=sh,
                      bg=THEME["bg_deep"], highlightthickness=0)
        c.pack(fill=tk.BOTH, expand=True)

        c.create_rectangle(0, 0, sw, sh,
                           outline=THEME["accent"], width=2)
        c.create_text(sw // 2, 55, text="Green",
                      fill=THEME["accent"],
                      font=("Segoe UI", 26, "bold"))
        c.create_text(sw // 2, 110, text="磁盘空间可视化工具",
                      fill=THEME["text"], font=("Segoe UI", 11))
        c.create_text(sw // 2, 145, text=_VERSION,
                      fill=THEME["text_dim"], font=("Segoe UI", 8))

        bar_x, bar_w = 60, sw - 120
        bar_y, bar_h = 190, 14
        c.create_rectangle(bar_x, bar_y, bar_x + bar_w, bar_y + bar_h,
                           fill=THEME["progress_bg"], outline=THEME["border"])
        self._splash_bar_fill = c.create_rectangle(
            bar_x + 1, bar_y + 1, bar_x + 1, bar_y + bar_h - 1,
            fill=THEME["accent"], outline="")
        self._splash_bar_info = (bar_x, bar_y, bar_w, bar_h)

        self._splash_pct_id = c.create_text(
            sw // 2, bar_y + bar_h + 20, text="0%",
            fill=THEME["text_dim"], font=("Segoe UI", 7))
        self._splash_status_id = c.create_text(
            sw // 2, bar_y + bar_h + 44, text="",
            fill=THEME["text_dim"], font=("Segoe UI", 7))

        self._splash = splash
        self._splash_canvas = c
        splash.update()

    def _update_splash_progress(self, ratio: float, text: str) -> None:
        try:
            if not self._splash.winfo_exists():
                return
        except (tk.TclError, AttributeError):
            return
        ratio = max(0.0, min(ratio, 1.0))
        bx, by, bw, bh = self._splash_bar_info
        self._splash_canvas.coords(
            self._splash_bar_fill,
            bx + 1, by + 1, bx + 1 + int(bw * ratio), by + bh - 1)
        self._splash_canvas.itemconfig(
            self._splash_pct_id, text=f"{int(ratio * 100)}%")
        self._splash_canvas.itemconfig(
            self._splash_status_id, text=text)
        self._splash.update()

    # ── Theme setup ──────────────────────────────────────────────

    def _setup_theme(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")

        style.configure(".", background=THEME["bg_surface"],
                        foreground=THEME["text"],
                        fieldbackground=THEME["bg_header"],
                        bordercolor=THEME["border"],
                        darkcolor=THEME["bg_deep"],
                        lightcolor=THEME["bg_header"],
                        troughcolor=THEME["progress_bg"],
                        selectbackground=THEME["accent"],
                        selectforeground=THEME["bg_deep"],
                        focuscolor=THEME["accent"])

        style.configure("TButton",
                        background=THEME["accent"],
                        foreground=THEME["bg_deep"],
                        padding=(16, 5),
                        font=("Segoe UI", 9, "bold"))
        style.map("TButton",
                  background=[("active", THEME["accent_dim"]),
                              ("pressed", THEME["accent_dim"])])

        style.configure("TLabel",
                        background=THEME["bg_surface"],
                        foreground=THEME["text"],
                        font=("Segoe UI", 9))

        style.configure("Header.TLabel",
                        background=THEME["bg_header"],
                        foreground=THEME["text"],
                        font=("Segoe UI", 9))

        style.configure("TFrame", background=THEME["bg_surface"])
        style.configure("Header.TFrame", background=THEME["bg_header"])

        style.configure("TCombobox",
                        fieldbackground=THEME["bg_header"],
                        background=THEME["bg_header"],
                        foreground="#ffffff",
                        arrowcolor=THEME["accent"],
                        selectbackground=THEME["accent"],
                        selectforeground=THEME["bg_deep"])
        style.map("TCombobox",
                  foreground=[("readonly", "#ffffff"), ("active", "#ffffff")],
                  fieldbackground=[("readonly", THEME["bg_header"]), ("active", THEME["bg_header"])])

        style.configure("TRadiobutton",
                        background=THEME["bg_surface"],
                        foreground=THEME["text"],
                        indicatorcolor=THEME["bg_header"],
                        font=("Segoe UI", 9))
        style.map("TRadiobutton",
                  indicatorcolor=[("selected", THEME["accent"])])

        style.configure("Header.TRadiobutton",
                        background=THEME["bg_header"],
                        foreground=THEME["text"],
                        indicatorcolor=THEME["bg_deep"],
                        font=("Segoe UI", 9),
                        indicatorsize=16)
        style.map("Header.TRadiobutton",
                  indicatorcolor=[("selected", THEME["accent"])])

        style.configure("Horizontal.TProgressbar",
                        background=THEME["accent"],
                        troughcolor=THEME["progress_bg"],
                        bordercolor=THEME["border"],
                        lightcolor=THEME["accent"],
                        darkcolor=THEME["accent_dim"])

        style.configure("Status.TLabel",
                        background=THEME["bg_header"],
                        foreground=THEME["text_dim"],
                        font=("Segoe UI", 8),
                        anchor="w")

    def _add_big_dot_radio(self, parent: tk.Frame, text: str, value: str,
                           padx: tuple) -> None:
        """在 parent 中增加一个「大圆点」单选：Canvas 画圆 + Label，可读性更好。"""
        s = _RADIO_DOT_SIZE + 4
        f = tk.Frame(parent, bg=THEME["bg_header"], cursor="hand2")
        cnv = tk.Canvas(f, width=s, height=s, bg=THEME["bg_header"],
                       highlightthickness=0)
        cnv.pack(side=tk.LEFT)
        lbl = tk.Label(f, text=text, bg=THEME["bg_header"], fg=THEME["text"],
                      font=("Segoe UI", 9), cursor="hand2")
        lbl.pack(side=tk.LEFT, padx=(6, 0))

        def on_click(_e=None) -> None:
            self.mode_var.set(value)

        def on_enter(_e: tk.Event) -> None:
            lbl.config(fg="#ffffff")

        def on_leave(_e: tk.Event) -> None:
            lbl.config(fg=THEME["text"])

        for w in (f, cnv, lbl):
            w.bind("<Button-1>", on_click)
            w.bind("<Enter>", on_enter)
            w.bind("<Leave>", on_leave)
        f.pack(side=tk.LEFT, padx=padx)
        self._scan_mode_canvases.append((value, cnv))

    def _draw_scan_mode_dots(self) -> None:
        """根据 mode_var 重绘两个大圆点：选中为实心，未选为空心环。"""
        current = self.mode_var.get()
        cx = (_RADIO_DOT_SIZE + 4) / 2.0
        r_outer = _RADIO_DOT_SIZE / 2.0 - 2
        for value, cnv in self._scan_mode_canvases:
            cnv.delete("all")
            cnv.create_oval(
                cx - r_outer, cx - r_outer, cx + r_outer, cx + r_outer,
                outline=THEME["accent"] if value == current else THEME["text_dim"],
                width=_RADIO_DOT_RING,
                fill=THEME["bg_header"])
            if value == current:
                cnv.create_oval(
                    cx - _RADIO_DOT_INNER_R, cx - _RADIO_DOT_INNER_R,
                    cx + _RADIO_DOT_INNER_R, cx + _RADIO_DOT_INNER_R,
                    outline="", fill=THEME["accent"])

    def _set_window_icon(self) -> None:
        """设置窗口图标为程序目录下的 icon.png（打包后从 _MEIPASS 读取）。"""
        if getattr(sys, "frozen", False):
            base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(sys.executable)))
        else:
            base = os.path.dirname(os.path.abspath(__file__))
        icon_png = os.path.join(base, "icon.png")
        icon_ico = os.path.join(base, "icon.ico")
        try:
            if platform.system() == "Windows" and os.path.isfile(icon_ico):
                self.iconbitmap(icon_ico)
            elif os.path.isfile(icon_png):
                self._icon_photo = tk.PhotoImage(file=icon_png)
                self.iconphoto(True, self._icon_photo)
        except Exception:
            pass

    # ── Main UI init ─────────────────────────────────────────────

    def _init_main_ui(self) -> None:
        self._update_splash_progress(0.10, "正在创建窗口...")

        self.title(f"Green 磁盘空间可视化工具 {_VERSION}")
        self.configure(bg=THEME["bg_deep"])

        scr_w = self.winfo_screenwidth()
        scr_h = self.winfo_screenheight()
        win_w = max(1200, int(scr_w * 0.72))
        win_h = max(820, int(scr_h * 0.80))
        win_x = (scr_w - win_w) // 2
        win_y = max(0, (scr_h - win_h) // 2 - 20)
        self.geometry(f"{win_w}x{win_h}+{win_x}+{win_y}")

        self._setup_theme()
        self._set_window_icon()

        self._is_admin: bool = _is_admin()

        self._current_thread: threading.Thread | None = None
        self._scan_result: ScanResult | None = None
        self._resize_after_id: str | None = None

        self._progress_files: int = 0
        self._progress_folders: int = 0
        self._progress_ratio: float = 0.0
        self._progress_last_path: str = ""
        self._scan_start_time: float = 0.0
        self._progress_updater_running: bool = False
        self._progress_history: list = []

        self._live_hierarchy: dict = {}
        self._last_live_draw: float = 0.0
        self._scan_mode: str = "fast"
        self._font_cache: dict = {}

        self._update_splash_progress(0.25, "正在创建界面组件...")

        # Top toolbar
        top_frame = tk.Frame(self, bg=THEME["bg_header"])
        top_frame.pack(side=tk.TOP, fill=tk.X)

        inner = ttk.Frame(top_frame, style="Header.TFrame")
        inner.pack(fill=tk.BOTH, expand=True, padx=10, pady=8)

        ttk.Label(inner, text="选择磁盘:",
                  style="Header.TLabel").pack(side=tk.LEFT)
        self.disk_var = tk.StringVar()
        self.disk_combo = ttk.Combobox(
            inner, textvariable=self.disk_var,
            state="readonly", width=22)
        self.disk_combo.pack(side=tk.LEFT, padx=(4, 12))

        self.scan_button = ttk.Button(
            inner, text="  扫描  ", command=self.on_scan_clicked)
        self.scan_button.pack(side=tk.LEFT)

        self.mode_var = tk.StringVar(value="fast")
        self._scan_mode_canvases: List[tuple] = []  # [(value, canvas), ...]
        mode_frame = tk.Frame(inner, bg=THEME["bg_header"])
        mode_frame.pack(side=tk.LEFT, padx=(20, 0))
        for text, value in [("快速扫描", "fast"), ("完整扫描", "full")]:
            padx = (0, 12) if value == "fast" else (0, 0)
            self._add_big_dot_radio(mode_frame, text, value, padx)
        self.mode_var.trace_add("write", lambda *a: self._draw_scan_mode_dots())
        self._draw_scan_mode_dots()

        self._update_splash_progress(0.40, "正在创建界面组件...")

        # Info + progress row
        info_frame = ttk.Frame(self)
        info_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=(6, 0))

        self.info_var = tk.StringVar(value='请选择磁盘并点击"扫描"。')
        ttk.Label(info_frame, textvariable=self.info_var,
                  anchor="w").pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.progress = ttk.Progressbar(
            self, mode="determinate", maximum=1000)
        self.progress.pack(side=tk.TOP, fill=tk.X, padx=10, pady=(4, 2))

        # Canvas
        self.canvas = tk.Canvas(
            self, bg=THEME["canvas_bg"], highlightthickness=0,
            width=800, height=500)
        self.canvas.pack(side=tk.TOP, fill=tk.BOTH, expand=True,
                         padx=10, pady=(4, 4))
        self.canvas.bind("<Configure>", self._on_canvas_configure)

        # Status bar：用 tk.Label 避免 ttk 主题裁切，足够高度+居左
        status_bar = tk.Frame(self, bg=THEME["bg_header"], height=48)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        status_bar.pack_propagate(False)

        self.status_var = tk.StringVar(value="")
        status_label = tk.Label(
            status_bar,
            textvariable=self.status_var,
            bg=THEME["bg_header"],
            fg=THEME["text_dim"],
            font=("Segoe UI", 9),
            anchor="w",
            justify="left",
        )
        status_label.pack(side=tk.LEFT, fill=tk.BOTH, expand=True,
                         padx=(14, 14), pady=10)

        self._update_splash_progress(0.65, "正在检测磁盘信息...")
        self.load_disks()

        self._update_splash_progress(1.0, "启动完成")
        self.after(300, self._close_splash)

    def _close_splash(self) -> None:
        try:
            self._splash.destroy()
        except Exception:
            pass
        self.deiconify()
        if not self._is_admin:
            self.info_var.set(
                '提示：当前以非管理员权限运行，MFT加速扫描不可用，'
                '部分系统目录可能无法读取。点击"扫描"使用标准模式。')

    # ── Disk / scan logic ────────────────────────────────────────

    def load_disks(self) -> None:
        disks = list_disks()
        display_items = [f"{device} ({mount})" for device, mount in disks]
        self._disk_mounts = [mount for _, mount in disks]
        self.disk_combo["values"] = display_items
        if display_items:
            self.disk_combo.current(0)
            self.info_var.set('请选择磁盘并点击"扫描"。')
        else:
            self.info_var.set("未发现可扫描的磁盘。")

    def on_scan_clicked(self) -> None:
        if self._current_thread and self._current_thread.is_alive():
            messagebox.showinfo("扫描进行中",
                                "当前已有扫描任务在执行，请稍候。")
            return

        idx = self.disk_combo.current()
        if idx < 0 or idx >= len(getattr(self, "_disk_mounts", [])):
            messagebox.showwarning("请选择磁盘", "请先选择一个磁盘。")
            return

        mount = self._disk_mounts[idx]
        mode = self.mode_var.get()
        self._scan_mode = mode

        if mode == "fast":
            exclude = [
                "$Recycle.Bin", "System Volume Information",
                "\\Windows\\WinSxS", "\\Windows\\Temp",
                "\\Windows\\Installer", "\\Program Files\\WindowsApps",
                "\\AppData\\Local\\Temp",
                ".git", "node_modules", "__pycache__",
            ]
            options = ScanOptions(
                path=mount, recursive=True, follow_symlinks=False,
                calculate_hash=False, exclude_patterns=exclude,
                max_depth=None, collect_file_details=False)
            self.info_var.set(
                f"正在快速扫描：{mount}（智能聚合模式，排除系统/临时目录）...")
        else:
            exclude = ["$Recycle.Bin", "System Volume Information"]
            options = ScanOptions(
                path=mount, recursive=True, follow_symlinks=False,
                calculate_hash=False, exclude_patterns=exclude,
                max_depth=None)
            self.info_var.set(
                f"正在完整扫描：{mount}（可能耗时较长，请耐心等待）...")

        self._scan_start_time = time.time()
        self._progress_files = 0
        self._progress_folders = 0
        self._progress_ratio = 0.0
        self._progress_last_path = ""
        self._progress_phase_message = ""  # MFT 阶段提示，如「正在读取MFT文件表...」
        self._progress_updater_running = True
        self._progress_history = []
        self._last_live_draw = 0.0
        self.progress["value"] = 0
        self.canvas.delete("all")
        self.status_var.set("进度：0.0%  预计剩余时间：估算中...")

        self._live_hierarchy = {}

        self.after(200, self._update_progress_ui)

        def worker():
            try:
                result = scan_path(
                    options,
                    progress_callback=self._on_scan_progress,
                    shared_hierarchy=self._live_hierarchy)
            except Exception as e:
                self.after(0, lambda: self.on_scan_failed(str(e)))
                return
            self.after(0, lambda: self.on_scan_finished(result))

        t = threading.Thread(target=worker, daemon=True)
        self._current_thread = t
        t.start()

    def on_scan_finished(self, result: ScanResult) -> None:
        self._progress_updater_running = False
        self.progress["value"] = self.progress["maximum"]
        self._scan_result = result

        method_text = "MFT加速" if result.scan_method == "mft" else "标准"
        self.info_var.set(
            f"扫描完成（{method_text}）："
            f"文件 {result.stats.file_count} 个，"
            f"文件夹 {result.stats.folder_count} 个，"
            f"用时 {result.scan_duration_ms} ms。")
        self.status_var.set(
            f"总容量: {self._format_size(result.stats.total_size)}  "
            f"已用: {self._format_size(result.stats.used_size)}  "
            f"可用: {self._format_size(result.stats.free_size)}")

        self._draw_treemap_from_hierarchy(result.hierarchy, is_live=False)

    def on_scan_failed(self, message: str) -> None:
        self._progress_updater_running = False
        messagebox.showerror("扫描失败",
                             f"扫描过程中出现错误：\n{message}")

    # ── Progress / progressive rendering ─────────────────────────

    def _on_scan_progress(self, files: int, folders: int,
                          current_path: str, ratio: float) -> None:
        self._progress_files = files
        self._progress_folders = folders
        self._progress_last_path = current_path
        self._progress_ratio = max(0.0, min(ratio, 1.0))
        # 阶段提示（如「正在读取MFT文件表...」）用于底栏显示
        if current_path.startswith("正在") or current_path.startswith("开始"):
            self._progress_phase_message = current_path
        else:
            self._progress_phase_message = ""

    def _update_progress_ui(self) -> None:
        if not self._progress_updater_running:
            return

        ratio = self._progress_ratio
        self.progress["value"] = int(ratio * self.progress["maximum"])

        now = time.time()
        self._progress_history.append((now, ratio))
        cutoff = now - 15
        self._progress_history = [
            (t, r) for t, r in self._progress_history if t >= cutoff]

        eta = "估算中..."
        # 仅在扫描进度达到一定比例且过去一段时间后才开始估算，
        # 避免前期因为样本太少导致的严重高估。
        if (len(self._progress_history) >= 2
                and ratio >= 0.05):
            old_t, old_r = self._progress_history[0]
            dt = now - old_t
            dr = ratio - old_r
            if dt >= 10.0 and dr > 0.01:
                speed = dr / dt
                remaining = max(0.0, (1.0 - ratio) / speed)
                mins, secs = int(remaining // 60), int(remaining % 60)
                eta = f"{mins}分{secs}秒" if mins else f"{secs}秒"

        if self._progress_phase_message:
            self.status_var.set(
                f"{self._progress_phase_message}  ({ratio * 100:.1f}%)")
        else:
            self.status_var.set(
                f"进度：{ratio * 100:.1f}%  "
                f"已扫描文件 {self._progress_files} 个 / "
                f"目录 {self._progress_folders} 个  "
                f"预计剩余时间：{eta}")

        now = time.time()
        if (self._live_hierarchy
                and now - self._last_live_draw >= 1.5):
            self._last_live_draw = now
            self._draw_treemap_from_hierarchy(
                self._live_hierarchy, is_live=True)

        self.after(500, self._update_progress_ui)

    # ── Font helpers ──────────────────────────────────────────────

    def _get_font(self, size: int, bold: bool = False) -> tkfont.Font:
        key = (size, bold)
        f = self._font_cache.get(key)
        if f is None:
            weight = "bold" if bold else "normal"
            f = tkfont.Font(family="Segoe UI", size=size, weight=weight)
            self._font_cache[key] = f
        return f

    def _truncate_text(self, text: str, max_px: int,
                       font: tkfont.Font) -> str:
        """Truncate *text* so it fits within *max_px* pixels."""
        if max_px <= 4 or not text:
            return ""
        if font.measure(text) <= max_px:
            return text
        for i in range(len(text), 0, -1):
            t = text[:i] + "\u2026"
            if font.measure(t) <= max_px:
                return t
        return ""

    # ── Treemap rendering (recursive N-level) ────────────────────

    def _draw_treemap_from_hierarchy(
            self, hierarchy: dict, *, is_live: bool = False) -> None:
        self.canvas.delete("all")
        if not hierarchy:
            return

        width = max(self.canvas.winfo_width(), 800)
        height = max(self.canvas.winfo_height(), 500)

        grand_total = sum(
            v["total"] for v in hierarchy.values()
            if isinstance(v, dict) and "total" in v)
        if grand_total <= 0:
            return

        max_depth = (_MAX_DEPTH_FULL if self._scan_mode == "full"
                     else _MAX_DEPTH_FAST)

        sorted_top = sorted(
            hierarchy.items(),
            key=lambda kv: kv[1]["total"] if isinstance(kv[1], dict) else 0,
            reverse=True)

        MIN_RATIO = 0.006
        main_items: list[tuple[str, dict]] = []
        other_size = 0
        other_count = 0
        for name, data in sorted_top:
            if not isinstance(data, dict):
                continue
            if data["total"] / grand_total >= MIN_RATIO:
                main_items.append((name, data))
            else:
                other_size += data["total"]
                other_count += 1
        if other_count > 0 and other_size > 0:
            main_items.append(
                (f"其他 ({other_count} 项)",
                 {"total": other_size, "children": {}}))

        top_nodes = build_treemap(
            [(n, d["total"], d) for n, d in main_items],
            width=width, height=height)

        GAP = 2
        for i, node in enumerate(top_nodes):
            hue = _BASE_HUES[i % len(_BASE_HUES)]
            data = node.data if isinstance(node.data, dict) else {}

            bx = node.x + GAP
            by = node.y + GAP
            bw = node.width - GAP * 2
            bh = node.height - GAP * 2
            if bw < 4 or bh < 4:
                continue

            self._draw_block(
                node.label, data,
                bx, by, bw, bh,
                hue, depth=0, max_depth=max_depth,
                grand_total=grand_total)

        if is_live:
            self.canvas.create_text(
                width - 10, 10, anchor="ne",
                text="扫描中...",
                fill=THEME["accent"],
                font=("Segoe UI", 9, "bold"))

    def _draw_block(self, name: str, data: dict,
                    x: float, y: float, w: float, h: float,
                    hue: int, depth: int, max_depth: int,
                    grand_total: float) -> None:
        """Recursively draw a treemap block with optional children."""
        children = data.get("children", {})
        total = data.get("total", 0)
        if total <= 0:
            return

        pct = total / grand_total * 100 if grand_total > 0 else 0
        size_text = self._format_size(int(total))

        has_expandable = (
            isinstance(children, dict)
            and len(children) > 0
            and any(
                (v.get("total", 0) if isinstance(v, dict) else 0)
                > _EXPAND_THRESHOLD
                for v in children.values()
            )
        )

        di = min(depth, len(_HEADER_HEIGHTS) - 1)
        min_w = _MIN_BLOCK_W[di]
        min_h = _MIN_BLOCK_H[di]

        should_expand = (
            depth < max_depth
            and has_expandable
            and w >= min_w and h >= min_h
        )

        if should_expand:
            self._draw_expanded_block(
                name, size_text, pct, children,
                x, y, w, h, hue, depth, max_depth, grand_total, total)
        else:
            self._draw_leaf_block(
                name, size_text, pct, x, y, w, h, hue, depth)

    def _draw_expanded_block(
            self, label: str, size_text: str, pct: float,
            children: dict,
            x: float, y: float, w: float, h: float,
            hue: int, depth: int, max_depth: int,
            grand_total: float, parent_total: float) -> None:
        di = min(depth, len(_HEADER_HEIGHTS) - 1)
        header_h = _HEADER_HEIGHTS[di]
        font_sz = _FONT_SIZES[di]

        sat = max(0.15, 0.30 - depth * 0.03)
        lum = min(0.22, 0.14 + depth * 0.02)

        bg = _hsl_to_hex(hue, sat, lum)
        border = _hsl_to_hex(hue, sat + 0.08, lum + 0.18)
        self.canvas.create_rectangle(
            x, y, x + w, y + h, fill=bg, outline=border, width=1)

        hdr_color = _hsl_to_hex(hue, sat + 0.20, lum + 0.14)
        self.canvas.create_rectangle(
            x, y, x + w, y + header_h, fill=hdr_color, outline="")

        hdr_font = self._get_font(font_sz, bold=True)
        avail_hdr = w - 10
        if avail_hdr > hdr_font.measure(label + "   " + size_text + " ("):
            ht = f"{label}   {size_text} ({pct:.1f}%)"
        elif avail_hdr > hdr_font.measure(label + "  " + size_text):
            ht = f"{label}  {size_text}"
        else:
            ht = label
        ht = self._truncate_text(ht, avail_hdr, hdr_font)

        if ht:
            self.canvas.create_text(
                x + 5, y + header_h / 2, anchor="w", text=ht,
                fill="#f0f0f0", font=hdr_font)

        cx = x + 1
        cy = y + header_h + 1
        cw = w - 2
        ch = h - header_h - 2
        if cw < 10 or ch < 10:
            return

        sorted_ch = sorted(
            children.items(),
            key=lambda kv: kv[1].get("total", 0)
                           if isinstance(kv[1], dict) else 0,
            reverse=True)

        MAX_CHILDREN = 30
        if len(sorted_ch) > MAX_CHILDREN:
            main = sorted_ch[:MAX_CHILDREN]
            rest_size = sum(
                (v.get("total", 0) if isinstance(v, dict) else 0)
                for _, v in sorted_ch[MAX_CHILDREN:])
            rest_count = len(sorted_ch) - MAX_CHILDREN
            if rest_size > 0:
                main.append(
                    (f"其他 ({rest_count} 项)",
                     {"total": rest_size, "children": {}}))
            sorted_ch = main

        total_ch = sum(
            v.get("total", 0) if isinstance(v, dict) else 0
            for _, v in sorted_ch)
        if total_ch <= 0:
            return

        MIN_CHILD_RATIO = 0.004
        filtered: list[tuple[str, dict]] = []
        other_sz = 0
        other_cnt = 0
        for cn, cv in sorted_ch:
            if not isinstance(cv, dict):
                continue
            ct = cv.get("total", 0)
            if ct / total_ch >= MIN_CHILD_RATIO:
                filtered.append((cn, cv))
            else:
                other_sz += ct
                other_cnt += 1
        if other_cnt > 0 and other_sz > 0:
            filtered.append(
                (f"其他 ({other_cnt} 项)",
                 {"total": other_sz, "children": {}}))
        if not filtered:
            return

        child_nodes = build_treemap(
            [(n, d["total"], d) for n, d in filtered],
            width=int(cw), height=int(ch))

        CHILD_GAP = 1
        for j, cn in enumerate(child_nodes):
            bx2 = cn.x + cx + CHILD_GAP
            by2 = cn.y + cy + CHILD_GAP
            bw2 = cn.width - CHILD_GAP * 2
            bh2 = cn.height - CHILD_GAP * 2
            if bw2 < 3 or bh2 < 3:
                continue

            child_data = cn.data if isinstance(cn.data, dict) else {}
            child_hue = hue + (j * 7) % 20 - 10

            self._draw_block(
                cn.label, child_data,
                bx2, by2, bw2, bh2,
                child_hue, depth + 1, max_depth, grand_total)

    def _draw_leaf_block(self, label: str, size_text: str, pct: float,
                         x: float, y: float, w: float, h: float,
                         hue: int, depth: int) -> None:
        di = min(depth, len(_FONT_SIZES) - 1)
        font_sz = _FONT_SIZES[di]

        sat = max(0.25, 0.45 - depth * 0.04)
        lum = min(0.40, 0.28 + depth * 0.03)

        fill = _hsl_to_hex(hue, sat, lum)
        outline = _hsl_to_hex(hue, sat - 0.10, lum + 0.12)
        self.canvas.create_rectangle(
            x, y, x + w, y + h, fill=fill, outline=outline, width=1)

        pad = 4
        avail_w = w - pad * 2
        if avail_w < 8:
            return

        name_font = self._get_font(font_sz, bold=True)
        sub_sz = max(5, font_sz - 1)
        sub_font = self._get_font(sub_sz, bold=False)
        name_line_h = name_font.metrics("linespace")
        sub_line_h = sub_font.metrics("linespace")

        two_line_h = pad + name_line_h + 2 + sub_line_h + pad
        one_line_h = pad + sub_line_h + pad

        if w >= 60 and h >= two_line_h:
            disp = self._truncate_text(label, avail_w, name_font)
            if disp:
                self.canvas.create_text(
                    x + pad, y + pad, anchor="nw", text=disp,
                    fill="#f0f0f0", font=name_font)
            sub_text = f"{size_text} ({pct:.1f}%)"
            sub_disp = self._truncate_text(sub_text, avail_w, sub_font)
            if sub_disp:
                self.canvas.create_text(
                    x + pad, y + pad + name_line_h + 2, anchor="nw",
                    text=sub_disp, fill="#cccccc", font=sub_font)
        elif w >= 32 and h >= one_line_h:
            disp = self._truncate_text(label, avail_w, sub_font)
            if disp:
                self.canvas.create_text(
                    x + pad, y + pad, anchor="nw", text=disp,
                    fill="#d8d8d8", font=sub_font)
        elif w >= 18 and h >= 10:
            tiny_font = self._get_font(5, bold=False)
            disp = self._truncate_text(label, w - 4, tiny_font)
            if disp:
                self.canvas.create_text(
                    x + 2, y + 2, anchor="nw", text=disp,
                    fill="#b0b0b0", font=tiny_font)

    # ── Canvas resize ────────────────────────────────────────────

    def _on_canvas_configure(self, event: tk.Event) -> None:  # type: ignore[type-arg]
        if self._scan_result is None:
            return
        if event.width < 100 or event.height < 100:
            return
        if self._resize_after_id is not None:
            self.after_cancel(self._resize_after_id)
        self._resize_after_id = self.after(150, self._deferred_redraw)

    def _deferred_redraw(self) -> None:
        self._resize_after_id = None
        if self._scan_result is not None:
            self._draw_treemap_from_hierarchy(
                self._scan_result.hierarchy, is_live=False)

    # ── Utility ──────────────────────────────────────────────────

    @staticmethod
    def _format_size(size: int) -> str:
        if size <= 0:
            return "0 B"
        units = ["B", "KB", "MB", "GB", "TB"]
        idx = 0
        value = float(size)
        while value >= 1024 and idx < len(units) - 1:
            value /= 1024.0
            idx += 1
        return f"{value:.2f} {units[idx]}"


def main() -> None:
    _hide_console()
    _init_dpi_awareness()
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
