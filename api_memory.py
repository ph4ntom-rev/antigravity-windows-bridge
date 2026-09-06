"""64-bit-safe memory calls with least-required access and bounded transfers."""
import base64
import ctypes
from ctypes import wintypes
from contextlib import contextmanager
from server import router, APIError

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
kernel32.CloseHandle.restype = wintypes.BOOL
for name in ("ReadProcessMemory", "WriteProcessMemory"):
    function = getattr(kernel32, name)
    function.argtypes = (wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t))
    function.restype = wintypes.BOOL

MAX_TRANSFER = 1024 * 1024


def checked_address(value, size):
    address = int(value, 16) if isinstance(value, str) and value.startswith("0x") else int(value)
    maximum = (1 << (ctypes.sizeof(ctypes.c_void_p) * 8)) - 1
    if isinstance(value, bool) or not 0 < size <= MAX_TRANSFER or not 0 < address <= maximum - size + 1:
        raise APIError("Invalid address or transfer size (maximum 1 MiB)")
    return address


@contextmanager
def open_process(pid, access):
    if isinstance(pid, bool) or not 0 < int(pid) <= 0xFFFFFFFF:
        raise APIError("Invalid PID")
    handle = kernel32.OpenProcess(access, False, int(pid))
    if not handle:
        raise APIError(f"OpenProcess failed: {ctypes.get_last_error()}")
    try:
        yield handle
    finally:
        kernel32.CloseHandle(handle)


@router.post(r"/api/memory/read", capability="memory_read")
def read_memory(req, **kwargs):
    size = int(req.get("size", 4))
    address = checked_address(req.get("address"), size)
    buffer = ctypes.create_string_buffer(size)
    transferred = ctypes.c_size_t()
    with open_process(req.get("pid"), 0x0010) as handle:  # PROCESS_VM_READ
        if not kernel32.ReadProcessMemory(handle, address, buffer, size, ctypes.byref(transferred)):
            raise APIError(f"ReadProcessMemory failed: {ctypes.get_last_error()}")
    data = buffer.raw[:transferred.value]
    return {"address": hex(address), "size": len(data), "data_hex": data.hex(), "data_b64": base64.b64encode(data).decode("ascii")}


@router.post(r"/api/memory/write", capability="memory_write")
def write_memory(req, **kwargs):
    raw = req.get("data_hex")
    if not isinstance(raw, str) or not raw or len(raw) > MAX_TRANSFER * 2:
        raise APIError("Invalid hex payload")
    data = bytes.fromhex(raw)
    address = checked_address(req.get("address"), len(data))
    buffer = ctypes.create_string_buffer(data)
    transferred = ctypes.c_size_t()
    with open_process(req.get("pid"), 0x0020 | 0x0008) as handle:
        if not kernel32.WriteProcessMemory(handle, address, buffer, len(data), ctypes.byref(transferred)):
            raise APIError(f"WriteProcessMemory failed: {ctypes.get_last_error()}")
    if transferred.value != len(data):
        raise APIError("Partial write; inspect target before retrying", 500)
    return {"success": True, "bytes_written": transferred.value}
