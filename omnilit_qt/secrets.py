from __future__ import annotations

import base64
import os


DPAPI_PREFIX = "dpapi:"
PLAIN_PREFIX = "plain:"


def _plain_encode(secret: str) -> str:
    """生成兼容回退密文。参数：明文。返回值：带格式前缀的 Base64 文本。"""
    return PLAIN_PREFIX + base64.b64encode(secret.encode("utf-8")).decode("ascii")


def _plain_decode(payload: str) -> str:
    """解析兼容回退密文。参数：带格式前缀的文本。返回值：明文。"""
    return base64.b64decode(payload[len(PLAIN_PREFIX) :]).decode("utf-8")


def _dpapi_transform(data: bytes, protect: bool) -> bytes:
    """调用 Windows DPAPI。参数：字节数据和加密方向。返回值：转换后的字节数据。"""
    import ctypes
    from ctypes import wintypes

    class DATA_BLOB(ctypes.Structure):
        """表示 DPAPI 输入输出缓冲区。"""

        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    buffer = ctypes.create_string_buffer(data)
    source = DATA_BLOB(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))
    target = DATA_BLOB()
    function = ctypes.windll.crypt32.CryptProtectData if protect else ctypes.windll.crypt32.CryptUnprotectData
    args = (ctypes.byref(source), None, None, None, None, 0, ctypes.byref(target))
    if not function(*args):
        raise OSError("Windows DPAPI 调用失败。")
    try:
        return ctypes.string_at(target.pbData, target.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(target.pbData)


def protect_secret(secret: str) -> str:
    """加密登录密码。参数：明文密码。返回值：可持久化的带格式密文。"""
    if not secret:
        return ""
    if os.name != "nt":
        # 非 Windows 平台暂时没有系统钥匙串依赖，回退格式只用于兼容，不提供强加密保证。
        return _plain_encode(secret)
    encrypted = _dpapi_transform(secret.encode("utf-8"), True)
    return DPAPI_PREFIX + base64.b64encode(encrypted).decode("ascii")


def unprotect_secret(payload: str) -> str:
    """解密登录密码。参数：持久化密文。返回值：明文密码。"""
    if not payload:
        return ""
    if payload.startswith(PLAIN_PREFIX):
        return _plain_decode(payload)
    if payload.startswith(DPAPI_PREFIX) and os.name == "nt":
        raw = base64.b64decode(payload[len(DPAPI_PREFIX) :])
        return _dpapi_transform(raw, False).decode("utf-8")
    raise ValueError("无法识别保存的密码格式。")
