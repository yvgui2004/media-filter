"""GPU discovery for the local YOLOv8 tagger.

ONNX Runtime exposes ``DmlExecutionProvider`` on every Windows build, even when
the machine only has the WARP software rasterizer.  That provider is therefore
not proof of hardware acceleration.  This module enumerates real DXGI adapters
with ctypes (no third-party dependency) so the settings page can say which GPU
will actually be used, and so the tagger can avoid WARP.

The app is Windows-only; on other platforms every helper here reports "no GPU".
"""

from __future__ import annotations

import ctypes
import sys
from dataclasses import dataclass
from functools import lru_cache

DEVICE_CHOICES: tuple[str, ...] = ("auto", "cpu", "gpu")

VENDOR_NAMES: dict[int, str] = {
    0x10DE: "NVIDIA",
    0x1002: "AMD",
    0x8086: "Intel",
    0x1414: "Microsoft",
    0x5143: "Qualcomm",
}

_DXGI_ADAPTER_FLAG_SOFTWARE = 0x2
_IID_IDXGIFACTORY1 = "770aae78-f26f-4dba-a829-253c83d1b387"


def normalize_device(value: str | None) -> str:
    return value if value in DEVICE_CHOICES else "auto"


@dataclass(frozen=True)
class AdapterInfo:
    index: int
    name: str
    vendor_id: int
    dedicated_video_mb: int
    shared_system_mb: int
    software: bool

    @property
    def vendor(self) -> str:
        return VENDOR_NAMES.get(self.vendor_id, "GPU")

    @property
    def is_integrated(self) -> bool:
        # Discrete cards report at least a gigabyte of dedicated VRAM; iGPUs
        # and APUs share system memory and report little or none.
        return not self.software and self.dedicated_video_mb < 1024


@dataclass(frozen=True)
class DeviceReport:
    adapters: tuple[AdapterInfo, ...]

    @property
    def hardware(self) -> AdapterInfo | None:
        """Best real adapter: discrete first, then the largest iGPU."""
        candidates = [item for item in self.adapters if not item.software]
        if not candidates:
            return None
        candidates.sort(
            key=lambda item: (
                not item.is_integrated,
                item.dedicated_video_mb,
                item.shared_system_mb,
            ),
            reverse=True,
        )
        return candidates[0]

    @property
    def software_only(self) -> bool:
        return bool(self.adapters) and not any(
            not item.software for item in self.adapters
        )


@dataclass(frozen=True)
class DeviceChoice:
    state: str          # gpu | igpu | cpu | warp | unavailable
    adapter: AdapterInfo | None
    use_dml: bool


class _LUID(ctypes.Structure):
    _fields_ = [
        ("LowPart", ctypes.c_uint32),
        ("HighPart", ctypes.c_int32),
    ]


class _DXGIAdapterDesc1(ctypes.Structure):
    _fields_ = [
        ("Description", ctypes.c_wchar * 128),
        ("VendorId", ctypes.c_uint32),
        ("DeviceId", ctypes.c_uint32),
        ("SubSysId", ctypes.c_uint32),
        ("Revision", ctypes.c_uint32),
        ("DedicatedVideoMemory", ctypes.c_size_t),
        ("DedicatedSystemMemory", ctypes.c_size_t),
        ("SharedSystemMemory", ctypes.c_size_t),
        ("AdapterLuid", _LUID),
        ("Flags", ctypes.c_uint32),
    ]


class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_uint32),
        ("Data2", ctypes.c_uint16),
        ("Data3", ctypes.c_uint16),
        ("Data4", ctypes.c_ubyte * 8),
    ]


def _guid(text: str) -> _GUID:
    parts = text.split("-")
    data4 = bytes.fromhex(parts[3] + parts[4])
    return _GUID(
        int(parts[0], 16),
        int(parts[1], 16),
        int(parts[2], 16),
        (ctypes.c_ubyte * 8)(*data4),
    )


def _com_method(pointer: ctypes.c_void_p, index: int, prototype):
    vtable = ctypes.cast(
        pointer, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))
    ).contents
    return prototype(vtable[index])


