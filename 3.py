import os
import subprocess
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, font, simpledialog
from pathlib import Path
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from datetime import datetime
import time
import traceback
import sys
import re

import customtkinter as ctk

try:
    import pywinstyles
    HAS_PYWINSTYLES = True
except ImportError:
    HAS_PYWINSTYLES = False


def send2trash(filepath):
    """Move file to Windows recycle bin using shell API."""
    import ctypes
    from ctypes import wintypes
    path = os.path.normpath(os.path.abspath(filepath))
    buf = ctypes.create_unicode_buffer(path + '\0\0')

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [
            ("hwnd", wintypes.HWND),
            ("wFunc", wintypes.UINT),
            ("pFrom", wintypes.LPCWSTR),
            ("pTo", wintypes.LPCWSTR),
            ("fFlags", wintypes.WORD),
            ("fAnyOperationsAborted", wintypes.BOOL),
            ("hNameMappings", wintypes.LPVOID),
            ("lpszProgressTitle", wintypes.LPCWSTR),
        ]

    fo = SHFILEOPSTRUCTW()
    fo.hwnd = 0
    fo.wFunc = 3
    fo.pFrom = ctypes.cast(buf, wintypes.LPCWSTR)
    fo.pTo = None
    fo.fFlags = 0x40 | 0x10 | 0x4 | 0x400
    fo.fAnyOperationsAborted = False
    ret = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(fo))
    if ret != 0:
        raise OSError(f"SHFileOperationW failed with code {ret}")
    if fo.fAnyOperationsAborted:
        raise OSError("Recycle bin operation aborted")


def setup_exception_logging():
    desktop = Path.home() / "Desktop"
    log_file = desktop / "video_info_error.log"
    def excepthook(exc_type, exc_value, exc_tb):
        with open(log_file, 'w', encoding='utf-8') as f:
            traceback.print_exception(exc_type, exc_value, exc_tb, file=f)
        messagebox.showerror("Error", f"Program encountered an error. Details saved to:\n{log_file}")
        sys.__excepthook__(exc_type, exc_value, exc_tb)
    sys.excepthook = excepthook


VIDEO_EXT = {
    '.mp4', '.avi', '.mkv', '.mov', '.flv', '.wmv', '.m4v', '.webm',
    '.ts', '.mts', '.m2ts', '.3gp', '.ogv', '.rmvb', '.asf', '.vob',
    '.f4v', '.divx', '.mpg', '.mpeg'
}

AUDIO_EXT = {
    '.mp3', '.aac', '.flac', '.wav', '.ogg', '.wma', '.m4a', '.opus',
    '.ac3', '.dts', '.alac', '.aiff', '.ape', '.wv', '.amr', '.ra',
    '.mid', '.midi', '.caf', '.au', '.pcm'
}

MEDIA_EXT = VIDEO_EXT | AUDIO_EXT

TEXTS = {
    'zh': {
        'title': "媒体统计 v2.4.0 · A (GitHub)",
        'select_folder': "选择文件夹",
        'export_txt': "导出 TXT",
        'no_folder': "未选择文件夹",
        'sort_label': "排序",
        'sort_name': "文件名",
        'sort_size': "大小",
        'sort_duration': "时长",
        'sort_vbr': "视频码率",
        'sort_abr': "音频码率",
        'asc': "升序",
        'desc': "降序",
        'select_all': "全选",
        'deselect_all': "取消全选",
        'ready': "就绪",
        'total_duration': "全部总时长: {}",
        'selected_stats': "已勾选: {} 个 | 总时长: {} | 总大小: {}",
        'scanning': "正在扫描...",
        'found': "共找到 {} 个媒体文件",
        'no_video': "未找到媒体文件",
        'warning': "警告",
        'info': "信息",
        'error': "错误",
        'export_confirm_checked': "已勾选 {} 个文件，确定导出这些文件？",
        'export_confirm_all': "未勾选任何文件，确定导出当前列表的全部 {} 个文件？",
        'export_success': "已成功导出到:\n{}",
        'export_failed': "导出失败",
        'no_data': "没有数据可导出，请先扫描文件夹。",
        'ffprobe_warning': "未检测到 ffprobe，无法获取媒体时长。\n请安装 FFmpeg 或将 ffprobe.exe 放在程序目录。",
        'settings': "设置",
        'appearance': "外观",
        'theme': "主题",
        'theme_light': "浅色",
        'theme_dark': "深色",
        'theme_auto': "跟随系统时间",
        'font_settings': "字体设置",
        'font_family': "字体",
        'font_size': "字号",
        'language': "语言",
        'apply': "应用",
        'cancel': "取消",
        'preview': "预览文本 ABC 123",
        'column_check': "✓",
        'column_index': "#",
        'column_filename': "文件名",
        'column_size': "大小",
        'column_duration': "时长",
        'column_vbr': "视频码率",
        'column_abr': "音频码率",
        'unknown': "未知",
        'total_files': "总媒体数量: {}",
        'folder_total_duration': "文件夹总时长: {}",
        'exported_total_duration': "导出文件总时长: {}",
        'exported_total_size': "导出文件总大小: {}",
        'rename': "重命名",
        'delete': "删除",
        'rename_prompt': "请输入新文件名（不含路径）:",
        'rename_exists': "文件名已存在，请重新输入。",
        'delete_confirm': "确定要将选中的 {} 个文件移到回收站吗？",
        'delete_success': "已将 {} 个文件移到回收站。",
        'delete_error': "移动到回收站时出错: {}",
        'rename_error': "重命名失败: {}",
        'open_file': "打开文件",
        'open_location': "打开文件所在位置",
        'app_title': "媒体统计",
        'app_subtitle': "专业版 v2.4.0",
        'videos': "媒体",
        'duration_label': "时长",
        'size_label': "大小",
        'open_folder': "打开文件夹",
        'browse': "浏览",
        'selection': "已选择",
        'folder_stats': "文件夹统计",
        'selection_stats': "选择统计",
        'export_heading': "媒体文件导出报表",
        'export_all': "全部",
        'filter_label': "筛选格式",
        'filter_all': "全部格式",
        'batch_cmd': "批量命令",
        'batch_title': "批量处理命令",
        'batch_presets': "预设命令",
        'batch_hint': "可用变量: {input} 输入路径  {output} 输出路径  {name} 文件名(无后缀)  {ext} 后缀  {folder} 所在目录",
        'batch_output_suffix': "输出文件后缀",
        'batch_selected': "已选择 {} 个文件",
        'batch_run': "执行",
        'batch_running': "执行中...",
        'batch_done': "完成: 成功 {} 个, 失败 {} 个",
        'batch_no_files': "请先在列表中勾选要处理的文件",
        'batch_confirm': "将对 {} 个文件执行命令，确定继续？",
        'batch_progress': "进度: {}/{} ({}%)",
        'batch_eta': "预计剩余: {}",
        'batch_eta_unknown': "预计剩余: 计算中...",
        'history_cmd': "历史命令：",
        'batch_cancelling': "⚠ 正在取消...",
        'batch_killed_proc': "  已终止一个进程",
        'batch_deleted_partial': "  已删除未完成的输出文件",
        'batch_cancelled_summary': "已取消  |  成功 {} 个, 失败 {} 个",
        'batch_running_warn': "任务正在执行中，请先点击取消按钮。",
        'batch_fail_title': "处理失败",
        'batch_success_title': "处理完成",
        'batch_success_msg': "全部 {} 个文件处理成功！",
        'batch_success_ask': "是否返回主页面并刷新文件夹？",
        'failed_files_hdr': "以下 {} 个文件处理失败：\n\n",
        # Preset labels & comments
        'preset_x265_crf23_label': '压缩75% (x265 CRF23 软编)',
        'preset_x265_crf23_comment': '# 文件压缩至75%原始大小, 尽量保持画质, 软件x265编码, 多线程',
        'preset_x265_crf26_label': '压缩50% (x265 CRF26 软编)',
        'preset_x265_crf26_comment': '# 文件压缩至50%原始大小, 尽量保持画质, 软件x265编码, 多线程',
        'preset_nvenc_hevc_cq23_label': 'GPU压缩75% (NVENC HEVC)',
        'preset_nvenc_hevc_cq23_comment': '# GPU硬件加速(NVIDIA独立显卡)压缩75%, HEVC编码, 速度快画质好',
        'preset_nvenc_hevc_cq26_label': 'GPU压缩50% (NVENC HEVC)',
        'preset_nvenc_hevc_cq26_comment': '# GPU硬件加速(NVIDIA独立显卡)压缩50%, HEVC编码, 速度快',
        'preset_nvenc_h264_label': 'GPU转H.264 (NVENC 兼容优先)',
        'preset_nvenc_h264_comment': '# GPU硬件加速(NVIDIA独立显卡)转H.264, 兼容性广, 保持画质',
    },
    'en': {
        'title': "Media Stats v2.4.0 · A (GitHub)",
        'select_folder': "Open Folder",
        'export_txt': "Export TXT",
        'no_folder': "No folder selected",
        'sort_label': "Sort by",
        'sort_name': "Name",
        'sort_size': "Size",
        'sort_duration': "Duration",
        'sort_vbr': "Video BR",
        'sort_abr': "Audio BR",
        'asc': "Ascending",
        'desc': "Descending",
        'select_all': "Select All",
        'deselect_all': "Deselect All",
        'ready': "Ready",
        'total_duration': "Total Duration: {}",
        'selected_stats': "Selected: {} files | Duration: {} | Size: {}",
        'scanning': "Scanning...",
        'found': "Found {} media file(s)",
        'no_video': "No media files found",
        'warning': "Warning",
        'info': "Info",
        'error': "Error",
        'export_confirm_checked': "{} file(s) checked. Export these files?",
        'export_confirm_all': "No files checked. Export all {} file(s) in the current list?",
        'export_success': "Successfully exported to:\n{}",
        'export_failed': "Export failed",
        'no_data': "No data to export. Please scan a folder first.",
        'ffprobe_warning': "ffprobe not detected. Media duration will be unavailable.\nPlease install FFmpeg or place ffprobe.exe beside this program.",
        'settings': "Settings",
        'appearance': "Appearance",
        'theme': "Theme",
        'theme_light': "Light",
        'theme_dark': "Dark",
        'theme_auto': "Auto (time-based)",
        'font_settings': "Font Settings",
        'font_family': "Font Family",
        'font_size': "Font Size",
        'language': "Language",
        'apply': "Apply",
        'cancel': "Cancel",
        'preview': "Preview Text ABC 123",
        'column_check': "✓",
        'column_index': "#",
        'column_filename': "Filename",
        'column_size': "Size",
        'column_duration': "Duration",
        'column_vbr': "Video BR",
        'column_abr': "Audio BR",
        'unknown': "Unknown",
        'total_files': "Total files: {}",
        'folder_total_duration': "Folder total duration: {}",
        'exported_total_duration': "Exported total duration: {}",
        'exported_total_size': "Exported total size: {}",
        'rename': "Rename",
        'delete': "Delete",
        'rename_prompt': "Enter new filename (without path):",
        'rename_exists': "Filename already exists, please enter a different name.",
        'delete_confirm': "Move {} selected file(s) to Recycle Bin?",
        'delete_success': "Moved {} file(s) to Recycle Bin.",
        'delete_error': "Error moving to Recycle Bin: {}",
        'rename_error': "Rename failed: {}",
        'open_file': "Open File",
        'open_location': "Open File Location",
        'app_title': "Media Stats",
        'app_subtitle': "Pro v2.4.0",
        'videos': "Media",
        'duration_label': "Duration",
        'size_label': "Size",
        'open_folder': "Open Folder",
        'browse': "Browse",
        'selection': "Selection",
        'folder_stats': "Folder Stats",
        'selection_stats': "Selection Stats",
        'export_heading': "Media File Export Report",
        'export_all': "All",
        'filter_label': "Filter",
        'filter_all': "All Formats",
        'batch_cmd': "Batch Command",
        'batch_title': "Batch Process Command",
        'batch_presets': "Presets",
        'batch_hint': "Variables: {input} in path  {output} out path  {name} name(no ext)  {ext} extension  {folder} directory",
        'batch_output_suffix': "Output suffix",
        'batch_selected': "{} file(s) selected",
        'batch_run': "Execute",
        'batch_running': "Running...",
        'batch_done': "Done: {} OK, {} failed",
        'batch_no_files': "Please check files in the list first",
        'batch_confirm': "Execute command on {} file(s), continue?",
        'batch_progress': "Progress: {}/{} ({}%)",
        'batch_eta': "ETA: {}",
        'batch_eta_unknown': "ETA: calculating...",
        'history_cmd': "History:",
        'batch_cancelling': "⚠ Cancelling...",
        'batch_killed_proc': "  Killed one process",
        'batch_deleted_partial': "  Deleted incomplete output file",
        'batch_cancelled_summary': "Cancelled | OK: {}  Failed: {}",
        'batch_running_warn': "Task is running. Please click Cancel first.",
        'batch_fail_title': "Process Failed",
        'batch_success_title': "Process Complete",
        'batch_success_msg': "All {} file(s) processed successfully!",
        'batch_success_ask': "Return to main page and refresh folder?",
        'failed_files_hdr': "Following {} file(s) failed:\n\n",
        # Preset labels & comments
        'preset_x265_crf23_label': 'Compress 75% (x265 CRF23 CPU)',
        'preset_x265_crf23_comment': '# Compress to 75% size, maintain quality, CPU x265 encoding, multi-thread',
        'preset_x265_crf26_label': 'Compress 50% (x265 CRF26 CPU)',
        'preset_x265_crf26_comment': '# Compress to 50% size, maintain quality, CPU x265 encoding, multi-thread',
        'preset_nvenc_hevc_cq23_label': 'GPU Compress 75% (NVENC HEVC)',
        'preset_nvenc_hevc_cq23_comment': '# GPU hardware (NVIDIA) compress 75%, HEVC encoding, fast speed, good quality',
        'preset_nvenc_hevc_cq26_label': 'GPU Compress 50% (NVENC HEVC)',
        'preset_nvenc_hevc_cq26_comment': '# GPU hardware (NVIDIA) compress 50%, HEVC encoding, fast speed',
        'preset_nvenc_h264_label': 'GPU to H.264 (NVENC Compatibility)',
        'preset_nvenc_h264_comment': '# GPU hardware (NVIDIA) to H.264, wide compatibility, maintain quality',
    }
}



