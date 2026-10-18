"""
桌面 GUI 美化工具模块
=====================
包含: 配色方案、窗口 Mica 效果、WTreeview 主题、右键菜单等

pip 依赖:
    pip install customtkinter pywinstyles

用法:
    from ui_utils import (ThemeColors, CTkPopupMenu,
                          apply_window_effect, apply_treeview_theme,
                          create_card, create_sidebar_button, create_accent_button)
"""

import os
import subprocess
import threading
import time
import re
from pathlib import Path
from queue import Queue
from tkinter import filedialog, messagebox

import tkinter as tk
from tkinter import ttk
from typing import Optional, Callable

import customtkinter as ctk

try:
    import pywinstyles
    HAS_PYWINSTYLES = True
except ImportError:
    HAS_PYWINSTYLES = False


# ═══════════════════════════════════════════════════════
# 1. 配色方案
# ═══════════════════════════════════════════════════════

class ThemeColors:
    """明/暗双主题完整色板。

    用法:
        c = ThemeColors.palette(dark=True)  # 暗色
        c = ThemeColors.palette(dark=False) # 亮色
    """
    @staticmethod
    def palette(dark: bool = False) -> dict:
        if dark:
            return {
                "bg": "#0d1117",
                "surface": "#161b22",
                "card": "#1c2333",
                "border": "#30363d",
                "fg": "#e6edf3",
                "fg2": "#8b949e",
                "accent": "#58a6ff",
                "accent_hover": "#4090e0",
                "accent_text": "#ffffff",
                "danger": "#f85149",
                "danger_hover": "#da3633",
                "success": "#3fb950",
                "header_bg": "#161b22",
                "header_fg": "#e6edf3",
                "row_alt": "#0d1117",
                "row": "#0d1117",
                "select_bg": "#1f6feb",
                "select_fg": "#ffffff",
                "input_bg": "#0d1117",
                "input_fg": "#e6edf3",
                "button_bg": "#21262d",
                "button_hover": "#30363d",
                "button_active": "#30363d",
                "separator": "#30363d",
                "row_hover": "#1a2332",
            }
        else:
            return {
                "bg": "#fafbfc",
                "surface": "#f0f2f5",
                "card": "#ffffff",
                "border": "#d0d7de",
                "fg": "#1c1e29",
                "fg2": "#656d76",
                "accent": "#4263eb",
                "accent_hover": "#3451d1",
                "accent_text": "#ffffff",
                "danger": "#cf222e",
                "danger_hover": "#a40e26",
                "success": "#1a7f37",
                "header_bg": "#f0f2f5",
                "header_fg": "#3d4153",
                "row_alt": "#f6f8fa",
                "row": "#ffffff",
                "select_bg": "#4263eb",
                "select_fg": "#ffffff",
                "input_bg": "#ffffff",
                "input_fg": "#1c1e29",
                "button_bg": "#f0f2f5",
                "button_hover": "#d0d7de",
                "button_active": "#c4cad3",
                "separator": "#d0d7de",
                "row_hover": "#eef1f7",
            }


# ═══════════════════════════════════════════════════════
# 2. 窗口 Mica / Acrylic 效果
# ═══════════════════════════════════════════════════════

def apply_window_effect(window: tk.Toplevel, dark: bool = False, bg_color: str = "#0d1117"):
    """对任意窗口应用 Windows 11 标题栏效果。

    参数:
        window:   目标 tk.Toplevel 或 ctk.CTk
        dark:     True = 暗色标题栏, False = 亮色
        bg_color: 标题栏底色 (与窗口背景保持一致)
    """
    if not HAS_PYWINSTYLES:
        return
    try:
        if dark:
            pywinstyles.apply_style(window, "dark")
        else:
            pywinstyles.apply_style(window, "normal")
        pywinstyles.change_header_color(window, bg_color)
    except Exception:
        pass


def apply_mica(window: tk.Toplevel, dark: bool = False, bg_color: str = "#0d1117"):
    """apply_window_effect 的别名, 语义更明确。"""
    apply_window_effect(window, dark, bg_color)


# ═══════════════════════════════════════════════════════
# 3. Treeview 主题 (ttk)
# ═══════════════════════════════════════════════════════

def apply_treeview_theme(tree: ttk.Treeview, c: dict, font_family: str = "微软雅黑",
                         font_size: int = 14, row_height: int = 40):
    """美化 ttk.Treeview: 行高、表头、选中态、交替行色。

    参数:
        tree:        目标 ttk.Treeview
        c:           ThemeColors.palette() 返回的色板
        font_family: 字体名
        font_size:   字号
        row_height:  行高 (px)
    """
    style = ttk.Style()
    style.theme_use('clam')

    style.configure('.',
                    background=c['bg'],
                    foreground=c['fg'],
                    fieldbackground=c['input_bg'],
                    font=(font_family, font_size))

    style.configure('TFrame', background=c['bg'], borderwidth=0, relief='flat')

    style.configure('Treeview',
                    background=c['row'],
                    foreground=c['fg'],
                    fieldbackground=c['row'],
                    rowheight=row_height,
                    borderwidth=0,
                    relief='flat')

    style.configure('Treeview.Heading',
                    background=c['header_bg'],
                    foreground=c['header_fg'],
                    relief='flat',
                    borderwidth=0,
                    padding=(12, 10),
                    font=(font_family, font_size, 'bold'))

    style.map('Treeview.Heading',
              background=[('active', c['button_hover'])],
              bordercolor=[('!focus', c['header_bg'])])

    style.map('Treeview',
              background=[('selected', c['select_bg'])],
              foreground=[('selected', c['select_fg'])],
              bordercolor=[('!focus', c['row']), ('focus', c['row'])])

    style.layout('Treeview', [('Treeview.treearea', {'sticky': 'nswe', 'border': '0'})])

    # Tag configuration for alternating rows
    tree.tag_configure('row', background=c['row'])
    tree.tag_configure('alt', background=c['row_alt'])
    tree.tag_configure('hover', background=c['row_hover'])

    # Disable keyboard navigation (optional)
    try:
        tree.tk.eval('bind Treeview <KeyPress> {}')
    except Exception:
        pass

    # Set ctk appearance mode to match
    ctk.set_appearance_mode("dark" if c['bg'] == "#0d1117" else "light")