@lru_cache(maxsize=1)
def enumerate_adapters() -> tuple[AdapterInfo, ...]:
    """Enumerate DXGI adapters once per process.

    Cached because the settings dialog may probe several times; adapter changes
    (eGPU hot-plug) are rare enough to require an app restart.
    """
    if sys.platform != "win32":
        return ()
    win_dll = getattr(ctypes, "WinDLL", None)
    if win_dll is None:
        return ()
    try:
        dxgi = win_dll("dxgi.dll")
    except OSError:
        return ()

    released = ctypes.WINFUNCTYPE(ctypes.c_uint32, ctypes.c_void_p)
    enum_adapters = ctypes.WINFUNCTYPE(
        ctypes.c_long,
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.POINTER(ctypes.c_void_p),
    )
    get_desc = ctypes.WINFUNCTYPE(
        ctypes.c_long, ctypes.c_void_p, ctypes.POINTER(_DXGIAdapterDesc1)
    )

    create = dxgi.CreateDXGIFactory1
    create.argtypes = [ctypes.POINTER(_GUID), ctypes.POINTER(ctypes.c_void_p)]
    create.restype = ctypes.c_long

    factory = ctypes.c_void_p()
    if create(ctypes.byref(_guid(_IID_IDXGIFACTORY1)), ctypes.byref(factory)) < 0:
        return ()

    adapters: list[AdapterInfo] = []
    try:
        enum = _com_method(factory, 12, enum_adapters)  # IDXGIFactory1::EnumAdapters1
        for index in range(32):
            adapter = ctypes.c_void_p()
            if enum(factory, index, ctypes.byref(adapter)) < 0:
                break
            try:
                desc = _DXGIAdapterDesc1()
                get = _com_method(adapter, 10, get_desc)  # IDXGIAdapter1::GetDesc1
                if get(adapter, ctypes.byref(desc)) < 0:
                    continue
                software = bool(desc.Flags & _DXGI_ADAPTER_FLAG_SOFTWARE)
                software = software or desc.VendorId == 0x1414
                adapters.append(
                    AdapterInfo(
                        index=index,
                        name=" ".join(desc.Description.split()),
                        vendor_id=desc.VendorId,
                        dedicated_video_mb=int(desc.DedicatedVideoMemory // (1024 * 1024)),
                        shared_system_mb=int(desc.SharedSystemMemory // (1024 * 1024)),
                        software=software,
                    )
                )
            finally:
                release = _com_method(adapter, 2, released)  # IUnknown::Release
                release(adapter)
    finally:
        release = _com_method(factory, 2, released)
        release(factory)
    return tuple(adapters)


def inspect() -> DeviceReport:
    return DeviceReport(enumerate_adapters())


@lru_cache(maxsize=1)
def dml_available() -> bool:
    """True when this install can create a DirectML session at all."""
    try:
        import onnxruntime as ort

        return "DmlExecutionProvider" in ort.get_available_providers()
    except Exception:
        return False


def choose(device: str, report: DeviceReport, provider: bool) -> DeviceChoice:
    """Resolve the saved preference against what the machine actually has."""
    device = normalize_device(device)
    if device == "cpu":
        return DeviceChoice("cpu", None, False)
    if not provider:
        return DeviceChoice("unavailable" if device == "gpu" else "cpu", None, False)
    adapter = report.hardware
    if adapter is not None:
        state = "igpu" if adapter.is_integrated else "gpu"
        return DeviceChoice(state, adapter, True)
    if device == "gpu":
        return DeviceChoice("unavailable", None, False)
    return DeviceChoice("warp" if report.software_only else "cpu", None, False)


def short_adapter_name(name: str) -> str:
    """'NVIDIA GeForce RTX 5070 Ti' -> 'RTX 5070 Ti' for narrow cards."""
    text = " ".join((name or "").replace("(R)", "").replace("(TM)", "").split())
    for prefix in ("NVIDIA GeForce ", "NVIDIA ", "AMD Radeon ", "AMD ", "Intel "):
        if text.startswith(prefix):
            text = text[len(prefix) :]
            break
    for suffix in (" Graphics", " Laptop GPU", " Video Adapter", " GPU"):
        if text.endswith(suffix):
            text = text[: -len(suffix)]
            break
    return text or name or "GPU"


def session_providers(device: str) -> list[str]:
    """Provider list for ONNX Runtime; CPU is always the fallback."""
    choice = choose(device, inspect(), dml_available())
    if choice.use_dml:
        return ["DmlExecutionProvider", "CPUExecutionProvider"]
    return ["CPUExecutionProvider"]


def dml_device_id(device: str) -> int:
    """DXGI index of the adapter DirectML should use (0 when unknown)."""
    choice = choose(device, inspect(), dml_available())
    if choice.use_dml and choice.adapter is not None:
        return choice.adapter.index
    return 0