class ToggleComboBox(ctk.CTkComboBox):
    """CTkComboBox that toggles dropdown on arrow click."""
    def _open_dropdown_menu(self):
        dm = getattr(self, "_dropdown_menu", None)
        if getattr(self, '_menu_visible', False):
            self._menu_visible = False
            if dm is not None:
                try:
                    dm.unpost()
                except Exception:
                    pass
            return

        self._menu_visible = True
        super()._open_dropdown_menu()

        # Detect external dismiss (click elsewhere) to keep flag accurate
        if dm is not None and not getattr(self, '_unmap_bound', False):
            def _on_unmap(e):
                self._menu_visible = False
            dm.bind('<Unmap>', _on_unmap, add='+')
            self._unmap_bound = True

    def _dropdown_callback(self, value):
        self._menu_visible = False
        super()._dropdown_callback(value)


class VideoInfoApp:
    def __init__(self, root):
        self.root = root
        self.lang = 'zh'
        self.theme_mode = 'light'
        self.current_theme = 'light'
        base_dir = Path(sys.executable if getattr(sys, 'frozen', False) else __file__).parent
        self.config_file = base_dir / "config.json"
        self.geometry_file = base_dir / "window_geometry.json"
        self.load_config()

        # Sync current_theme with loaded theme_mode
        if self.theme_mode == 'auto':
            self.current_theme = 'dark' if self.is_dark_time() else 'light'
        else:
            self.current_theme = self.theme_mode

        self.root.title(self.t('title'))
        self.root.withdraw()
        self.root.geometry(self.saved_geometry if hasattr(self, 'saved_geometry') else "1200x780")
        self.root.minsize(850, 680)
        self.root.resizable(True, True)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.bind("<Configure>", self.on_window_configure)

        self.video_list = []
        self.display_data = []
        self.sort_column = 'name'
        self.sort_reverse = False
        self.item_data_map = {}
        self.check_vars = []
        self.filter_format = None
        self.available_formats = set()

        self.ffprobe_path = self.find_ffprobe()
        if not self.ffprobe_path:
            messagebox.showwarning(self.t('warning'), self.t('ffprobe_warning'))

        self.last_geometry = self.root.geometry()
        self.drag_start_item = None
        self.drag_selection_state = None
        self.current_folder = None

        ctk.set_appearance_mode("dark" if self.current_theme == "dark" else "light")
        ctk.set_default_color_theme("dark-blue")

        self.setup_styles()
        self.setup_ui()
        self.apply_font_to_all()
        if self.saved_geometry and '+' not in self.saved_geometry:
            self.center_window(self.root)
        self.root.deiconify()

        if self.theme_mode == 'auto':
            self.schedule_theme_check()

    # ---------- Helpers ----------
    def t(self, key, *args):
        text = TEXTS[self.lang].get(key, key)
        if args:
            return text.format(*args)
        return text

    def _default_font(self):
        available = set(font.families())
        for name in ('宋体', 'SimSun', '微软雅黑', 'Microsoft YaHei', 'Segoe UI'):
            if name in available:
                return name
        return 'Segoe UI'

    def load_config(self):
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    self.lang = config.get('language', 'zh')
                    self.theme_mode = config.get('theme_mode', 'light')
            except:
                self.lang = 'zh'
                self.theme_mode = 'light' if self.theme_mode != 'light' else 'dark'
        else:
            self.lang = 'zh'
            self.theme_mode = 'light'
        self.font_family = '宋体'
        self.font_size = 14

        if self.geometry_file.exists():
            try:
                with open(self.geometry_file, 'r', encoding='utf-8') as f:
                    geo_data = json.load(f)
                    self.saved_geometry = geo_data.get('main', '1200x780')
            except:
                self.saved_geometry = '1200x780'
        else:
            self.saved_geometry = '1200x780'

    def save_config(self):
        config = {
            'language': self.lang,
            'theme_mode': self.theme_mode
        }
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2)
        except:
            pass

    def save_geometry(self):
        geo = self.root.geometry()
        try:
            with open(self.geometry_file, 'w', encoding='utf-8') as f:
                json.dump({'main': geo}, f)
        except:
            pass

    def on_window_configure(self, event):
        current = self.root.geometry()
        if current != self.last_geometry:
            self.last_geometry = current
            if hasattr(self, '_save_geo_after'):
                self.root.after_cancel(self._save_geo_after)
            self._save_geo_after = self.root.after(1000, self.save_geometry)

    def on_close(self):
        self.save_geometry()
        self.save_config()
        self.root.destroy()

    def is_dark_time(self):
        now = datetime.now().time()
        start = datetime.strptime("18:00", "%H:%M").time()
        end = datetime.strptime("06:00", "%H:%M").time()
        return start <= now or now <= end

    def update_theme_by_mode(self):
        old_c = self._get_tree_colors()
        if self.theme_mode == 'auto':
            self.current_theme = 'dark' if self.is_dark_time() else 'light'
        else:
            self.current_theme = self.theme_mode
        ctk.set_appearance_mode("dark" if self.current_theme == "dark" else "light")
        self._apply_treeview_theme()
        self._refresh_custom_colors(old_c)

        # Belt-and-suspenders: force every known widget to the correct theme color
        self._force_color(self._get_tree_colors())
        # Safety: ensure all main containers are explicitly refreshed
        c = self._get_tree_colors()
        if hasattr(self, 'sidebar') and self.sidebar.winfo_exists():
            try:
                self.sidebar.master.configure(fg_color=c['bg'])
                self.sidebar.configure(fg_color=c['surface'])
            except Exception:
                pass
        if hasattr(self, 'content_frame'):
            try:
                self.content_frame.configure(fg_color=c['bg'])
            except Exception:
                pass
        self.update_theme_button_text()
        self._update_pywinstyles()

    def _refresh_custom_colors(self, old_c):
        """Re-apply explicit fg_color/text_color/hover_color after theme switch.
        Walks all widgets from root. Uses cget() directly (not .keys()) because
        CTk widgets hide their custom attributes from .keys()."""
        new_c = self._get_tree_colors()

        _TEXT_ROLES = {'fg', 'fg2', 'accent_text', 'select_fg', 'header_fg', 'input_fg'}

        old_hex_roles = [(role, val) for role, val in old_c.items()
                         if isinstance(val, str) and val.startswith('#')]
        old_bg_roles = [(r, v) for r, v in old_hex_roles if r not in _TEXT_ROLES]
        old_txt_roles = [(r, v) for r, v in old_hex_roles if r in _TEXT_ROLES]

        def _try_refresh_attr(w, attr, old_role_list):
            try:
                cur = w.cget(attr)
            except Exception:
                return
            if not isinstance(cur, str):
                return
            for role, old_val in old_role_list:
                if cur.lower() == old_val.lower():
                    try:
                        w.configure(**{attr: new_c[role]})
                    except Exception:
                        pass
                    return

        def _refresh(w):
            _try_refresh_attr(w, 'fg_color', old_bg_roles)
            _try_refresh_attr(w, 'text_color', old_txt_roles)
            _try_refresh_attr(w, 'hover_color', old_hex_roles)
            try:
                children = w.winfo_children()
            except Exception:
                return
            for child in children:
                _refresh(child)

        # Traverse from root so Toplevel windows (batch dialog) are included
        if hasattr(self, 'root') and self.root.winfo_exists():
            _refresh(self.root)
        elif hasattr(self, 'sidebar') and self.sidebar.winfo_exists():
            _refresh(self.sidebar.master)


    def schedule_theme_check(self):
        self.update_theme_by_mode()
        self.root.after(3600000, self.schedule_theme_check)

    def _force_color(self, c):
        """Force-set known widgets to theme colors. No cget, no matching."""
        _NORMAL_BTNS = [
            'btn_select_all', 'btn_deselect_all', 'btn_export', 'btn_batch',
            'btn_theme', 'btn_lang', 'btn_order', 'btn_refresh',
        ]
        for name in _NORMAL_BTNS:
            btn = getattr(self, name, None)
            if btn is not None and btn.winfo_exists():
                btn.configure(fg_color=c['button_bg'],
                              text_color=c['fg'],
                              hover_color=c['button_hover'])
        if hasattr(self, 'btn_open') and self.btn_open.winfo_exists():
            self.btn_open.configure(fg_color=c['accent'],
                                    text_color=c['accent_text'],
                                    hover_color=c['accent_hover'])
        # Sidebar / toolbar / statusbar labels — fg2 (secondary text)
        for attr in ('lbl_stats_heading', 'lbl_sel_heading',
                     'lbl_app_subtitle', 'lbl_folder_label',
                     'lbl_sort', 'lbl_filter', 'lbl_status', 'lbl_hint'):
            lbl = getattr(self, attr, None)
            if lbl is not None and lbl.winfo_exists():
                lbl.configure(text_color=c['fg2'])
        # Sidebar / toolbar / statusbar labels — fg (primary text)
        for attr in ('lbl_stats_total', 'lbl_stats_duration', 'lbl_stats_size',
                     'lbl_sel_count', 'lbl_sel_duration', 'lbl_sel_size',
                     'lbl_app_title', 'lbl_folder'):
            lbl = getattr(self, attr, None)
            if lbl is not None and lbl.winfo_exists():
                lbl.configure(text_color=c['fg'])
        for attr in ('stats_card', 'sel_card'):
            card = getattr(self, attr, None)
            if card is not None and card.winfo_exists():
                card.configure(fg_color=c['card'])
        if hasattr(self, 'separator') and self.separator.winfo_exists():
            self.separator.configure(fg_color=c['border'])

    def _update_pywinstyles(self):
        if not HAS_PYWINSTYLES:
            return
        try:
            c = self._get_tree_colors()
            if self.current_theme == 'dark':
                pywinstyles.apply_style(self.root, "dark")
                pywinstyles.change_header_color(self.root, c['bg'])
            else:
                pywinstyles.apply_style(self.root, "normal")
                pywinstyles.change_header_color(self.root, c['bg'])
        except Exception:
            pass

    def _get_tree_colors(self):
        """A · Light + GitHub dark"""
        is_dark = self.current_theme == "dark"
        if is_dark:
            return {
                "bg": "#0d1117",
                "surface": "#161b22",
                "card": "#1a1f27",
                "border": _lighten("#161b22", 0.12),
                "fg": "#e6edf3",
                "fg2": "#8b949e",
                "accent": "#58a6ff",
                "accent_hover": _lighten("#58a6ff", 0.15),
                "accent_text": "#ffffff",
                "danger": "#f85149",
                "danger_hover": "#ff6b63",
                "success": "#3fb950",
                "header_bg": "#161b22",
                "header_fg": "#e6edf3",
                "row_alt": _lighten("#0d1117", 0.03),
                "row": "#0d1117",
                "select_bg": "#58a6ff",
                "select_fg": "#ffffff",
                "input_bg": _lighten("#0d1117", 0.04),
                "input_fg": "#e6edf3",
                "button_bg": "#161b22",
                "button_hover": _lighten("#161b22", 0.12),
                "button_active": _lighten("#161b22", 0.12),
                "separator": _lighten("#161b22", 0.12),
                "row_hover": _lighten("#0d1117", 0.05),
            }
        else:
            return {
                "bg": "#f8f9fb",
                "surface": "#f5f6f9",
                "card": "#f3f4f6",
                "border": "#e1e4ed",
                "fg": "#1c1e29",
                "fg2": "#6e7489",
                "accent": "#4263eb",
                "accent_hover": "#3651d5",
                "accent_text": "#ffffff",
                "danger": "#e03131",
                "danger_hover": "#c92a2a",
                "success": "#2f9e44",
                "header_bg": "#eef0f5",
                "header_fg": "#3d4153",
                "row_alt": "#f5f6fa",
                "row": "#ffffff",
                "select_bg": "#4263eb",
                "select_fg": "#ffffff",
                "input_bg": "#ffffff",
                "input_fg": "#1c1e29",
                "button_bg": "#eef0f5",
                "button_hover": "#e1e4ed",
                "button_active": "#d0d3dc",
                "separator": "#e1e4ed",
                "row_hover": "#f0f2f8",
            }

    def _refresh_filter_values(self):
        if not hasattr(self, 'combo_filter'):
            return
        if not self.available_formats:
            self.combo_filter.configure(values=[self.t('filter_all')])
            self.filter_var.set(self.t('filter_all'))
            return
        filter_values = [self.t('filter_all')] + [
            f"{fmt} ({sum(1 for d in self.display_data if d[5].lower().endswith(fmt))})"
            for fmt in sorted(self.available_formats)
        ]
        self.combo_filter.configure(values=filter_values)
        if self.filter_format:
            for v in filter_values:
                if v.startswith(self.filter_format):
                    self.filter_var.set(v)
                    break
            else:
                self.filter_var.set(self.t('filter_all'))
        else:
            self.filter_var.set(self.t('filter_all'))

    def update_theme_button_text(self):
        icon = '☀' if self.current_theme == 'light' else '☾'
        if hasattr(self, 'btn_theme'):
            self.btn_theme.configure(text=icon)

    # ---------- Styles (Treeview only, CTk handles the rest) ----------
    def setup_styles(self):
        style = ttk.Style()
        style.theme_use('clam')
        self._apply_treeview_theme()

    def _apply_treeview_theme(self):
        style = ttk.Style()
        style.theme_use('clam')
        c = self._get_tree_colors()

        style.configure('.',
                        background=c['bg'],
                        foreground=c['fg'],
                        fieldbackground=c['input_bg'],
                        font=(self.font_family, self.font_size))

        style.configure('TFrame', background=c['bg'], borderwidth=0, relief='flat')
        style.configure('Card.TFrame', background=c['surface'], relief='flat', borderwidth=0)

        style.configure('Treeview',
                        background=c['row'],
                        foreground=c['fg'],
                        fieldbackground=c['row'],
                        rowheight=38,
                        borderwidth=0,
                        relief='flat')
        style.configure('Treeview.Heading',
                        background=c['header_bg'],
                        foreground=c['header_fg'],
                        relief='flat',
                        borderwidth=0,
                        padding=(12, 8),
                        font=(self.font_family, self.font_size, 'bold'))
        style.map('Treeview.Heading',
                  background=[('active', c['button_hover'])],
                  bordercolor=[('!focus', c['header_bg'])])
        style.map('Treeview',
                  background=[('selected', c['select_bg'])],
                  foreground=[('selected', c['select_fg'])],
                  bordercolor=[('!focus', c['row']),
                               ('focus', c['row'])])
        style.layout('Treeview', [('Treeview.treearea', {'sticky': 'nswe', 'border': '0'})])

        # Scrollbar provided by CTkScrollbar

        if hasattr(self, 'tree'):
            c2 = self._get_tree_colors()
            self.tree.tag_configure('row', background=c2['row'])
            self.tree.tag_configure('alt', background=c2['row_alt'])
            self.tree.tag_configure('hover', background=c2['row_hover'])

        self._update_pywinstyles()

    def _refresh_tree_tags(self):
        c = self._get_tree_colors()
        self.tree.tag_configure('row', background=c['row'])
        self.tree.tag_configure('alt', background=c['row_alt'])
        self.tree.tag_configure('hover', background=c['row_hover'])
        for i, item in enumerate(self.tree.get_children()):
            tag = 'alt' if i % 2 == 0 else 'row'
            self.tree.item(item, tags=(tag,))

    # ---------- Font ----------
    _BASE_FONT_SIZE = 14
    _BASE_MIN_WIDTH = 1050
    _BASE_MIN_HEIGHT = 780

    def apply_font_to_all(self, snap=False):
        default_font = (self.font_family, self.font_size)
        self.root.option_add('*Font', default_font)
        style = ttk.Style()
        style.configure('.', font=default_font)
        style.configure('Treeview.Heading', font=(self.font_family, self.font_size, 'bold'))
        ctk.set_widget_scaling(1.0)

        self._refresh_ui_fonts()
        self.update_ui_texts()

        ratio = self.font_size / self._BASE_FONT_SIZE
        min_w = round(self._BASE_MIN_WIDTH * ratio)
        min_h = round(self._BASE_MIN_HEIGHT * ratio)
        self.root.minsize(min_w, min_h)

        if snap:
            self.root.geometry(f"{min_w}x{min_h}")
            self.center_window(self.root)
        else:
            self.root.update_idletasks()
            cur_w = self.root.winfo_width()
            cur_h = self.root.winfo_height()
            if cur_w < min_w or cur_h < min_h:
                self.root.geometry(f"{max(cur_w, min_w)}x{max(cur_h, min_h)}")

        self.save_config()

    def _refresh_ui_fonts(self):
        f = self.font_family
        s = self.font_size

        def _font(offset=0, bold=False):
            return (f, s + offset, 'bold') if bold else (f, s + offset)

        if hasattr(self, 'lbl_app_title'):
            self.lbl_app_title.configure(font=_font(1, bold=True))
            self.lbl_app_subtitle.configure(font=_font(-1))
            self.btn_open.configure(font=_font(0, bold=True))
            self.lbl_folder_label.configure(font=_font(-1))
            self.lbl_folder.configure(font=_font(0))
            self.lbl_stats_heading.configure(font=_font(-1, bold=True))
            self.lbl_stats_total.configure(font=_font(0))
            self.lbl_stats_duration.configure(font=_font(0))
            self.lbl_stats_size.configure(font=_font(0))
            self.lbl_sel_heading.configure(font=_font(-1, bold=True))
            self.lbl_sel_count.configure(font=_font(0))
            self.lbl_sel_duration.configure(font=_font(0))
            self.lbl_sel_size.configure(font=_font(0))
            self.btn_select_all.configure(font=_font(0))
            self.btn_deselect_all.configure(font=_font(0))
            self.btn_export.configure(font=_font(0, bold=True))
            self.btn_batch.configure(font=_font(-1))
            self.btn_theme.configure(font=_font(5))
            self.btn_lang.configure(font=_font(0, bold=True))
        if hasattr(self, 'lbl_sort'):
            self.lbl_sort.configure(font=_font(0))
            self.lbl_filter.configure(font=_font(0))
            self.btn_order.configure(font=_font(0))
            self.combo_sort.configure(font=_font(0))
            self.combo_filter.configure(font=_font(0))
            self.btn_refresh.configure(font=_font(1))
        if hasattr(self, 'lbl_status'):
            self.lbl_status.configure(font=_font(-1))
            self.lbl_hint.configure(font=_font(-1))

    def update_ui_texts(self):
        self.root.title(self.t('title'))
        if not hasattr(self, 'btn_open'):
            return
        if hasattr(self, 'lbl_app_title'):
            self.lbl_app_title.configure(text=self.t('app_title'))
            self.lbl_app_subtitle.configure(text=self.t('app_subtitle'))
        self.btn_open.configure(text=self.t('select_folder'))
        self.btn_export.configure(text=self.t('export_txt'))
        self.btn_batch.configure(text=self.t('batch_cmd'))
        self.lbl_folder_label.configure(text=self.t('open_folder'))
        self.lbl_folder.configure(text=self.t('no_folder'))
        self.lbl_stats_heading.configure(text=self.t('folder_stats'))
        self.lbl_sel_heading.configure(text=self.t('selection_stats'))
        self.lbl_sort.configure(text=self.t('sort_label'))
        self.combo_sort.configure(values=[self.t('sort_name'), self.t('sort_size'), self.t('sort_duration'),
                                          self.t('sort_vbr'), self.t('sort_abr')])
        self.btn_order.configure(text=self.t('asc') if not self.sort_reverse else self.t('desc'))
        self.btn_select_all.configure(text=self.t('select_all'))
        self.btn_deselect_all.configure(text=self.t('deselect_all'))
        self.lbl_status.configure(text=self.t('ready'))
        self.lbl_filter.configure(text=self.t('filter_label') + ':')
        self._refresh_filter_values()
        self.update_total_duration()
        self.update_selected_stats()
        self.tree.heading("check", text=self.t('column_check'))
        self.tree.heading("index", text=self.t('column_index'))
        self.tree.heading("filename", text=self.t('column_filename'))
        self.tree.heading("size", text=self.t('column_size'))
        self.tree.heading("duration", text=self.t('column_duration'))
        self.tree.heading("vbr", text=self.t('column_vbr'))
        self.tree.heading("abr", text=self.t('column_abr'))
        col_map = {'name': self.t('sort_name'), 'size': self.t('sort_size'), 'duration': self.t('sort_duration'),
                   'vbr': self.t('sort_vbr'), 'abr': self.t('sort_abr')}
        self.sort_var.set(col_map.get(self.sort_column, self.t('sort_name')))
        self.update_theme_button_text()
        if hasattr(self, 'btn_lang'):
            self.btn_lang.configure(text='EN' if self.lang == 'zh' else '中')

    def center_window(self, win):
        win.update_idletasks()
        width = win.winfo_width()
        height = win.winfo_height()
        screen_width = win.winfo_screenwidth()
        screen_height = win.winfo_screenheight()
        x = (screen_width - width) // 2
        y = (screen_height - height) // 2
        win.geometry(f"+{x}+{y}")

    def find_ffprobe(self):
        local_ffprobe = Path(__file__).parent / "ffprobe.exe"
        if local_ffprobe.exists():
            return str(local_ffprobe)
        import shutil
        path = shutil.which("ffprobe")
        return path

    # ---------- UI Layout ----------
    def setup_ui(self):
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_rowconfigure(0, weight=1)

        c = self._get_tree_colors()

        master = ctk.CTkFrame(self.root, corner_radius=0, fg_color=c['bg'])
        master.grid(row=0, column=0, sticky='nsew')
        master.grid_columnconfigure(1, weight=1)
        master.grid_rowconfigure(0, weight=1)

        self._sidebar_width = 240
        self.sidebar = ctk.CTkFrame(master, width=self._sidebar_width, corner_radius=0,
                                    fg_color=c['surface'])
        self.sidebar.grid(row=0, column=0, sticky='nsw')
        self.sidebar.grid_propagate(False)
        self._build_sidebar()

        self.separator = ctk.CTkFrame(master, width=1, corner_radius=0, fg_color=c['border'])
        self.separator.grid(row=0, column=0, sticky='nse', padx=(self._sidebar_width, 0))

        self.content_frame = ctk.CTkFrame(master, corner_radius=0, fg_color=c['bg'])
        self.content_frame.grid(row=0, column=1, sticky='nsew')
        self.content_frame.grid_columnconfigure(0, weight=1)
        self.content_frame.grid_rowconfigure(1, weight=1)

        self._build_toolbar(self.content_frame)
        self._build_table(self.content_frame)
        self._build_statusbar(self.content_frame)

        self.root.bind("<Configure>", self._on_sidebar_resize, add='+')

    def _build_sidebar(self):
        c = self._get_tree_colors()

        header = ctk.CTkFrame(self.sidebar, fg_color="transparent", corner_radius=0)
        header.pack(fill=tk.X, padx=16, pady=(16, 8))

        self.lbl_app_title = ctk.CTkLabel(header, text=self.t('app_title'),
                                          font=(self.font_family, self.font_size + 1, 'bold'),
                                          text_color=c['fg'],
                                          anchor="w")
        self.lbl_app_title.pack(fill=tk.X)
        self.lbl_app_subtitle = ctk.CTkLabel(header, text=self.t('app_subtitle'),
                                             font=(self.font_family, self.font_size - 1),
                                             text_color=c['fg2'],
                                             anchor="w")
        self.lbl_app_subtitle.pack(fill=tk.X)

        sep1 = ctk.CTkFrame(self.sidebar, height=1, corner_radius=0, fg_color=c['border'])
        sep1.pack(fill=tk.X, padx=16, pady=(12, 16))

        self.btn_open = ctk.CTkButton(self.sidebar,
                                       text=self.t('select_folder'),
                                       font=(self.font_family, self.font_size, 'bold'),
                                       fg_color=c['accent'],
                                       hover_color=c['accent_hover'],
                                       text_color=c['accent_text'],
                                       corner_radius=6,
                                       height=38,
                                       command=self.select_folder)
        self.btn_open.pack(fill=tk.X, padx=16, pady=(0, 12))

        self.lbl_folder_label = ctk.CTkLabel(self.sidebar,
                                             text=self.t('open_folder'),
                                             font=(self.font_family, self.font_size - 1),
                                             text_color=c['fg2'],
                                             anchor="w")
        self.lbl_folder_label.pack(fill=tk.X, padx=16, pady=(0, 2))
        self.lbl_folder = ctk.CTkLabel(self.sidebar,
                                       text=self.t('no_folder'),
                                       font=(self.font_family, self.font_size),
                                       text_color=c['fg'],
                                       anchor="w", justify="left",
                                       wraplength=208)
        self.lbl_folder.pack(fill=tk.X, padx=16, pady=(0, 4))

        sep2 = ctk.CTkFrame(self.sidebar, height=1, corner_radius=0, fg_color=c['border'])
        sep2.pack(fill=tk.X, padx=16, pady=(12, 12))

        # Folder Stats card
        self.stats_card = ctk.CTkFrame(self.sidebar, fg_color=c['card'], corner_radius=8)
        self.stats_card.pack(fill=tk.X, padx=12, pady=(0, 8))

        self.lbl_stats_heading = ctk.CTkLabel(self.stats_card,
                                              text=self.t('folder_stats'),
                                              font=(self.font_family, self.font_size - 1, 'bold'),
                                              text_color=c['fg2'],
                                              anchor="w")
        self.lbl_stats_heading.pack(fill=tk.X, padx=12, pady=(10, 6))

        self.lbl_stats_total = ctk.CTkLabel(self.stats_card,
                                            text=self.t('total_files', 0),
                                            font=(self.font_family, self.font_size),
                                            text_color=c['fg'],
                                            anchor="w")
        self.lbl_stats_total.pack(fill=tk.X, padx=12, pady=(0, 3))

        self.lbl_stats_duration = ctk.CTkLabel(self.stats_card,
                                               text=self.t('total_duration', '00:00:00'),
                                               font=(self.font_family, self.font_size),
                                               text_color=c['fg'],
                                               anchor="w")
        self.lbl_stats_duration.pack(fill=tk.X, padx=12, pady=(0, 3))

        self.lbl_stats_size = ctk.CTkLabel(self.stats_card,
                                           text=f"{self.t('size_label')}: 0 B",
                                           font=(self.font_family, self.font_size),
                                           text_color=c['fg'],
                                           anchor="w")
        self.lbl_stats_size.pack(fill=tk.X, padx=12, pady=(0, 10))

        # Selection Stats card
        self.sel_card = ctk.CTkFrame(self.sidebar, fg_color=c['card'], corner_radius=8)
        self.sel_card.pack(fill=tk.X, padx=12, pady=(0, 12))

        self.lbl_sel_heading = ctk.CTkLabel(self.sel_card,
                                            text=self.t('selection_stats'),
                                            font=(self.font_family, self.font_size - 1, 'bold'),
                                            text_color=c['fg2'],
                                            anchor="w")
        self.lbl_sel_heading.pack(fill=tk.X, padx=12, pady=(10, 6))

        self.lbl_sel_count = ctk.CTkLabel(self.sel_card,
                                          text=f"0 {self.t('videos')}",
                                          font=(self.font_family, self.font_size),
                                          text_color=c['fg'],
                                          anchor="w")
        self.lbl_sel_count.pack(fill=tk.X, padx=12, pady=(0, 3))

        self.lbl_sel_duration = ctk.CTkLabel(self.sel_card,
                                             text=f"{self.t('duration_label')}: 00:00:00",
                                             font=(self.font_family, self.font_size),
                                             text_color=c['fg'],
                                             anchor="w")
        self.lbl_sel_duration.pack(fill=tk.X, padx=12, pady=(0, 3))

        self.lbl_sel_size = ctk.CTkLabel(self.sel_card,
                                         text=f"{self.t('size_label')}: 0 B",
                                         font=(self.font_family, self.font_size),
                                         text_color=c['fg'],
                                         anchor="w")
        self.lbl_sel_size.pack(fill=tk.X, padx=12, pady=(0, 10))

        # Quick selection buttons
        self.btn_select_all = ctk.CTkButton(self.sidebar,
                                            text=self.t('select_all'),
                                            font=(self.font_family, self.font_size),
                                            fg_color=c['button_bg'],
                                            hover_color=c['button_hover'],
                                            text_color=c['fg'],
                                            corner_radius=6,
                                            height=34,
                                            command=self.select_all)
        self.btn_select_all.pack(fill=tk.X, padx=16, pady=(0, 6))

        self.btn_deselect_all = ctk.CTkButton(self.sidebar,
                                              text=self.t('deselect_all'),
                                              font=(self.font_family, self.font_size),
                                              fg_color=c['button_bg'],
                                              hover_color=c['button_hover'],
                                              text_color=c['fg'],
                                              corner_radius=6,
                                              height=34,
                                              command=self.deselect_all)
        self.btn_deselect_all.pack(fill=tk.X, padx=16, pady=(0, 6))

        self.btn_export = ctk.CTkButton(self.sidebar,
                                        text=self.t('export_txt'),
                                        font=(self.font_family, self.font_size, 'bold'),
                                        fg_color=c['button_bg'],
                                        hover_color=c['button_hover'],
                                        text_color=c['fg'],
                                        corner_radius=6,
                                        height=36,
                                        command=self.export_txt)
        self.btn_export.pack(fill=tk.X, padx=16, pady=(4, 6))

        self.btn_batch = ctk.CTkButton(self.sidebar,
                                        text=self.t('batch_cmd'),
                                        font=(self.font_family, self.font_size - 1),
                                        fg_color=c['button_bg'],
                                        hover_color=c['button_hover'],
                                        text_color=c['fg'],
                                        corner_radius=6,
                                        height=34,
                                        command=self.open_batch_command)
        self.btn_batch.pack(fill=tk.X, padx=16, pady=(0, 12))

        # Bottom theme/language row (directly below batch button)
        bottom_row = ctk.CTkFrame(self.sidebar, fg_color="transparent", corner_radius=0)
        bottom_row.pack(fill=tk.X, padx=16, pady=(0, 8))

        self.btn_theme = ctk.CTkButton(bottom_row,
                                       text='☾',
                                       font=(self.font_family, self.font_size + 5),
                                       fg_color=c['button_bg'],
                                       hover_color=c['button_hover'],
                                       text_color=c['fg'],
                                       corner_radius=6,
                                       width=44,
                                       height=34,
                                       command=self.cycle_theme)
        self.btn_theme.pack(side=tk.LEFT, padx=(0, 8))

        self.btn_lang = ctk.CTkButton(bottom_row,
                                      text='EN' if self.lang == 'zh' else '中',
                                      font=(self.font_family, self.font_size, 'bold'),
                                      fg_color=c['button_bg'],
                                      hover_color=c['button_hover'],
                                      text_color=c['fg'],
                                      corner_radius=6,
                                      width=44,
                                      height=34,
                                      command=self.toggle_language)
        self.btn_lang.pack(side=tk.LEFT)

    def _build_toolbar(self, parent):
        c = self._get_tree_colors()
        self.toolbar_frame = ctk.CTkFrame(parent, fg_color="transparent", corner_radius=0)
        self.toolbar_frame.grid(row=0, column=0, sticky='w', padx=(20, 20), pady=(16, 8))
        toolbar = self.toolbar_frame

        self.lbl_sort = ctk.CTkLabel(toolbar,
                                     text=self.t('sort_label'),
                                     font=(self.font_family, self.font_size),
                                     text_color=c['fg2'])
        self.lbl_sort.grid(row=0, column=0, padx=(0, 8))

        self.sort_var = tk.StringVar(value=self.t('sort_name'))
        self.combo_sort = ToggleComboBox(toolbar,
                                          variable=self.sort_var,
                                          values=[self.t('sort_name'), self.t('sort_size'), self.t('sort_duration')],
                                          state="readonly", width=140,
                                          font=(self.font_family, self.font_size),
                                          corner_radius=6,
                                          command=self.on_sort_change)
        self.combo_sort.grid(row=0, column=1, padx=(0, 10))

        self.btn_order = ctk.CTkButton(toolbar,
                                       text=self.t('asc'),
                                       font=(self.font_family, self.font_size),
                                       fg_color=c['button_bg'],
                                       hover_color=c['button_hover'],
                                       text_color=c['fg'],
                                       corner_radius=6,
                                       width=70,
                                       height=32,
                                       command=self.toggle_sort_order)
        self.btn_order.grid(row=0, column=2, padx=(0, 14))

        self.lbl_filter = ctk.CTkLabel(toolbar,
                                       text=self.t('filter_label') + ':',
                                       font=(self.font_family, self.font_size),
                                       text_color=c['fg2'])
        self.lbl_filter.grid(row=0, column=3, padx=(0, 6))

        self.filter_var = tk.StringVar(value=self.t('filter_all'))
        self.combo_filter = ToggleComboBox(toolbar,
                                            variable=self.filter_var,
                                            values=[self.t('filter_all')],
                                            state="readonly", width=120,
                                            font=(self.font_family, self.font_size),
                                            corner_radius=6,
                                            command=self.on_filter_change)
        self.combo_filter.grid(row=0, column=4, padx=(0, 14))

        self.btn_refresh = ctk.CTkButton(toolbar,
                                         text="↻",
                                         font=(self.font_family, self.font_size + 1),
                                         fg_color=c['button_bg'],
                                         hover_color=c['button_hover'],
                                         text_color=c['fg'],
                                         corner_radius=6,
                                         width=40,
                                         height=32,
                                         command=self.refresh_current_folder)
        self.btn_refresh.grid(row=0, column=5, padx=(14, 6))

        # Hidden progress bar for scan overlay (top-right of content area)
        self.progress_overlay = ctk.CTkProgressBar(parent, width=200, height=8, corner_radius=4)
        self.progress_overlay.set(0)

    def _build_table(self, parent):
        c = self._get_tree_colors()
        table_frame = ctk.CTkFrame(parent, fg_color="transparent", corner_radius=0)
        table_frame.grid(row=1, column=0, sticky='nsew', padx=20, pady=(0, 8))
        table_frame.grid_rowconfigure(0, weight=1)
        table_frame.grid_columnconfigure(0, weight=1)

        columns = ("check", "index", "filename", "size", "duration", "vbr", "abr")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode='extended')

        self.tree.heading("check", text=self.t('column_check'),
                          command=lambda: self.toggle_sort_order())
        self.tree.heading("index", text=self.t('column_index'))
        self.tree.heading("filename", text=self.t('column_filename'),
                          command=lambda: self.set_sort_column('name'))
        self.tree.heading("size", text=self.t('column_size'),
                          command=lambda: self.set_sort_column('size'))
        self.tree.heading("duration", text=self.t('column_duration'),
                          command=lambda: self.set_sort_column('duration'))
        self.tree.heading("vbr", text=self.t('column_vbr'),
                          command=lambda: self.set_sort_column('vbr'))
        self.tree.heading("abr", text=self.t('column_abr'),
                          command=lambda: self.set_sort_column('abr'))

        self.tree.column("check", width=42, anchor='center', stretch=False)
        self.tree.column("index", width=55, anchor='center', stretch=False)
        self.tree.column("filename", width=180, minwidth=80, stretch=True)
        self.tree.column("size", width=100, minwidth=70, anchor='e', stretch=False)
        self.tree.column("duration", width=100, minwidth=70, anchor='center', stretch=False)
        self.tree.column("vbr", width=110, minwidth=70, anchor='center', stretch=False)
        self.tree.column("abr", width=110, minwidth=70, anchor='center', stretch=False)

        self.tree.bind('<Button-1>', self.on_tree_click)
        self.tree.bind('<Double-1>', self.on_double_click)
        self.tree.bind('<B1-Motion>', self.on_drag_selection)
        self.tree.bind('<ButtonRelease-1>', self.on_drag_release)
        self.tree.bind('<Button-3>', self.show_context_menu)
        self.tree.bind('<Motion>', self.on_tree_motion)
        self.tree.bind('<Leave>', self.on_tree_leave)
        self._last_hover_item = None

        scrollbar_y = ctk.CTkScrollbar(table_frame, orientation="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar_y.set)

        self.tree.grid(row=0, column=0, sticky='nsew')
        scrollbar_y.grid(row=0, column=1, sticky='ns', padx=(2, 0))

    def _build_statusbar(self, parent):
        c = self._get_tree_colors()
        self.statusbar_frame = ctk.CTkFrame(parent, fg_color="transparent", corner_radius=0)
        self.statusbar_frame.grid(row=2, column=0, sticky='ew', padx=20, pady=(0, 12))
        self.statusbar_frame.grid_columnconfigure(1, weight=1)
        status_frame = self.statusbar_frame

        self.lbl_status = ctk.CTkLabel(status_frame,
                                       text=self.t('ready'),
                                       font=(self.font_family, self.font_size - 1),
                                       text_color=c['fg2'],
                                       anchor="w")
        self.lbl_status.grid(row=0, column=0, sticky='w')

        self.lbl_hint = ctk.CTkLabel(status_frame,
                                     text="1493442405@qq.com",
                                     font=(self.font_family, self.font_size - 1),
                                     text_color=c['fg2'],
                                     anchor="e")
        self.lbl_hint.grid(row=0, column=2, sticky='e')

    def _on_sidebar_resize(self, event):
        if not hasattr(self, '_last_root_width'):
            self._last_root_width = self.root.winfo_width()
            return
        cur_w = self.root.winfo_width()
        if cur_w == self._last_root_width:
            return
        self._last_root_width = cur_w
        new_w = max(220, min(380, round(cur_w * 0.22)))
        if new_w == self._sidebar_width:
            return
        self._sidebar_width = new_w
        self.sidebar.configure(width=new_w)
        self.separator.grid_configure(padx=(new_w, 0))
        if hasattr(self, 'lbl_folder'):
            self.lbl_folder.configure(wraplength=new_w - 32)

    # ---------- Theme cycling ----------
    def cycle_theme(self):
        def _fade_out(step=5):
            if step > 0:
                self.root.attributes('-alpha', step / 5)
                self.root.after(20, lambda s=step: _fade_out(s - 1))
            else:
                self.root.withdraw()
                self.theme_mode = 'light' if self.theme_mode != 'light' else 'dark'
                self.update_theme_by_mode()
                self.save_config()
                self.root.update_idletasks()
                self.root.update()
                self.root.attributes('-alpha', 0.0)
                self.root.deiconify()
                _fade_in(1)

        def _fade_in(step=1):
            if step <= 5:
                self.root.attributes('-alpha', step / 5)
                self.root.after(20, lambda s=step: _fade_in(s + 1))
            else:
                self.root.attributes('-alpha', 1.0)

        _fade_out()

    def toggle_sort_order(self):
        self.sort_reverse = not self.sort_reverse
        self.btn_order.configure(text=self.t('asc') if not self.sort_reverse else self.t('desc'))
        self.apply_sort_and_display()

    def toggle_language(self):
        geo = self.root.geometry()

        def _fade_out(step=5):
            if step > 0:
                self.root.attributes('-alpha', step / 5)
                self.root.after(20, lambda s=step: _fade_out(s - 1))
            else:
                self.root.withdraw()
                self.lang = 'en' if self.lang == 'zh' else 'zh'
                self.update_ui_texts()
                self._refresh_ui_fonts()
                self.root.geometry(geo)
                self.save_config()
                self.root.update_idletasks()
                self.root.update()
                self.root.attributes('-alpha', 0.0)
                self.root.deiconify()
                _fade_in(1)

        def _fade_in(step=1):
            if step <= 5:
                self.root.attributes('-alpha', step / 5)
                self.root.after(20, lambda s=step: _fade_in(s + 1))
            else:
                self.root.attributes('-alpha', 1.0)

        _fade_out()

    # ---------- Tree interaction ----------
    def on_tree_click(self, event):
        region = self.tree.identify_region(event.x, event.y)
        if region != "cell":
            return
        column = self.tree.identify_column(event.x)
        item = self.tree.identify_row(event.y)
        if not item:
            return
        if column == "#1":
            self.toggle_check(item)
            return "break"

    def on_double_click(self, event):
        item = self.tree.identify_row(event.y)
        if item:
            self.toggle_check(item)

    def toggle_check(self, item_id):
        data = self.item_data_map.get(item_id)
        if not data:
            return
        current = data['checked'].get()
        data['checked'].set(not current)
        self.tree.set(item_id, "check", "✓" if not current else "")
        self.update_selected_stats()

    def on_drag_selection(self, event):
        item = self.tree.identify_row(event.y)
        if not item:
            return
        if self.drag_start_item is None:
            self.drag_start_item = item
            data = self.item_data_map.get(item)
            self.drag_selection_state = not data['checked'].get() if data else True
        else:
            data = self.item_data_map.get(item)
            if data and data['checked'].get() != self.drag_selection_state:
                data['checked'].set(self.drag_selection_state)
                self.tree.set(item, "check", "✓" if self.drag_selection_state else "")
        self.tree.selection_add(item)
        self.update_selected_stats()

    def on_drag_release(self, event):
        was_dragging = self.drag_start_item is not None
        self.drag_start_item = None
        self.drag_selection_state = None
        if was_dragging:
            self.tree.selection_remove(*self.tree.selection())

    def on_tree_motion(self, event):
        item = self.tree.identify_row(event.y)
        if item == self._last_hover_item:
            return
        if self._last_hover_item and self.tree.exists(self._last_hover_item):
            tags = list(self.tree.item(self._last_hover_item, 'tags'))
            if 'hover' in tags:
                tags.remove('hover')
            self.tree.item(self._last_hover_item, tags=tags)
        if item:
            tags = list(self.tree.item(item, 'tags'))
            if 'hover' not in tags:
                tags.append('hover')
            self.tree.item(item, tags=tags)
        self._last_hover_item = item

    def on_tree_leave(self, event):
        if self._last_hover_item and self.tree.exists(self._last_hover_item):
            tags = list(self.tree.item(self._last_hover_item, 'tags'))
            if 'hover' in tags:
                tags.remove('hover')
            self.tree.item(self._last_hover_item, tags=tags)
        self._last_hover_item = None

    def get_checked_items(self):
        result = []
        for item_id in self.tree.get_children():
            data = self.item_data_map.get(item_id)
            if data and data['checked'].get():
                result.append(item_id)
        return result

    def show_context_menu(self, event):
        item = self.tree.identify_row(event.y)
        if not item:
            return
        selected = self.tree.selection()
        if item not in selected:
            self.tree.selection_set(item)
            selected = [item]

        checked = self.get_checked_items()

        c = self._get_tree_colors()
        menu = tk.Menu(self.root, tearoff=0,
                       bg=c['card'], fg=c['fg'],
                       relief='flat', borderwidth=1,
                       activebackground=c['accent'],
                       activeforeground=c['accent_text'])
        menu.add_command(label=self.t('open_file'), command=lambda: self.open_selected_files(selected))
        menu.add_command(label=self.t('open_location'), command=lambda: self.open_file_locations(selected))
        menu.add_command(label=self.t('rename'), command=lambda: self.rename_files(selected))
        menu.add_separator()
        targets = checked if checked else selected
        menu.add_command(label=self.t('delete'), command=lambda: self.delete_files(targets))
        menu.tk_popup(event.x_root, event.y_root)

    def open_selected_files(self, items):
        for item in items:
            data = self.item_data_map.get(item)
            if data:
                try:
                    os.startfile(data['path'])
                except Exception as e:
                    messagebox.showerror(self.t('error'), f"Cannot open file: {e}")

    def open_file_locations(self, items):
        for item in items:
            data = self.item_data_map.get(item)
            if data:
                try:
                    subprocess.Popen(['explorer', '/select,', data['path']])
                except Exception as e:
                    messagebox.showerror(self.t('error'), f"Cannot open location: {e}")

    # ---------- File operations ----------
    def rename_files(self, items):
        if not items:
            return
        if len(items) > 1:
            messagebox.showinfo(self.t('info'), "Only one file can be renamed at a time.")
            return
        item = items[0]
        data = self.item_data_map.get(item)
        if not data:
            return
        old_path = data['path']
        old_dir = os.path.dirname(old_path)
        old_name = os.path.basename(old_path)

        new_name = simpledialog.askstring(self.t('rename'), self.t('rename_prompt'),
                                          initialvalue=old_name, parent=self.root)
        if not new_name or new_name == old_name:
            return
        new_path = os.path.join(old_dir, new_name)
        if os.path.exists(new_path):
            messagebox.showerror(self.t('error'), self.t('rename_exists'))
            return
        try:
            os.rename(old_path, new_path)
            data['path'] = new_path
            self.tree.set(item, "filename", new_name)
            for lst in (self.display_data, self.video_list):
                for i, entry in enumerate(lst):
                    if entry[0] == old_name or (len(entry) > 5 and entry[5] == old_path):
                        entry[0] = new_name
                        if len(entry) > 5:
                            entry[5] = new_path
                        break
            self.update_selected_stats()
        except Exception as e:
            messagebox.showerror(self.t('error'), self.t('rename_error', str(e)))

    def delete_files(self, items):
        if not items:
            return
        count = len(items)
        if not messagebox.askyesno(self.t('delete'), self.t('delete_confirm', count)):
            return
        errors = []
        deleted_paths = []
        for item in items:
            data = self.item_data_map.get(item)
            if not data:
                continue
            path = data['path']
            try:
                send2trash(path)
                deleted_paths.append(path)
                self.tree.delete(item)
            except Exception as e:
                errors.append(f"{path}: {e}")
        self.display_data = [d for d in self.display_data if d[5] not in deleted_paths]
        self.video_list = [v for v in self.video_list if v[0] not in deleted_paths]
        for item in items:
            if item in self.item_data_map:
                del self.item_data_map[item]
        self.refresh_display_after_delete()
        self.update_selected_stats()
        self.update_total_duration()
        if errors:
            messagebox.showerror(self.t('error'), self.t('delete_error', '\n'.join(errors)))
        else:
            self.lbl_status.configure(text=self.t('delete_success', count))

    def refresh_display_after_delete(self):
        self.apply_sort_and_display()

    def select_all(self):
        for item_id in self.tree.get_children():
            data = self.item_data_map.get(item_id)
            if data:
                data['checked'].set(True)
                self.tree.set(item_id, "check", "✓")
        self.update_selected_stats()

    def deselect_all(self):
        for item_id in self.tree.get_children():
            data = self.item_data_map.get(item_id)
            if data:
                data['checked'].set(False)
                self.tree.set(item_id, "check", "")
        self.update_selected_stats()

    def update_selected_stats(self):
        total_duration_sec = 0
        total_size_bytes = 0
        count = 0
        for item_id in self.tree.get_children():
            data = self.item_data_map.get(item_id)
            if data and data['checked'].get():
                total_duration_sec += data['duration_sec']
                total_size_bytes += data['size_bytes']
                count += 1
        duration_str = self.format_duration(total_duration_sec)
        size_str = self.format_size(total_size_bytes)

        if hasattr(self, 'lbl_sel_count'):
            self.lbl_sel_count.configure(text=f"{count} {self.t('videos')}")
            self.lbl_sel_duration.configure(text=f"{self.t('duration_label')}: {duration_str}")
            self.lbl_sel_size.configure(text=f"{self.t('size_label')}: {size_str}")

    def select_folder(self):
        folder = filedialog.askdirectory(title=self.t('select_folder'))
        if folder:
            self.current_folder = folder
            self.lbl_folder.configure(text=folder)
            self.scan_folder(folder)

    def refresh_current_folder(self):
        if self.current_folder and os.path.isdir(self.current_folder):
            self.scan_folder(self.current_folder)

    def get_scan_threads(self, folder):
        drive_letter = os.path.splitdrive(folder)[0][0]
        try:
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            ps_cmd = f'powershell -NoProfile -Command "$d=(Get-Partition -DriveLetter {drive_letter}).DiskNumber;(Get-PhysicalDisk -DeviceNumber $d).MediaType"'
            result = subprocess.run(ps_cmd, capture_output=True, text=True, shell=True,
                                   timeout=8, startupinfo=si)
            if 'HDD' in result.stdout.upper():
                return 1
        except Exception:
            pass
        return 6

    def scan_folder(self, folder):
        self.progress_overlay.place(relx=1.0, rely=0.0, anchor='ne', x=-24, y=32)
        self.progress_overlay.start()
        self.lbl_status.configure(text=self.t('scanning'))
        self.tree.delete(*self.tree.get_children())
        self.video_list.clear()
        self.display_data.clear()
        self.item_data_map.clear()
        self.check_vars.clear()
        self.update_selected_stats()

        def task():
            try:
                video_files = []
                extensions_found = set()
                for root, dirs, files in os.walk(folder):
                    for f in files:
                        ext = os.path.splitext(f)[1].lower()
                        if ext in MEDIA_EXT:
                            video_files.append(os.path.join(root, f))
                            extensions_found.add(ext)

                total = len(video_files)
                if total == 0:
                    self.root.after(0, self.scan_finished, self.t('no_video'))
                    return

                num_threads = self.get_scan_threads(folder)

                def process_one(fp):
                    try:
                        size_bytes = os.path.getsize(fp)
                        duration_sec, vbr_err, abr_err = self.get_video_info(fp)
                        filename = os.path.basename(fp)
                        size_str = self.format_size(size_bytes)
                        duration_str = self.format_duration(duration_sec) if duration_sec > 0 else self.t('unknown')
                        vbr_str = self.format_bitrate(vbr_err)
                        abr_str = self.format_bitrate(abr_err)
                        sort_duration = duration_sec if duration_sec > 0 else -1
                        return [filename, size_str, duration_str, sort_duration, size_bytes, fp, vbr_str, abr_str, vbr_err, abr_err]
                    except Exception as e:
                        print(f"Failed processing file {fp}: {e}")
                        return None

                processed = 0
                with ThreadPoolExecutor(max_workers=num_threads) as executor:
                    futures = {executor.submit(process_one, fp): fp for fp in video_files}
                    for future in as_completed(futures):
                        result = future.result()
                        if result is not None:
                            self.video_list.append([result[5], result[4], result[3], result[8], result[9]])
                            self.display_data.append(result)
                        processed += 1
                        if processed % 10 == 0 or processed == total:
                            self.root.after(0, lambda p=processed, t=total: self.lbl_status.configure(
                                text=f"{self.t('scanning')} {p}/{t}"))

                self.root.after(0, lambda: self.scan_finished(None, extensions_found))
            except Exception as e:
                error_msg = f"Scan error: {str(e)}\n{traceback.format_exc()}"
                self.root.after(0, self.scan_finished, error_msg)

        threading.Thread(target=task, daemon=True).start()

    def scan_finished(self, error_msg, extensions_found=None):
        self.progress_overlay.stop()
        self.progress_overlay.place_forget()
        if error_msg:
            if error_msg == self.t('no_video'):
                self.lbl_status.configure(text=error_msg)
                messagebox.showinfo(self.t('info'), error_msg)
            else:
                self.lbl_status.configure(text="Scan error")
                messagebox.showerror(self.t('error'), error_msg)
        else:
            if extensions_found:
                self.available_formats = sorted(extensions_found)
                filter_values = [self.t('filter_all')] + [
                    f"{fmt} ({sum(1 for d in self.display_data if d[5].lower().endswith(fmt))})"
                    for fmt in self.available_formats
                ]
                self.combo_filter.configure(values=filter_values)
                self.filter_var.set(self.t('filter_all'))
                self.filter_format = None
            self.lbl_status.configure(text=self.t('found', len(self.display_data)))
            self.apply_sort_and_display()
            self.update_total_duration()

    def get_video_info(self, filepath):
        if not self.ffprobe_path:
            return 0, 0, 0
        try:
            cmd = [
                self.ffprobe_path,
                '-v', 'error',
                '-show_entries', 'format=duration,bit_rate:stream=codec_type,bit_rate',
                '-of', 'json',
                filepath
            ]
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', startupinfo=startupinfo)
            if result.returncode == 0:
                data = json.loads(result.stdout)
                fmt = data.get('format', {})
                duration = float(fmt.get('duration', 0))
                format_br = 0
                try:
                    format_br = int(fmt.get('bit_rate', 0) or 0)
                except Exception:
                    pass
                vbr = 0
                abr = 0
                for stream in data.get('streams', []):
                    try:
                        br = int(stream.get('bit_rate', 0) or 0)
                    except Exception:
                        br = 0
                    if stream.get('codec_type') == 'video' and br > 0 and vbr == 0:
                        vbr = br
                    elif stream.get('codec_type') == 'audio' and br > 0 and abr == 0:
                        abr = br
                if vbr == 0 and format_br > 0:
                    vbr = max(0, format_br - abr) if abr > 0 else format_br
                return duration, vbr, abr
        except Exception:
            pass
        return 0, 0, 0

    def format_bitrate(self, bps):
        if bps <= 0:
            return self.t('unknown')
        if bps >= 1000000:
            return f"{bps / 1000000:.2f} Mbps"
        elif bps >= 1000:
            return f"{bps / 1000:.0f} Kbps"
        else:
            return f"{bps} bps"

    def format_size(self, bytes_val):
        if bytes_val < 1024:
            return f"{bytes_val} B"
        elif bytes_val < 1024 ** 2:
            return f"{bytes_val/1024:.2f} KB"
        elif bytes_val < 1024 ** 3:
            return f"{bytes_val/(1024**2):.2f} MB"
        else:
            return f"{bytes_val/(1024**3):.2f} GB"

    def format_duration(self, seconds):
        if seconds is None or seconds < 0:
            return self.t('unknown')
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"

    def set_sort_column(self, col):
        if self.sort_column == col:
            self.sort_reverse = not self.sort_reverse
        else:
            self.sort_column = col
            self.sort_reverse = False
        col_name_map = {'name': self.t('sort_name'), 'size': self.t('sort_size'), 'duration': self.t('sort_duration'),
                       'vbr': self.t('sort_vbr'), 'abr': self.t('sort_abr')}
        self.sort_var.set(col_name_map.get(col, self.t('sort_name')))
        self.btn_order.configure(text=self.t('asc') if not self.sort_reverse else self.t('desc'))
        self.apply_sort_and_display()

    def on_sort_change(self, event=None):
        col_map = {self.t('sort_name'): 'name', self.t('sort_size'): 'size',
                   self.t('sort_duration'): 'duration',
                   self.t('sort_vbr'): 'vbr', self.t('sort_abr'): 'abr'}
        self.sort_column = col_map.get(self.sort_var.get(), 'name')
        self.apply_sort_and_display()

    def on_filter_change(self, event=None):
        selected = self.filter_var.get()
        if selected == self.t('filter_all'):
            self.filter_format = None
        else:
            for fmt in self.available_formats:
                if selected.startswith(fmt):
                    self.filter_format = fmt
                    break
            else:
                self.filter_format = None
        self.apply_sort_and_display()
        self.update_total_duration()

    def apply_sort_and_display(self):
        if not self.display_data:
            return

        if self.filter_format:
            filtered_data = [d for d in self.display_data
                             if d[5].lower().endswith(self.filter_format)]
        else:
            filtered_data = self.display_data[:]

        if not filtered_data:
            self.tree.delete(*self.tree.get_children())
            self.item_data_map.clear()
            self.check_vars.clear()
            self.sorted_display = []
            self.update_selected_stats()
            return

        key_map = {'name': 0, 'size': 4, 'duration': 3, 'vbr': 8, 'abr': 9}
        key_index = key_map.get(self.sort_column, 0)

        if self.sort_column == 'name':
            sorted_data = sorted(filtered_data, key=lambda x: str(x[key_index]).lower(), reverse=self.sort_reverse)
        else:
            sorted_data = sorted(filtered_data, key=lambda x: x[key_index] if x[key_index] > 0 else -1, reverse=self.sort_reverse)

        self.tree.delete(*self.tree.get_children())
        self.item_data_map.clear()
        self.check_vars.clear()

        c = self._get_tree_colors()
        self.tree.tag_configure('row', background=c['row'])
        self.tree.tag_configure('alt', background=c['row_alt'])
        self.tree.tag_configure('hover', background=c['row_hover'])

        for idx, item in enumerate(sorted_data, start=1):
            filename, size_str, duration_str, sort_dur, size_bytes, filepath, vbr_str, abr_str, vbr_val, abr_val = item
            checked_var = tk.BooleanVar(value=False)
            self.check_vars.append(checked_var)
            tag = 'alt' if idx % 2 == 0 else 'row'
            item_id = self.tree.insert("", tk.END,
                                       values=("", idx, filename, size_str, duration_str, vbr_str, abr_str),
                                       tags=(tag,))
            self.item_data_map[item_id] = {
                'duration_sec': sort_dur if sort_dur > 0 else 0,
                'size_bytes': size_bytes,
                'checked': checked_var,
                'path': filepath
            }

        self.sorted_display = sorted_data
        self.update_selected_stats()

    def update_total_duration(self):
        total_sec = 0
        total_size = 0
        for item in self.display_data:
            dur = item[3]
            if dur > 0:
                total_sec += dur
            total_size += item[4]
        total_str = self.format_duration(total_sec)
        size_str = self.format_size(total_size)

        if hasattr(self, 'lbl_stats_total'):
            self.lbl_stats_total.configure(text=self.t('total_files', len(self.display_data)))
            self.lbl_stats_duration.configure(text=self.t('total_duration', total_str))
            self.lbl_stats_size.configure(text=f"{self.t('size_label')}: {size_str}")

        self.total_duration_str = total_str
        self.total_seconds = total_sec

    # ---------- Export ----------
    def export_txt(self):
        if not hasattr(self, 'sorted_display') or not self.sorted_display:
            messagebox.showwarning(self.t('warning'), self.t('no_data'))
            return

        checked_items = []
        all_items = []
        for item_id in self.tree.get_children():
            values = self.tree.item(item_id, 'values')
            data = self.item_data_map.get(item_id)
            entry = (values[1], values[2], values[3], values[4], values[5], values[6], data['path'] if data else '')
            all_items.append(entry)
            if data and data['checked'].get():
                checked_items.append(entry)

        if checked_items:
            msg = self.t('export_confirm_checked', len(checked_items))
            export_items = checked_items
            is_checked = True
        else:
            msg = self.t('export_confirm_all', len(all_items))
            export_items = all_items
            is_checked = False

        if not messagebox.askyesno(self.t('export_txt'), msg):
            return

        if not export_items:
            return

        file_path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            title=self.t('export_txt')
        )
        if not file_path:
            return

        try:
            tag = "Selected" if is_checked else "All"
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(f"{self.t('export_heading')}  [{tag}]\n")
                f.write("=" * 94 + "\n")
                f.write(f"{'#':<5}{self.t('column_filename'):<40}{self.t('column_size'):<10}{self.t('column_duration'):<10}{self.t('column_vbr'):<14}{self.t('column_abr'):<14}\n")
                f.write("-" * 94 + "\n")
                for seq, name, size, duration, vbr, abr, _ in export_items:
                    f.write(f"{seq:<5}{name:<40}{size:<10}{duration:<10}{vbr:<14}{abr:<14}\n")
                f.write("=" * 94 + "\n")
                f.write(self.t('total_files', len(export_items)) + "\n")
                total_dur = 0
                total_sz = 0
                for seq, name, size_str, dur_str, vbr, abr, _ in export_items:
                    if dur_str != self.t('unknown'):
                        try:
                            h, m, s = map(int, dur_str.split(':'))
                            total_dur += h * 3600 + m * 60 + s
                        except:
                            pass
                    total_sz += self.parse_size_to_bytes(size_str)
                f.write(self.t('exported_total_duration', self.format_duration(total_dur)) + "\n")
                f.write(self.t('exported_total_size', self.format_size(total_sz)) + "\n")
            messagebox.showinfo(self.t('info'), self.t('export_success', file_path))
        except Exception as e:
            messagebox.showerror(self.t('error'), self.t('export_failed') + "\n" + str(e))

    def parse_size_to_bytes(self, size_str):
        match = re.match(r'([\d.]+)\s*([KMGT]?B)', size_str.strip())
        if not match:
            return 0
        num = float(match.group(1))
        unit = match.group(2)
        multipliers = {'B': 1, 'KB': 1024, 'MB': 1024 ** 2, 'GB': 1024 ** 3, 'TB': 1024 ** 4}
        return int(num * multipliers.get(unit, 1))

    def open_batch_command(self):
        checked_paths = []
        file_durations = {}
        for item_id in self.tree.get_children():
            data = self.item_data_map.get(item_id)
            if data and data['checked'].get():
                checked_paths.append(data['path'])
                file_durations[data['path']] = data['duration_sec']
        if not checked_paths:
            messagebox.showwarning(self.t('warning'), self.t('batch_no_files'))
            return
        BatchCommandDialog(self, checked_paths, file_durations)