# ═══════════════════════════════════════════════════════
# 4. 自定义 CTk 右键菜单
# ═══════════════════════════════════════════════════════

class CTkPopupMenu:
    """现代圆角弹出菜单, 替代 tk.Menu。

    用法:
        menu = CTkPopupMenu(parent_window, ThemeColors.palette(dark=True),
                            font_family="微软雅黑", font_size=14)
        menu.add_command(label="打开文件", icon="📄", command=open_file)
        menu.add_separator()
        menu.add_command(label="删除", icon="🗑", command=delete, danger=True)
        menu.popup(x, y)
    """

    def __init__(self, parent: tk.Widget, c: dict = None,
                 font_family: str = "微软雅黑", font_size: int = 14):
        if c is None:
            c = ThemeColors.palette(dark=False)
        self.parent = parent
        self.c = c
        self.font_family = font_family
        self.font_size = font_size
        self._win: Optional[tk.Toplevel] = None
        self._items: list = []
        self._bind_id: Optional[str] = None

    def add_command(self, label: str, command: Callable, icon: str = "",
                    danger: bool = False, disabled: bool = False):
        """添加菜单项。"""
        self._items.append({
            'type': 'command',
            'label': label,
            'command': command,
            'icon': icon,
            'danger': danger,
            'disabled': disabled,
        })

    def add_separator(self):
        """添加分割线。"""
        self._items.append({'type': 'separator'})

    def popup(self, x: int, y: int):
        """在屏幕坐标 (x, y) 弹出菜单。"""
        self._show(x, y)

    # ── 内部实现 ──

    def _show(self, x, y):
        c = self.c

        self._win = tk.Toplevel(self.parent)
        self._win.overrideredirect(True)
        self._win.attributes('-topmost', True)
        self._win.withdraw()

        outer = ctk.CTkFrame(self._win, fg_color=c['border'], corner_radius=10)
        outer.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)

        inner = ctk.CTkFrame(outer, fg_color=c['card'], corner_radius=9)
        inner.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)

        for item in self._items:
            if item['type'] == 'separator':
                sep = ctk.CTkFrame(inner, height=1, fg_color=c['border'], corner_radius=0)
                sep.pack(fill=tk.X, padx=10, pady=4)
            else:
                self._create_menu_item(inner, item)

        self._win.bind('<FocusOut>', lambda e: self._dismiss())
        self._win.bind('<Escape>', lambda e: self._dismiss())

        self._win.update_idletasks()
        w = self._win.winfo_reqwidth()
        h = self._win.winfo_reqheight()

        screen_w = self.parent.winfo_screenwidth()
        screen_h = self.parent.winfo_screenheight()
        if x + w > screen_w:
            x = screen_w - w - 4
        if y + h > screen_h:
            y = screen_h - h - 4
        x = max(4, x)
        y = max(4, y)

        self._win.geometry(f"+{x}+{y}")
        self._win.deiconify()

        self._bind_id = self.parent.bind('<Button-1>', lambda e: self._dismiss_global(e), add='+')

    def _create_menu_item(self, parent, item):
        c = self.c
        fg = c['danger'] if item['danger'] else c['fg']
        hover_bg = c['danger_hover'] if item['danger'] else c['accent']
        state = "disabled" if item['disabled'] else "normal"
        label = f"  {item['icon']}  {item['label']}" if item['icon'] else f"  {item['label']}"

        btn = ctk.CTkButton(
            parent,
            text=label,
            font=(self.font_family, self.font_size),
            fg_color="transparent",
            hover_color=hover_bg,
            text_color=fg,
            text_color_disabled=c['fg2'],
            corner_radius=6,
            height=34,
            anchor="w",
            state=state,
            command=item['command'] if not item['disabled'] else None,
        )
        btn.pack(fill=tk.X, padx=6, pady=2)

    def _dismiss(self, event=None):
        self._destroy()

    def _dismiss_global(self, event=None):
        if self._win and event:
            wx = self._win.winfo_rootx()
            wy = self._win.winfo_rooty()
            ww = self._win.winfo_width()
            wh = self._win.winfo_height()
            if wx <= event.x_root <= wx + ww and wy <= event.y_root <= wy + wh:
                return
        self._destroy()

    def _destroy(self):
        if self._bind_id:
            try:
                self.parent.unbind('<Button-1>', self._bind_id)
            except Exception:
                pass
            self._bind_id = None
        if self._win:
            try:
                self._win.destroy()
            except Exception:
                pass
            self._win = None


# ═══════════════════════════════════════════════════════
# 5. 快捷组件工厂
# ═══════════════════════════════════════════════════════

def create_card(parent, c: dict, corner_radius: int = 10, **pack_kw) -> ctk.CTkFrame:
    """创建带边框的卡片容器。"""
    card = ctk.CTkFrame(parent, fg_color=c['card'], corner_radius=corner_radius,
                        border_width=1, border_color=c['border'])
    if pack_kw:
        card.pack(**pack_kw)
    return card


