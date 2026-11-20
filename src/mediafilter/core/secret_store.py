"""Windows DPAPI helpers for storing the cloud API key at rest.

The ciphertext is bound to the current Windows user; copying config.json to
another machine produces an unreadable value, which the settings dialog treats
as "please enter the key again".  Nothing here ever logs the plaintext.
"""

from __future__ import annotations

import base64
import ctypes
import sys
from ctypes import wintypes

CRYPTPROTECT_UI_FORBIDDEN = 0x01


class SecretStoreError(RuntimeError):
    """The platform could not protect or unprotect the secret."""


class _DataBlob(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_char)),
    ]


def is_available() -> bool:
    return sys.platform == "win32"


def protect(text: str) -> str:
    """Encrypt ``text`` for the current Windows user and return Base64."""
    if not text:
        return ""
    if not is_available():
        raise SecretStoreError("当前系统不支持 Windows DPAPI，密钥无法安全保存")
    return base64.b64encode(_crypt(text.encode("utf-8"), protect=True)).decode("ascii")


def unprotect(token: str) -> str:
    """Decrypt a Base64 DPAPI blob; raises SecretStoreError when unreadable."""
    if not token:
        return ""
    if not is_available():
        raise SecretStoreError("当前系统不支持 Windows DPAPI，无法读取密钥")
    try:
        raw = base64.b64decode(token, validate=True)
    except (ValueError, TypeError) as exc:
        raise SecretStoreError("密钥密文格式不正确，请重新填写") from exc
    try:
        return _crypt(raw, protect=False).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SecretStoreError("密钥密文无法解析，请重新填写") from exc


def key_hint(text: str) -> str:
    """Last four characters, for a masked UI hint only."""
    text = (text or "").strip()
    return text[-4:] if len(text) >= 4 else ""


def _crypt(data: bytes, protect: bool) -> bytes:
    if not is_available():
        raise SecretStoreError("当前系统不支持 Windows DPAPI")
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    buffer = ctypes.create_string_buffer(data, len(data))
    in_blob = _DataBlob(
        len(data),
        ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)),
    )
    out_blob = _DataBlob()
    description = "mediafilter" if protect else None

    crypt32.CryptProtectData.argtypes = [
        ctypes.POINTER(_DataBlob),
        wintypes.LPCWSTR,
        ctypes.POINTER(_DataBlob),
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(_DataBlob),
    ]
    crypt32.CryptProtectData.restype = wintypes.BOOL
    crypt32.CryptUnprotectData.argtypes = [
        ctypes.POINTER(_DataBlob),
        ctypes.POINTER(wintypes.LPWSTR),
        ctypes.POINTER(_DataBlob),
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(_DataBlob),
    ]
    crypt32.CryptUnprotectData.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [wintypes.HLOCAL]
    kernel32.LocalFree.restype = wintypes.HLOCAL

    try:
        if protect:
            ok = crypt32.CryptProtectData(
                ctypes.byref(in_blob),
                description,
                None,
                None,
                None,
                CRYPTPROTECT_UI_FORBIDDEN,
                ctypes.byref(out_blob),
            )
        else:
            description_out = wintypes.LPWSTR()
            ok = crypt32.CryptUnprotectData(
                ctypes.byref(in_blob),
                ctypes.byref(description_out),
                None,
                None,
                None,
                CRYPTPROTECT_UI_FORBIDDEN,
                ctypes.byref(out_blob),
            )
    except OSError as exc:
        raise SecretStoreError("Windows 安全存储调用失败") from exc

    if not ok:
        error = ctypes.get_last_error()
        raise SecretStoreError(f"Windows 安全存储失败（错误 {error}）")
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        if out_blob.pbData:
            kernel32.LocalFree(out_blob.pbData)