class BatchCommandDialog:
    PRESETS = [
        {
            'key': 'preset_x265_crf23',
            'cmd': 'ffmpeg -threads 0 -i "{input}" -c:v libx265 -crf 23 -preset medium -c:a aac -b:a 128k -movflags +faststart "{output}"',
            'suffix': '_x265_crf23',
        },
        {
            'key': 'preset_x265_crf26',
            'cmd': 'ffmpeg -threads 0 -i "{input}" -c:v libx265 -crf 26 -preset medium -c:a aac -b:a 96k -movflags +faststart "{output}"',
            'suffix': '_x265_crf26',
        },
        {
            'key': 'preset_nvenc_hevc_cq23',
            'cmd': 'ffmpeg -hwaccel cuda -threads 0 -i "{input}" -c:v hevc_nvenc -preset p7 -tune hq -rc vbr -cq 23 -qmin 18 -qmax 30 -c:a aac -b:a 128k -movflags +faststart "{output}"',
            'suffix': '_nvenc_hevc_cq23',
        },
        {
            'key': 'preset_nvenc_hevc_cq26',
            'cmd': 'ffmpeg -hwaccel cuda -threads 0 -i "{input}" -c:v hevc_nvenc -preset p7 -tune hq -rc vbr -cq 26 -qmin 20 -qmax 32 -c:a aac -b:a 96k -movflags +faststart "{output}"',
            'suffix': '_nvenc_hevc_cq26',
        },
        {
            'key': 'preset_nvenc_h264',
            'cmd': 'ffmpeg -hwaccel cuda -threads 0 -i "{input}" -c:v h264_nvenc -preset p7 -tune hq -rc vbr -cq 23 -qmin 18 -qmax 30 -c:a aac -b:a 128k -movflags +faststart "{output}"',
            'suffix': '_nvenc_h264',
        },
    ]

    def _get_localized_presets(self):
        """Return presets with labels and comments in the current language."""
        return [
            {
                'key': p['key'],
                'label': self.app.t(f"{p['key']}_label"),
                'comment': self.app.t(f"{p['key']}_comment"),
                'cmd': p['cmd'],
                'suffix': p['suffix'],
            }
            for p in self.PRESETS
        ]

    def __init__(self, app, file_paths, file_durations):
        self.app = app
        self.file_paths = file_paths
        self.file_durations = file_durations
        self.total_duration = sum(file_durations.values())
        self.running = False

        base_dir = Path(sys.executable if getattr(sys, 'frozen', False) else __file__).parent
        self.history_file = base_dir / "cmd_history.json"
        self._cmd_history = self._load_history()

        self.win = ctk.CTkToplevel(app.root)
        self.win.title(app.t('batch_title'))
        self.win.geometry("680x600")
        self.win.minsize(520, 500)
        self.win.transient(app.root)
        self.win.grab_set()

        c = app._get_tree_colors()
        self.win.configure(fg_color=c['bg'])

        if HAS_PYWINSTYLES and app.current_theme == 'dark':
            try:
                pywinstyles.apply_style(self.win, "dark")
                pywinstyles.change_header_color(self.win, c['bg'])
            except:
                pass

        self.win.withdraw()
        self.setup_ui()
        self.app.center_window(self.win)
        self.win.deiconify()

        self.win.protocol("WM_DELETE_WINDOW", self.on_close)

    def _c(self):
        return self.app._get_tree_colors()

    def t(self, key, *args):
        text = TEXTS[self.app.lang].get(key, key)
        if args:
            return text.format(*args)
        return text

    def on_close(self):
        if self.running and not self._cancelled:
            messagebox.showwarning(self.t('warning'),
                                   self.t('batch_running_warn'),
                                   parent=self.win)
            return
        self.win.destroy()

    def setup_ui(self):
        c = self._c()
        f = self.app.font_family
        s = self.app.font_size

        # -- Header --
        header = ctk.CTkFrame(self.win, fg_color="transparent", corner_radius=0)
        header.pack(fill=tk.X, padx=24, pady=(20, 12))
        ctk.CTkLabel(header, text=self.t('batch_title'),
                     text_color=c['fg'],
                     font=(f, s + 3, 'bold')).pack(side=tk.LEFT)
        ctk.CTkLabel(header, text=self.t('batch_selected', len(self.file_paths)),
                     text_color=c['fg2'],
                     font=(f, s - 1)).pack(side=tk.RIGHT)

        # -- Command input --
        cmd_frame = ctk.CTkFrame(self.win, fg_color=c['card'], corner_radius=8)
        cmd_frame.pack(fill=tk.BOTH, expand=True, padx=24, pady=(0, 8))

                # -- History combobox --
        hist_row = ctk.CTkFrame(cmd_frame, fg_color="transparent", corner_radius=0)
        hist_row.pack(fill=tk.X, padx=12, pady=(12, 0))
        ctk.CTkLabel(hist_row, text=self.t('history_cmd') + ':',
                     text_color=c['fg'],
                     font=(f, s)).pack(side=tk.LEFT, padx=(0, 6))
        hist_display = []
        for hc in self._cmd_history:
            flat = hc.replace('\n', ' ').strip()
            hist_display.append(flat[:70] + ('...' if len(flat) > 70 else ''))
        if not hist_display:
            hist_display = ['']
        self.hist_var = tk.StringVar(value=hist_display[0])
        self.combo_hist = ToggleComboBox(hist_row, variable=self.hist_var,
                                          values=hist_display, state="readonly",
                                          font=(f, s - 1), corner_radius=6,
                                          command=self._on_history_select)
        self.combo_hist.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.cmd_text = ctk.CTkTextbox(cmd_frame, wrap="word", height=100,
                                       fg_color=c['input_bg'], text_color=c['fg'],
                                       font=(f, s),
                                       corner_radius=6, border_width=0)
        self.cmd_text.pack(fill=tk.BOTH, expand=True, padx=12, pady=(12, 0))

        # -- Hint --
        ctk.CTkLabel(cmd_frame, text=self.t('batch_hint'),
                     text_color=c['fg2'],
                     font=(f, s - 2),
                     anchor="w", justify="left",
                     wraplength=620).pack(fill=tk.X, padx=12, pady=(4, 0))

        # -- Presets --
        presets_row = ctk.CTkFrame(cmd_frame, fg_color="transparent", corner_radius=0)
        presets_row.pack(fill=tk.X, padx=12, pady=(8, 0))
        ctk.CTkLabel(presets_row, text=self.t('batch_presets') + ':',
                     text_color=c['fg'],
                     font=(f, s)).pack(side=tk.LEFT, padx=(0, 6))

        self.preset_var = tk.StringVar()
        self._localized_presets = self._get_localized_presets()
        preset_names = [p['label'] for p in self._localized_presets]
        self.combo_preset = ToggleComboBox(presets_row, variable=self.preset_var,
                                           values=preset_names, state="readonly",
                                           font=(f, s - 1), corner_radius=6,
                                           command=self._on_preset_select)
        self.combo_preset.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # -- Output suffix --
        suffix_row = ctk.CTkFrame(cmd_frame, fg_color="transparent", corner_radius=0)
        suffix_row.pack(fill=tk.X, padx=12, pady=(8, 12))
        ctk.CTkLabel(suffix_row, text=self.t('batch_output_suffix'),
                     text_color=c['fg'],
                     font=(f, s)).pack(side=tk.LEFT, padx=(0, 8))
        self.suffix_var = tk.StringVar(value='_processed')
        suffix_entry = ctk.CTkEntry(suffix_row, textvariable=self.suffix_var,
                                    fg_color=c['input_bg'], text_color=c['fg'],
                                    font=(f, s),
                                    corner_radius=6, border_width=1,
                                    width=140)
        suffix_entry.pack(side=tk.LEFT)

        # -- Log area --
        log_frame = ctk.CTkFrame(self.win, fg_color=c['card'], corner_radius=8)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=24, pady=(0, 12))

        self.log_text = ctk.CTkTextbox(log_frame, wrap="word", height=100,
                                       fg_color=c['input_bg'], text_color=c['fg'],
                                       font=(f, s - 1),
                                       corner_radius=6, border_width=0)
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=12, pady=(12, 8))
        self.log_text.configure(state="disabled")

        # -- Progress --
        self.prog_frame = ctk.CTkFrame(log_frame, fg_color="transparent", corner_radius=0)
        self.prog_frame.pack(fill=tk.X, padx=12, pady=(0, 6))

        self.prog_bar = ctk.CTkProgressBar(self.prog_frame, mode='determinate', height=8, corner_radius=4)
        self.prog_bar.pack(fill=tk.X)
        self.prog_bar.set(0)

        self.prog_label = ctk.CTkLabel(self.prog_frame,
                                       text='',
                                       text_color=c['fg2'],
                                       font=(f, s - 2),
                                       anchor="w")
        self.prog_label.pack(fill=tk.X, pady=(4, 6))

        # -- Buttons --
        btn_row = ctk.CTkFrame(self.win, fg_color="transparent", corner_radius=0)
        btn_row.pack(fill=tk.X, padx=24, pady=(0, 20))

        cancel_btn = ctk.CTkButton(btn_row, text=self.t('cancel'),
                                   font=(f, s),
                                   fg_color=c['button_bg'],
                                   hover_color=c['button_hover'],
                                   text_color=c['fg'],
                                   corner_radius=6,
                                   height=36, width=90,
                                   command=self.on_close)
        cancel_btn.pack(side=tk.RIGHT, padx=(8, 0))

        self.run_btn = ctk.CTkButton(btn_row, text=self.t('batch_run'),
                                     font=(f, s, 'bold'),
                                     fg_color=c['accent'],
                                     hover_color=c['accent_hover'],
                                     text_color=c['accent_text'],
                                     corner_radius=6,
                                     height=36, width=100,
                                     command=self.execute)
        self.run_btn.pack(side=tk.RIGHT)

    def log(self, msg):
        self.log_text.configure(state="normal")
        self.log_text.insert(tk.END, msg + '\n')
        self.log_text.see(tk.END)
        self.log_text.configure(state="disabled")
        self.win.update_idletasks()

    _PROG_KEYS = ('frame=', 'fps=', 'q=', 'size=', 'out_time', 'dup_frames=',
                  'drop_frames=', 'speed=', 'progress=', 'bitrate=',
                  'total_size=', 'stream_', 'out_time_ms=', 'out_time_us=')

    @staticmethod
    def _strip_comments(cmd_text):
        lines = [l for l in cmd_text.split('\n') if not l.strip().startswith('#')]
        return '\n'.join(lines).strip()

    def _parse_ffmpeg_time(self, line):
        if line.startswith('out_time='):
            ts = line.split('=', 1)[1]
            m = re.match(r'(\d+):(\d+):(\d+)\.(\d+)', ts)
            if m:
                h, mi, s, ms = int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4)
                return h * 3600 + mi * 60 + s + int(ms[:3].ljust(3, '0')) / 1000
            return None
        if line.startswith('out_time_us='):
            try:
                return int(line.split('=', 1)[1]) / 1_000_000
            except Exception:
                return None
        m = re.search(r'time=(\d+):(\d+):(\d+)\.(\d+)', line)
        if m:
            h, mi, s, ms = int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4)
            return h * 3600 + mi * 60 + s + int(ms[:3].ljust(3, '0')) / 1000
        return None

    def _load_history(self):
        if self.history_file.exists():
            try:
                with open(self.history_file, 'r', encoding='utf-8') as fh:
                    return json.load(fh)
            except Exception:
                pass
        return []

    def _save_history(self, cmd):
        history = self._cmd_history
        if cmd in history:
            history.remove(cmd)
        history.insert(0, cmd)
        self._cmd_history = history[:10]
        try:
            with open(self.history_file, 'w', encoding='utf-8') as fh:
                json.dump(self._cmd_history, fh, ensure_ascii=False, indent=2)
        except Exception:
            pass
        if hasattr(self, 'combo_hist'):
            hist_display = []
            for hc in self._cmd_history:
                flat = hc.replace('\n', ' ').strip()
                hist_display.append(flat[:70] + ('...' if len(flat) > 70 else ''))
            if not hist_display:
                hist_display = ['']
            self.combo_hist.configure(values=hist_display)
            self.hist_var.set(hist_display[0])



    def _on_history_select(self, choice):
        if not choice:
            return
        display_list = []
        for hc in self._cmd_history:
            flat = hc.replace('\n', ' ').strip()
            display_list.append(flat[:70] + ('...' if len(flat) > 70 else ''))
        if choice in display_list:
            idx = display_list.index(choice)
            if idx < len(self._cmd_history):
                cmd = self._cmd_history[idx]
                self.cmd_text.delete('1.0', tk.END)
                self.cmd_text.insert('1.0', cmd)

    def _on_preset_select(self, choice):
        for p in self._localized_presets:
            if p['label'] == choice:
                self._fill_preset(p)
                break

    def _fill_preset(self, p):
        full_cmd = p['comment'] + '\n' + p['cmd']
        self.cmd_text.delete('1.0', tk.END)
        self.cmd_text.insert('1.0', full_cmd)
        self.suffix_var.set(p['suffix'])

    def execute(self):
        cmd_template = self.cmd_text.get('1.0', 'end-1c').strip()
        if not cmd_template:
            return
        suffix = self.suffix_var.get().strip()

        if not messagebox.askyesno(self.t('batch_run'),
                                   self.t('batch_confirm', len(self.file_paths)),
                                   parent=self.win):
            return

        self._save_history(cmd_template)

        self.running = True
        self._cancelled = False
        self._active_procs = []
        self._active_outs = {}
        c = self._c()
        self.run_btn.configure(state="disabled", text=self.t('batch_running'),
                               fg_color=c['button_bg'], hover_color=c['button_hover'])
        for child in self.win.winfo_children():
            if isinstance(child, ctk.CTkFrame):
                for sub in child.winfo_children():
                    if isinstance(sub, ctk.CTkButton):
                        btn_text = sub.cget('text')
                        if btn_text in (self.t('cancel'), 'Cancel'):
                            sub.configure(text=self.t('cancel'), command=self.cancel_execution)
                            self._cancel_btn = sub
                            break
        self.log_text.configure(state="normal")
        self.log_text.delete('1.0', tk.END)
        self.log_text.configure(state="disabled")
        self.prog_bar.set(0)
        self.prog_bar.configure(mode='determinate')
        self.prog_label.configure(text=self.t('batch_eta_unknown'))
        self._batch_start_time = time.time()

        has_durations = self.total_duration > 0

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
                name, ext = os.path.splitext(os.path.basename(fp))
                out_path = os.path.join(folder, f"{name}{suffix}{ext}")
                cmd = cmd_template.replace('{input}', fp)
                cmd = cmd.replace('{output}', out_path)
                cmd = cmd.replace('{name}', name)
                cmd = cmd.replace('{ext}', ext)
                cmd = cmd.replace('{folder}', folder)
                cmd = self._strip_comments(cmd)
                is_ffmpeg_cmd = cmd.strip().startswith('ffmpeg')
                if is_ffmpeg_cmd:
                    cmd = 'ffmpeg -progress pipe:2 -nostats' + cmd[6:]
                work_items.append({
                    'fp': fp, 'file_dur': file_dur, 'seq': idx + 1,
                    'cmd': cmd, 'out_path': out_path,
                    'filename': os.path.basename(fp),
                    'is_ffmpeg': is_ffmpeg_cmd,
                })

            from queue import Queue
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

                    self.win.after(0, self.log, f"[{seq}/{total}] {item['filename']}")
                    self.win.after(0, self.log, f"  > {cmd}")

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
                                if item['is_ffmpeg'] and has_durations and file_dur > 0:
                                    t = self._parse_ffmpeg_time(line)
                                    if t is not None:
                                        with lock:
                                            active_positions[wid] = min(t, file_dur)
                                            cur_total = completed_dur + sum(active_positions.values())
                                            fraction = cur_total / self.total_duration
                                        self.win.after(0, lambda f=fraction: self._update_progress(ok + fail, f))
                                        continue
                                if item['is_ffmpeg'] and any(line.startswith(k) for k in self._PROG_KEYS):
                                    continue
                                self.win.after(0, self.log, f"  {line.strip()}")
                        if buf.strip():
                            self.win.after(0, self.log, f"  {buf.strip()}")

                        proc.wait()
                        rc = proc.returncode

                        if proc in self._active_procs:
                            self._active_procs.remove(proc)
                        self._active_outs.pop(wid, None)

                        if self._cancelled:
                            if os.path.exists(out_path):
                                try:
                                    os.remove(out_path)
                                    self.win.after(0, self.log, self.t('batch_deleted_partial'))
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
                            self.win.after(0, self.log, "  OK")
                        else:
                            with lock:
                                fail += 1
                                failed_files.append(fp)
                                active_positions.pop(wid, None)
                            self.win.after(0, self.log, f"  FAIL (code {rc})")
                    except Exception as e:
                        with lock:
                            fail += 1
                            failed_files.append(fp)
                            active_positions.pop(wid, None)
                        if proc in self._active_procs:
                            self._active_procs.remove(proc)
                        self._active_outs.pop(wid, None)
                        self.win.after(0, self.log, f"  ERROR: {e}")

                    done = ok + fail
                    self.win.after(0, lambda d=done: self._update_progress(d))
                    q.task_done()

            threads = []
            for wid in range(num_workers):
                t = threading.Thread(target=worker, args=(wid,), daemon=True)
                t.start()
                threads.append(t)
            for t in threads:
                t.join()

            self.win.after(0, lambda: self.finish(ok, fail, failed_files))

        threading.Thread(target=task, daemon=True).start()

    def cancel_execution(self):
        if not self.running:
            return
        self._cancelled = True
        self.log(self.t('batch_cancelling'))
        for proc in list(self._active_procs):
            try:
                proc.kill()
                self.log(self.t('batch_killed_proc'))
            except Exception:
                pass
        self._active_procs.clear()

    def _update_progress(self, done, fraction=None):
        total = len(self.file_paths)
        if fraction is not None and self.total_duration > 0:
            self.prog_bar.configure(mode='determinate')
            self.prog_bar.set(fraction)
            pct = round(fraction * 100)
        else:
            self.prog_bar.configure(mode='determinate')
            pct = round(done / total * 100) if total > 0 else 0
            self.prog_bar.set(done / total if total > 0 else 0)
        self.prog_label.configure(text=self.t('batch_progress', done, total, pct))
        if done >= 0 and done < total and hasattr(self, '_batch_start_time'):
            elapsed = time.time() - self._batch_start_time
            if fraction is not None and fraction > 0 and self.total_duration > 0:
                remaining = elapsed / fraction - elapsed
            elif done > 0:
                avg = elapsed / done
                remaining = avg * (total - done)
            else:
                remaining = 0
            if remaining > 0:
                if remaining < 60:
                    eta = f"{round(remaining)}s"
                elif remaining < 3600:
                    eta = f"{int(remaining // 60)}m {round(remaining % 60)}s"
                else:
                    eta = f"{int(remaining // 3600)}h {int((remaining % 3600) // 60)}m"
                self.prog_label.configure(text=self.prog_label.cget('text') + '  |  ' + self.t('batch_eta', eta))

    def finish(self, ok, fail, failed_files):
        self.running = False
        self._active_procs.clear()
        self._active_outs.clear()
        self.log('─' * 50)
        if self._cancelled:
            self.log(self.t('batch_cancelled_summary', ok, fail))
        else:
            self.log(self.t('batch_done', ok, fail))
        c = self._c()
        self.run_btn.configure(state="normal", text=self.t('batch_run'),
                               fg_color=c['accent'], hover_color=c['accent_hover'])
        if hasattr(self, '_cancel_btn') and self._cancel_btn.winfo_exists():
            self._cancel_btn.configure(text=self.t('cancel'), command=self.on_close)
        if failed_files:
            msg = self.t('failed_files_hdr', len(failed_files))
            for fp in failed_files:
                msg += f"  {os.path.basename(fp)}\n"
            self.win.after(100, lambda m=msg: messagebox.showwarning(self.t('batch_fail_title'), m, parent=self.win))
        elif ok > 0 and not self._cancelled:
            msg = self.t('batch_success_msg', ok)
            def _on_success():
                if messagebox.askyesno(self.t('batch_success_title'), f"{msg}\n\n{self.t('batch_success_ask')}", parent=self.win):
                    self.win.destroy()
                    self.app.refresh_current_folder()
            self.win.after(150, _on_success)


# Color helpers
def _lighten(hex_color, factor=0.1):
    if not hex_color or not hex_color.startswith('#'):
        return hex_color or '#000000'
    hex_color = hex_color.lstrip('#')
    r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    r = min(255, int(r + (255 - r) * factor))
    g = min(255, int(g + (255 - g) * factor))
    b = min(255, int(b + (255 - b) * factor))
    return f"#{r:02x}{g:02x}{b:02x}"


def _darken(hex_color, factor=0.1):
    if not hex_color or not hex_color.startswith('#'):
        return hex_color or '#000000'
    hex_color = hex_color.lstrip('#')
    r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    r = max(0, int(r * (1 - factor)))
    g = max(0, int(g * (1 - factor)))
    b = max(0, int(b * (1 - factor)))
    return f"#{r:02x}{g:02x}{b:02x}"


if __name__ == "__main__":
    setup_exception_logging()
    root = ctk.CTk()
    app = VideoInfoApp(root)
    root.mainloop()