def create_separator(parent, c: dict, horizontal: bool = True, **pack_kw) -> ctk.CTkFrame:
    """创建分割线。"""
    if horizontal:
        sep = ctk.CTkFrame(parent, height=1, corner_radius=0, fg_color=c['border'])
    else:
        sep = ctk.CTkFrame(parent, width=1, corner_radius=0, fg_color=c['border'])
    if pack_kw:
        sep.pack(**pack_kw)
    return sep


def create_sidebar_button(parent, text: str, c: dict, command: Callable,
                          font_family: str = "微软雅黑", font_size: int = 14,
                          accent: bool = False, bold: bool = False, **pack_kw) -> ctk.CTkButton:
    """创建侧边栏风格按钮 (自动配色)。"""
    if accent:
        btn = ctk.CTkButton(parent, text=text, command=command,
                            font=(font_family, font_size, 'bold' if bold else 'normal'),
                            fg_color=c['accent'], hover_color=c['accent_hover'],
                            text_color=c['accent_text'],
                            corner_radius=8, height=38)
    else:
        btn = ctk.CTkButton(parent, text=text, command=command,
                            font=(font_family, font_size, 'bold' if bold else 'normal'),
                            fg_color=c['button_bg'], hover_color=c['button_hover'],
                            text_color=c['fg'],
                            corner_radius=8, height=36)
    if pack_kw:
        btn.pack(**pack_kw)
    return btn


def create_label(parent, text: str, c: dict, role: str = "fg",
                 font_family: str = "微软雅黑", font_size: int = 14,
                 bold: bool = False, offset: int = 0, **pack_kw) -> ctk.CTkLabel:
    """创建标签 (自动配色)。"""
    lbl = ctk.CTkLabel(parent, text=text,
                       text_color=c[role],
                       font=(font_family, font_size + offset, 'bold' if bold else 'normal'),
                       anchor="w")
    if pack_kw:
        lbl.pack(**pack_kw)
    return lbl


def create_entry(parent, variable, c: dict,
                 font_family: str = "微软雅黑", font_size: int = 14,
                 width: int = 200, **pack_kw) -> ctk.CTkEntry:
    """创建输入框 (自动配色 + 边框)。"""
    entry = ctk.CTkEntry(parent, textvariable=variable,
                         fg_color=c['input_bg'], text_color=c['fg'],
                         font=(font_family, font_size),
                         corner_radius=8, border_width=1,
                         border_color=c['border'], width=width)
    if pack_kw:
        entry.pack(**pack_kw)
    return entry


# ═══════════════════════════════════════════════════════
# 6. 通用辅助
# ═══════════════════════════════════════════════════════

def _lighten(hex_color: str, factor: float = 0.1) -> str:
    """将 hex 颜色变亮。"""
    if not hex_color or not hex_color.startswith('#'):
        return hex_color or '#000000'
    hex_color = hex_color.lstrip('#')
    r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    r = min(255, int(r + (255 - r) * factor))
    g = min(255, int(g + (255 - g) * factor))
    b = min(255, int(b + (255 - b) * factor))
    return f"#{r:02x}{g:02x}{b:02x}"


def _darken(hex_color: str, factor: float = 0.1) -> str:
    """将 hex 颜色变暗。"""
    if not hex_color or not hex_color.startswith('#'):
        return hex_color or '#000000'
    hex_color = hex_color.lstrip('#')
    r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    r = max(0, int(r * (1 - factor)))
    g = max(0, int(g * (1 - factor)))
    b = max(0, int(b * (1 - factor)))
    return f"#{r:02x}{g:02x}{b:02x}"


def center_window(window: tk.Toplevel):
    """将窗口居中显示。"""
    window.update_idletasks()
    w = window.winfo_width()
    h = window.winfo_height()
    sw = window.winfo_screenwidth()
    sh = window.winfo_screenheight()
    x = (sw - w) // 2
    y = (sh - h) // 2
    window.geometry(f"+{x}+{y}")


# ═══════════════════════════════════════════════════════
# 7. 格式转换弹窗 — FormatConvertDialog
# ═══════════════════════════════════════════════════════

