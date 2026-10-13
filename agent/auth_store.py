"""Protect the user's Discord OAuth credentials with Windows DPAPI CurrentUser."""
import ctypes
from ctypes import wintypes
import json
from pathlib import Path

CRYPTPROTECT_UI_FORBIDDEN = 1


class Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD),
                ("pbData", ctypes.POINTER(ctypes.c_ubyte))]


crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
crypt32.CryptProtectData.argtypes = [
    ctypes.POINTER(Blob), wintypes.LPCWSTR, ctypes.POINTER(Blob),
    ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
crypt32.CryptProtectData.restype = wintypes.BOOL
crypt32.CryptUnprotectData.argtypes = [
    ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.POINTER(Blob),
    ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
crypt32.CryptUnprotectData.restype = wintypes.BOOL
kernel32.LocalFree.argtypes = [ctypes.c_void_p]
kernel32.LocalFree.restype = ctypes.c_void_p


def blob_from(data: bytes):
    buffer = ctypes.create_string_buffer(data)
    blob = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    return blob, buffer


def crypt(data: bytes, *, protect: bool) -> bytes:
    source, source_buffer = blob_from(data)
    result = Blob()
    operation = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    if not operation(ctypes.byref(source), None, None, None, None,
                     CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(result)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(result.pbData, result.cbData)
    finally:
        kernel32.LocalFree(ctypes.cast(result.pbData, ctypes.c_void_p))


def save_token(path: Path, token: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    encrypted = crypt(json.dumps(token).encode("utf-8"), protect=True)
    temp = path.with_suffix(".new")
    temp.write_bytes(encrypted)
    temp.replace(path)


def load_token(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(crypt(path.read_bytes(), protect=False))
    except (ValueError, OSError):
        return None