class FormatConvertDialog:
    """三步式格式转换弹窗：选格式 → 选预设 → 设置输出 → 执行。

    用法:
        dlg = FormatConvertDialog(app, file_paths, file_durations)
        # app 需要有 .t(key) 翻译方法 和 ._get_tree_colors() 配色方法
    """

    FORMATS = [
        {'name': 'MP4',  'ext': '.mp4',  'recommended': True},
        {'name': 'MKV',  'ext': '.mkv',  'recommended': False},
        {'name': 'WebM', 'ext': '.webm', 'recommended': False},
        {'name': 'AVI',  'ext': '.avi',  'recommended': False},
        {'name': 'MOV',  'ext': '.mov',  'recommended': False},
    ]

    PRESETS = [
        {
            'key': 'h265',
            'label_key': 'format_preset_h265',
            'desc_key': 'format_preset_h265_desc',
            'video_codec': 'libx265',
            'crf': '23',
            'audio_codec': 'aac',
            'audio_bitrate': '128k',
            'extra': '-preset medium',
        },
        {
            'key': 'h264',
            'label_key': 'format_preset_h264',
            'desc_key': 'format_preset_h264_desc',
            'video_codec': 'libx264',
            'crf': '23',
            'audio_codec': 'aac',
            'audio_bitrate': '128k',
            'extra': '-preset medium',
        },
        {
            'key': 'gpu',
            'label_key': 'format_preset_gpu',
            'desc_key': 'format_preset_gpu_desc',
            'video_codec': 'hevc_nvenc',
            'crf': '',
            'audio_codec': 'aac',
            'audio_bitrate': '128k',
            'extra': '-hwaccel cuda -preset p7 -tune hq -rc vbr -cq 23 -qmin 18 -qmax 30',
        },
        {
            'key': 'copy',
            'label_key': 'format_preset_copy',
            'desc_key': 'format_preset_copy_desc',
            'video_codec': 'copy',
            'crf': '',
            'audio_codec': 'copy',
            'audio_bitrate': '',
            'extra': '',
        },
        {
            'key': 'audio',
            'label_key': 'format_preset_audio',
            'desc_key': 'format_preset_audio_desc',
            'video_codec': '',
            'crf': '',
            'audio_codec': 'libmp3lame',
            'audio_bitrate': '192k',
            'extra': '-vn',
        },
    ]

    _PROG_KEYS = ('frame=', 'fps=', 'q=', 'size=', 'out_time', 'dup_frames=',
                  'drop_frames=', 'progress=', 'bitrate=',
                  'total_size=', 'stream_', 'out_time_ms=', 'out_time_us=')

    def __init__(self, app, file_paths, file_durations):
        self.app = app
        self.file_paths = file_paths
        self.file_durations = file_durations
        self.total_duration = sum(file_durations.values())
        self.running = False
        self._cancelled = False

        # default selections
        self.target_format = 'MP4'
        self.selected_preset = None

        c = self._c()
        f = app.font_family
        s = app.font_size

        self.win = ctk.CTkToplevel(app.root)
        self.win.title(app.t('format_title'))
        self.win.geometry("820x600")
        self.win.minsize(700, 550)
        icon = Path(__file__).parent / "app_icon.ico"
        if icon.exists():
            self.win.iconbitmap(bitmap=str(icon), default=str(icon))
        self.win.transient(app.root)
        self.win.grab_set()
        self.win.configure(fg_color=c['bg'])

        apply_mica(self.win, dark=(app.current_theme == 'dark'), bg_color=c['bg'])

        self.win.withdraw()
        self._build_ui()
        self._center_on_parent()
        self.win.deiconify()

        self.win.protocol("WM_DELETE_WINDOW", self._on_close)

        # Select first preset by default
        self._on_preset_change(self.PRESETS[0]['key'])

    def _c(self):
        return self.app._get_tree_colors()

    def _f(self):
        return self.app.font_family

    def _s(self):
        return self.app.font_size

    # ── Window close ──────────────────────────────
    def _on_close(self):
        if self.running and not self._cancelled:
            t = self.app.t
            messagebox.showwarning(t('warning'), t('batch_running_warn'), parent=self.win)
            return
        self.win.destroy()

    def _center_on_parent(self):
        self.win.update_idletasks()
        root = self.app.root
        root.update_idletasks()
        rw = root.winfo_width()
        rh = root.winfo_height()
        rx = root.winfo_rootx()
        ry = root.winfo_rooty()
        ww = self.win.winfo_width()
        wh = self.win.winfo_height()
        x = rx + (rw - ww) // 2
        y = ry + (rh - wh) // 2
        self.win.geometry(f"+{x}+{y}")

    # ── Build entire UI (left-right split) ──────
    def _build_ui(self):
        c = self._c()
        f = self._f()
        s = self._s()
        t = self.app.t

        # ── Header ──
        header = ctk.CTkFrame(self.win, fg_color="transparent", corner_radius=0)
        header.pack(fill=tk.X, padx=24, pady=(18, 10))
        if getattr(self.app, '_logo', None) is not None:
            ctk.CTkLabel(header, image=self.app._logo, text="", width=26, height=26) \
                .pack(side=tk.LEFT, padx=(0, 10))
        create_label(header, t('format_title'), c, role='fg',
                     font_family=f, font_size=s, offset=2, bold=True).pack(side=tk.LEFT)
        create_label(header, t('batch_selected', len(self.file_paths)), c, role='fg2',
                     font_family=f, font_size=s, offset=-1).pack(side=tk.RIGHT)

        # ── Body: left-right split ──
        body = ctk.CTkFrame(self.win, fg_color="transparent", corner_radius=0)
        body.pack(fill=tk.BOTH, expand=True, padx=24, pady=(0, 8))
        body.grid_columnconfigure(0, weight=0, minsize=380)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)

        # === LEFT: Settings ===
        left_card = ctk.CTkFrame(body, fg_color=c['card'], corner_radius=10,
                                 border_width=1, border_color=c['border'])
        left_card.grid(row=0, column=0, sticky='nsew', padx=(0, 6))
        left_card.grid_columnconfigure(0, weight=1)

        # -- Format buttons (2 rows: 3 + 2) --
        fmt_section = ctk.CTkFrame(left_card, fg_color="transparent", corner_radius=0)
        fmt_section.grid(row=0, column=0, sticky='ew', padx=14, pady=(12, 6))

        create_label(fmt_section, t('format_target'), c, role='fg2',
                     font_family=f, font_size=s, offset=-1, bold=True).pack(anchor='w', padx=(2, 0))

        self.fmt_buttons = {}
        rows = [self.FORMATS[:3], self.FORMATS[3:]]
        for r, row_fmts in enumerate(rows):
            row_frame = ctk.CTkFrame(fmt_section, fg_color="transparent", corner_radius=0)
            row_frame.pack(fill=tk.X, pady=(4, 0))
            for fmt in row_fmts:
                sel = (fmt['name'] == self.target_format)
                text = f"★ {fmt['name']}" if fmt['recommended'] else fmt['name']
                btn = ctk.CTkButton(
                    row_frame, text=text,
                    font=(f, s),
                    fg_color=c['accent'] if sel else c['button_bg'],
                    hover_color=c['accent_hover'] if sel else c['button_hover'],
                    text_color=c['accent_text'] if sel else c['fg'],
                    corner_radius=8,
                    height=46, width=110,
                    command=lambda ft=fmt['name']: self._on_format_select(ft))
                btn.pack(side=tk.LEFT, padx=(0, 6))
                self.fmt_buttons[fmt['name']] = btn

        create_separator(left_card, c).grid(row=1, column=0, sticky='ew', padx=14, pady=(4, 2))

        # -- Preset radios --
        preset_section = ctk.CTkFrame(left_card, fg_color="transparent", corner_radius=0)
        preset_section.grid(row=2, column=0, sticky='ew', padx=14, pady=(4, 4))

        create_label(preset_section, t('format_preset'), c, role='fg2',
                     font_family=f, font_size=s, offset=-1, bold=True).pack(anchor='w', padx=(2, 0), pady=(0, 4))

        self.preset_buttons = {}

        # Two rows of preset buttons
        preset_rows = [self.PRESETS[:3], self.PRESETS[3:]]
        for row_presets in preset_rows:
            btn_row = ctk.CTkFrame(preset_section, fg_color="transparent", corner_radius=0)
            btn_row.pack(fill=tk.X, pady=(2, 0))
            for p in row_presets:
                btn = ctk.CTkButton(
                    btn_row, text=self.app.t(p['label_key']),
                    font=(f, s - 1),
                    fg_color=c['button_bg'],
                    hover_color=c['button_hover'],
                    text_color=c['fg'],
                    corner_radius=8,
                    height=42,
                    command=lambda pk=p['key']: self._on_preset_change(pk))
                btn.pack(side=tk.LEFT, padx=(0, 4), fill=tk.X, expand=True)
                self.preset_buttons[p['key']] = btn

        # Dynamic description (shows selected preset's desc)
        self.preset_desc_label = create_label(
            preset_section, '', c, role='fg2',
            font_family=f, font_size=s, offset=-2)
        self.preset_desc_label.pack(anchor='w', padx=(2, 0), pady=(6, 0))

        create_separator(left_card, c).grid(row=3, column=0, sticky='ew', padx=14, pady=(4, 2))

        # -- Output settings --
        out_section = ctk.CTkFrame(left_card, fg_color="transparent", corner_radius=0)
        out_section.grid(row=4, column=0, sticky='ew', padx=14, pady=(4, 12))

        create_label(out_section, t('format_output_dir'), c, role='fg2',
                     font_family=f, font_size=s, offset=-1, bold=True).pack(anchor='w', padx=(2, 0), pady=(0, 4))

        out_row = ctk.CTkFrame(out_section, fg_color="transparent", corner_radius=0)
        out_row.pack(fill=tk.X)

        self.outdir_var = tk.StringVar(value=self.app.t('format_same_as_source'))
        create_entry(out_row, self.outdir_var, c, font_family=f, font_size=s - 1).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))

        ctk.CTkButton(out_row, text=t('format_browse'),
                      font=(f, s - 1),
                      fg_color=c['button_bg'],
                      hover_color=c['button_hover'],
                      text_color=c['fg'],
                      corner_radius=6,
                      width=60, height=32,
                      command=self._browse_output_dir).pack(side=tk.RIGHT)

        self.keep_structure_var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(out_section, text=t('format_keep_structure'),
                        variable=self.keep_structure_var,
                        font=(f, s - 1),
                        text_color=c['fg'],
                        fg_color=c['accent'],
                        hover_color=c['accent_hover'],
                        border_color=c['fg2'],
                        checkmark_color=c['accent_text']).pack(anchor='w', pady=(6, 0))

        # === RIGHT: Monitor ===
        right_card = ctk.CTkFrame(body, fg_color=c['card'], corner_radius=10,
                                  border_width=1, border_color=c['border'])
        right_card.grid(row=0, column=1, sticky='nsew', padx=(6, 0))
        right_card.grid_columnconfigure(0, weight=1)
        right_card.grid_rowconfigure(0, weight=0)   # cmd preview
        right_card.grid_rowconfigure(1, weight=1)   # console
        right_card.grid_rowconfigure(2, weight=0)   # progress

        # -- Command preview --
        cmd_card = ctk.CTkFrame(right_card, fg_color=c['surface'], corner_radius=6)
        cmd_card.grid(row=0, column=0, sticky='ew', padx=12, pady=(12, 6))
        create_label(cmd_card, '▸ ' + t('format_preview_cmd'), c, role='fg2',
                     font_family=f, font_size=s, offset=-1, bold=True).pack(anchor='w', padx=10, pady=(8, 2))
        self.cmd_preview_label = ctk.CTkLabel(
            cmd_card, text='',
            text_color=c['fg'],
            font=(f, s - 1),
            anchor="w", justify="left",
            wraplength=370)
        self.cmd_preview_label.pack(fill=tk.X, padx=10, pady=(0, 8))

        # -- Console --
        console_card = ctk.CTkFrame(right_card, fg_color=c['surface'], corner_radius=6)
        console_card.grid(row=1, column=0, sticky='nsew', padx=12, pady=(0, 6))
        console_card.grid_columnconfigure(0, weight=1)
        console_card.grid_rowconfigure(0, weight=1)

        self.console_text = ctk.CTkTextbox(
            console_card, wrap="word",
            fg_color=c['input_bg'], text_color=c['fg'],
            font=(f, s - 2),
            corner_radius=6, border_width=0)
        self.console_text.grid(row=0, column=0, sticky='nsew', padx=8, pady=(8, 8))
        self.console_text.configure(state="disabled")

        # -- Progress --
        prog_card = ctk.CTkFrame(right_card, fg_color=c['surface'], corner_radius=6)
        prog_card.grid(row=2, column=0, sticky='ew', padx=12, pady=(0, 12))

        self.prog_bar = ctk.CTkProgressBar(prog_card, mode='determinate', height=8, corner_radius=4)
        self.prog_bar.pack(fill=tk.X, padx=10, pady=(10, 4))
        self.prog_bar.set(0)

        self.prog_label = ctk.CTkLabel(prog_card, text='',
                                       text_color=c['fg2'],
                                       font=(f, s - 2), anchor="w")
        self.prog_label.pack(fill=tk.X, padx=10, pady=(0, 10))

        # ── Buttons ──
        btn_row = ctk.CTkFrame(self.win, fg_color="transparent", corner_radius=0)
        btn_row.pack(fill=tk.X, padx=24, pady=(0, 18))

        ctk.CTkButton(btn_row, text=t('format_preview_cmd'),
                      font=(f, s),
                      fg_color=c['button_bg'],
                      hover_color=c['button_hover'],
                      text_color=c['fg'],
                      corner_radius=8,
                      height=38, width=110,
                      command=self._preview_command).pack(side=tk.LEFT)

        ctk.CTkButton(btn_row, text=t('cancel'),
                      font=(f, s),
                      fg_color=c['button_bg'],
                      hover_color=c['button_hover'],
                      text_color=c['fg'],
                      corner_radius=8,
                      height=38, width=90,
                      command=self._on_close).pack(side=tk.RIGHT, padx=(8, 0))

        self.run_btn = ctk.CTkButton(btn_row, text=t('format_start'),
                                     font=(f, s, 'bold'),
                                     fg_color=c['accent'],
                                     hover_color=c['accent_hover'],
                                     text_color=c['accent_text'],
                                     corner_radius=8,
                                     height=38, width=130,
                                     command=self.execute)
        self.run_btn.pack(side=tk.RIGHT)

    # ═══════════════ Callbacks ═══════════════════

    def _on_format_select(self, fmt):
        self.target_format = fmt
        c = self._c()
        for fname, btn in self.fmt_buttons.items():
            sel = (fname == fmt)
            text = f"★ {fname}" if any(
                ft['name'] == fname and ft['recommended'] for ft in self.FORMATS
            ) else fname
            btn.configure(
                text=text,
                fg_color=c['accent'] if sel else c['button_bg'],
                hover_color=c['accent_hover'] if sel else c['button_hover'],
                text_color=c['accent_text'] if sel else c['fg'])
        self._update_cmd_preview()

    def _on_preset_change(self, preset_key):
        self.selected_preset = preset_key
        c = self._c()
        for key, btn in self.preset_buttons.items():
            sel = (key == preset_key)
            btn.configure(
                fg_color=c['accent'] if sel else c['button_bg'],
                hover_color=c['accent_hover'] if sel else c['button_hover'],
                text_color=c['accent_text'] if sel else c['fg'])
        for p in self.PRESETS:
            if p['key'] == preset_key:
                self.preset_desc_label.configure(text=self.app.t(p['desc_key']))
                break
        self._update_cmd_preview()

    def _update_cmd_preview(self):
        """Regenerate command preview from current settings."""
        if not self.file_paths:
            return
        fp = self.file_paths[0]
        folder = os.path.dirname(fp)
        name = os.path.splitext(os.path.basename(fp))[0]
        target_ext = '.mp3' if self.selected_preset == 'audio' else '.' + self.target_format.lower()
        out_path = os.path.join(folder, f"{name}_converted{target_ext}")
        cmd = self._build_command(fp, out_path)
        self.cmd_preview_label.configure(text=cmd)

    def _browse_output_dir(self):
        folder = filedialog.askdirectory(title=self.app.t('format_select_dir'), parent=self.win)
        if folder:
            self.outdir_var.set(folder)

    # ═══════════════ Command Builder ═════════════

    def _build_command(self, input_path, out_path):
        """Build ffmpeg command from current format + preset."""
        preset = next((p for p in self.PRESETS if p['key'] == self.selected_preset), None)
        if not preset:
            return '# Select a preset first'
        parts = ['ffmpeg', '-hide_banner', '-loglevel', 'warning', '-progress', 'pipe:2', '-nostats']
        if preset['video_codec'] == 'hevc_nvenc':
            parts.append('-hwaccel cuda')
        parts.extend(['-i', f'"{input_path}"'])
        # Video
        vc = preset['video_codec']
        if vc == 'copy':
            parts.append('-c:v copy')
        elif vc:
            parts.append(f'-c:v {vc}')
            if vc in ('libx265', 'libx264'):
                parts.extend(['-preset', 'medium', '-crf', preset['crf']])
            elif vc == 'hevc_nvenc':
                parts.extend(['-preset', 'p7', '-tune', 'hq', '-rc', 'vbr',
                              '-cq', '23', '-qmin', '18', '-qmax', '30'])
        # Audio
        ac = preset['audio_codec']
        if ac == 'copy':
            parts.append('-c:a copy')
        elif ac:
            parts.extend(['-c:a', ac, '-b:a', preset['audio_bitrate']])
        else:
            parts.append('-an')
        parts.extend(['-movflags', '+faststart'])
        parts.append(f'"{out_path}"')
        return ' '.join(parts)

    # ═══════════════ Preview ═════════════════════

    def _preview_command(self):
        """Show command preview for the first file in console."""
        self.console_text.configure(state="normal")
        self.console_text.delete('1.0', tk.END)

        fp = self.file_paths[0]
        folder = os.path.dirname(fp)
        name = os.path.splitext(os.path.basename(fp))[0]
        target_ext = '.mp3' if self.selected_preset == 'audio' else '.' + self.target_format.lower()
        out_path = os.path.join(folder, f"{name}_converted{target_ext}")
        cmd = self._build_command(fp, out_path)
        self._log(f"[Preview] {os.path.basename(fp)}")
        self._log(f"  {cmd}")
        if len(self.file_paths) > 1:
            self._log(f"  ... (+ {len(self.file_paths) - 1} more files)")
        self.console_text.configure(state="disabled")

    # ═══════════════ Logging ═════════════════════

    def _log(self, msg):
        self.console_text.configure(state="normal")
        self.console_text.insert(tk.END, msg + '\n')
        self.console_text.see(tk.END)
        self.console_text.configure(state="disabled")
        self.win.update_idletasks()

    def _show_task(self, seq, total, filename, cmd):
        """Update command preview with current task."""
        lines = cmd.split(' -')
        short = ' -'.join(lines[:3])
        if len(short) > 130:
            short = short[:128] + '...'
        self.cmd_preview_label.configure(text=f"[{seq}/{total}] {filename}\n{short}")

    # ═══════════════ Execution ═══════════════════

    def execute(self):
        t = self.app.t
        if not messagebox.askyesno(t('format_start'),
                                   t('format_confirm', len(self.file_paths)),
                                   parent=self.win):
            return

        self.running = True
        self._cancelled = False
        self._active_procs = []
        self._active_outs = {}
        c = self._c()

        self.run_btn.configure(state="disabled", text=t('batch_running'),
                               fg_color=c['button_bg'], hover_color=c['button_hover'])

        # Repurpose cancel button
        for child in self.win.winfo_children():
            if isinstance(child, ctk.CTkFrame):
                for sub in child.winfo_children():
                    if isinstance(sub, ctk.CTkButton):
                        if sub.cget('text') in (t('cancel'), 'Cancel'):
                            sub.configure(text=t('cancel'), command=self.cancel_execution)
                            self._cancel_btn = sub
                            break

        self.console_text.configure(state="normal")
        self.console_text.delete('1.0', tk.END)
        self.console_text.configure(state="disabled")
        self.prog_bar.set(0)
        self.prog_bar.configure(mode='determinate')
        self.prog_label.configure(text=t('batch_eta_unknown'))
        self._batch_start_time = time.time()

        has_durations = self.total_duration > 0
        output_dir = self.outdir_var.get()
        if output_dir == t('format_same_as_source'):
            output_dir = ''
        keep_structure = self.keep_structure_var.get()
        target_ext = '.mp3' if self.selected_preset == 'audio' else '.' + self.target_format.lower()

        def task():
            ok = 0
            fail = 0
            completed_dur = 0.0
            failed_files = []
            lock = threading.Lock()
            active_positions = {}
            total = len(self.file_paths)
            num_workers = 2 if total >= 2 else 1

            work_items = []
            for idx, fp in enumerate(self.file_paths):
                file_dur = self.file_durations.get(fp, 0)
                folder = os.path.dirname(fp)
                name = os.path.splitext(os.path.basename(fp))[0]

                if output_dir and keep_structure:
                    all_dirs = [os.path.dirname(p) for p in self.file_paths]
                    common = os.path.commonpath(all_dirs) if len(all_dirs) > 1 else all_dirs[0]
                    try:
                        rel = os.path.relpath(fp, common)
                    except ValueError:
                        rel = os.path.basename(fp)
                    rel_dir = os.path.dirname(rel)
                    out_folder = os.path.join(output_dir, rel_dir) if rel_dir else output_dir
                    os.makedirs(out_folder, exist_ok=True)
                    out_path = os.path.join(out_folder, f"{name}{target_ext}")
                elif output_dir:
                    out_path = os.path.join(output_dir, f"{name}{target_ext}")
                else:
                    out_path = os.path.join(folder, f"{name}{target_ext}")

                # Avoid overwriting source when input ext == target ext
                if os.path.normpath(out_path) == os.path.normpath(fp):
                    out_path = os.path.join(folder, f"{name}_converted{target_ext}")

                cmd = self._build_command(fp, out_path)
                work_items.append({
                    'fp': fp, 'file_dur': file_dur, 'seq': idx + 1,
                    'cmd': cmd, 'out_path': out_path,
                    'filename': os.path.basename(fp),
                    'is_ffmpeg': True,
                })

            q = Queue()
            for item in work_items:
                q.put(item)
            for _ in range(num_workers):
                q.put(None)

            def worker(wid):
                nonlocal ok, fail, completed_dur, failed_files
                while True:
                    item = q.get()
                    if item is None or self._cancelled:
                        q.task_done()
                        break

                    fp = item['fp']
                    file_dur = item['file_dur']
                    seq = item['seq']
                    out_path = item['out_path']
                    cmd = item['cmd']

                    self.win.after(0, self._log, f"[{seq}/{total}] {item['filename']}")
                    self.win.after(0, self._log, f"  > {cmd}")
                    self.win.after(0, lambda s=seq, t=total, fn=item['filename'], c=cmd:
                                   self._show_task(s, t, fn, c))

                    proc = None
                    try:
                        startupinfo = subprocess.STARTUPINFO()
                        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                        proc = subprocess.Popen(cmd, shell=True,
                                                stdout=subprocess.DEVNULL,
                                                stderr=subprocess.PIPE,
                                                text=True,
                                                encoding='utf-8', errors='replace',
                                                startupinfo=startupinfo)
                        self._active_procs.append(proc)
                        self._active_outs[wid] = out_path

                        with lock:
                            active_positions[wid] = 0.0

                        buf = ''
                        for chunk in iter(lambda: proc.stderr.buffer.read1(4096).decode('utf-8', errors='replace'), ''):
                            if self._cancelled:
                                proc.kill()
                                break
                            buf += chunk
                            while '\n' in buf or '\r' in buf:
                                r_pos = buf.index('\r') if '\r' in buf else 999999
                                n_pos = buf.index('\n') if '\n' in buf else 999999
                                pos = min(r_pos, n_pos)
                                line = buf[:pos]
                                sk = 1
                                if buf[pos] == '\r' and pos + 1 < len(buf) and buf[pos + 1] == '\n':
                                    sk = 2
                                buf = buf[pos + sk:]
                                if not line:
                                    continue
                                if has_durations and file_dur > 0:
                                    if line.startswith('out_time='):
                                        ts = line.split('=', 1)[1]
                                        m = re.match(r'(\d+):(\d+):(\d+)\.(\d+)', ts)
                                        if m:
                                            h, mi, sec, ms = int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4)
                                            t_val = h * 3600 + mi * 60 + sec + int(ms[:3].ljust(3, '0')) / 1000
                                            with lock:
                                                active_positions[wid] = min(t_val, file_dur)
                                                cur_total = completed_dur + sum(active_positions.values())
                                                fraction = cur_total / self.total_duration
                                            self.win.after(0, lambda f=fraction: self._update_progress(ok + fail, f))
                                            continue
                                if any(line.startswith(k) for k in self._PROG_KEYS):
                                    continue
                                if line.startswith('out_time='):
                                    continue
                                self.win.after(0, self._log, f"  {line}")
                        if buf.strip():
                            self.win.after(0, self._log, f"  {buf.strip()}")

                        proc.wait()
                        rc = proc.returncode

                        if proc in self._active_procs:
                            self._active_procs.remove(proc)
                        self._active_outs.pop(wid, None)

                        if self._cancelled:
                            if os.path.exists(out_path):
                                try:
                                    os.remove(out_path)
                                    self.win.after(0, self._log, t('batch_deleted_partial'))
                                except Exception:
                                    pass
                            with lock:
                                active_positions.pop(wid, None)
                            q.task_done()
                            break

                        if rc == 0:
                            with lock:
                                ok += 1
                                completed_dur += file_dur
                                active_positions.pop(wid, None)
                            self.win.after(0, self._log, "  OK")
                        else:
                            with lock:
                                fail += 1
                                failed_files.append(fp)
                                active_positions.pop(wid, None)
                            self.win.after(0, self._log, f"  FAIL (code {rc})")
                    except Exception as e:
                        with lock:
                            fail += 1
                            failed_files.append(fp)
                            active_positions.pop(wid, None)
                        if proc is not None and proc in self._active_procs:
                            self._active_procs.remove(proc)
                        self._active_outs.pop(wid, None)
                        self.win.after(0, self._log, f"  ERROR: {e}")

                    done = ok + fail
                    self.win.after(0, lambda d=done: self._update_progress(d))
                    q.task_done()

            threads = []
            for wid in range(num_workers):
                thr = threading.Thread(target=worker, args=(wid,), daemon=True)
                thr.start()
                threads.append(thr)
            for thr in threads:
                thr.join()

            self.win.after(0, lambda: self._finish(ok, fail, failed_files))

        threading.Thread(target=task, daemon=True).start()

    def cancel_execution(self):
        if not self.running:
            return
        self._cancelled = True
        self._log(self.app.t('batch_cancelling'))
        for proc in list(self._active_procs):
            try:
                proc.kill()
                self._log(self.app.t('batch_killed_proc'))
            except Exception:
                pass
        self._active_procs.clear()

    def _update_progress(self, done, fraction=None):
        total = len(self.file_paths)
        if fraction is not None and self.total_duration > 0:
            self.prog_bar.set(fraction)
            pct = round(fraction * 100)
        else:
            pct = round(done / total * 100) if total > 0 else 0
            self.prog_bar.set(done / total if total > 0 else 0)
        t = self.app.t
        self.prog_label.configure(text=t('batch_progress', done, total, pct))
        if 0 <= done < total and hasattr(self, '_batch_start_time'):
            elapsed = time.time() - self._batch_start_time
            if fraction is not None and fraction > 0 and self.total_duration > 0:
                remaining = elapsed / fraction - elapsed
            elif done > 0:
                remaining = elapsed / done * (total - done)
            else:
                remaining = 0
            if remaining > 0:
                if remaining < 60:
                    eta = f"{round(remaining)}s"
                elif remaining < 3600:
                    eta = f"{int(remaining // 60)}m {round(remaining % 60)}s"
                else:
                    eta = f"{int(remaining // 3600)}h {int((remaining % 3600) // 60)}m"
                self.prog_label.configure(
                    text=self.prog_label.cget('text') + '  |  ' + t('batch_eta', eta))

    def _finish(self, ok, fail, failed_files):
        self.running = False
        self._active_procs.clear()
        self._active_outs.clear()
        t = self.app.t
        self.cmd_preview_label.configure(text='Done.')
        self._log('─' * 50)
        if self._cancelled:
            self._log(t('batch_cancelled_summary', ok, fail))
        else:
            self._log(t('batch_done', ok, fail))
        c = self._c()
        self.run_btn.configure(state="normal", text=t('format_start'),
                               fg_color=c['accent'], hover_color=c['accent_hover'])
        if hasattr(self, '_cancel_btn') and self._cancel_btn.winfo_exists():
            self._cancel_btn.configure(text=t('cancel'), command=self._on_close)
        if failed_files:
            msg = t('failed_files_hdr', len(failed_files))
            for fp in failed_files:
                msg += f"  {os.path.basename(fp)}\n"
            self.win.after(100, lambda m=msg: messagebox.showwarning(
                t('batch_fail_title'), m, parent=self.win))
        elif ok > 0 and not self._cancelled:
            msg = t('batch_success_msg', ok)
            def _cb():
                if messagebox.askyesno(t('batch_success_title'),
                                       f"{msg}\n\n{t('batch_success_ask')}",
                                       parent=self.win):
                    self.win.destroy()
                    self.app.refresh_current_folder()
            self.win.after(150, _cb)
