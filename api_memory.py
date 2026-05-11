import ctypes
from ctypes import wintypes
from server import router, APIError
import urllib.parse

kernel32 = ctypes.windll.kernel32

# Constants
PROCESS_ALL_ACCESS = 0x1F0FFF
MEM_COMMIT = 0x1000
MEM_RESERVE = 0x2000
PAGE_EXECUTE_READWRITE = 0x40

@router.post(r"/api/memory/read")
def read_memory(req, **kwargs):
    pid = req.get("pid")
    address = req.get("address")
    size = req.get("size", 4)
    
    if not pid or not address:
        raise APIError("pid and address are required")
        
    pid = int(pid)
    address = int(str(address), 16) if isinstance(address, str) and address.startswith("0x") else int(address)
    size = int(size)
    
    process_handle = kernel32.OpenProcess(PROCESS_ALL_ACCESS, False, pid)
    if not process_handle:
        raise APIError(f"Failed to open process. Error code: {kernel32.GetLastError()}")
        
    buffer = ctypes.create_string_buffer(size)
    bytes_read = ctypes.c_size_t(0)
    
    success = kernel32.ReadProcessMemory(process_handle, address, buffer, size, ctypes.byref(bytes_read))
    kernel32.CloseHandle(process_handle)
    
    if not success:
        raise APIError(f"Failed to read memory. Error code: {kernel32.GetLastError()}")
        
    import base64
    return {
        "address": hex(address),
        "size": bytes_read.value,
        "data_hex": buffer.raw[:bytes_read.value].hex(),
        "data_b64": base64.b64encode(buffer.raw[:bytes_read.value]).decode()
    }

@router.post(r"/api/memory/write")
def write_memory(req, **kwargs):
    pid = req.get("pid")
    address = req.get("address")
    data_hex = req.get("data_hex")
    
    if not pid or not address or not data_hex:
        raise APIError("pid, address, and data_hex are required")
        
    pid = int(pid)
    address = int(str(address), 16) if isinstance(address, str) and address.startswith("0x") else int(address)
    data = bytes.fromhex(data_hex)
    size = len(data)
    
    process_handle = kernel32.OpenProcess(PROCESS_ALL_ACCESS, False, pid)
    if not process_handle:
        raise APIError("Failed to open process")
        
    bytes_written = ctypes.c_size_t(0)
    success = kernel32.WriteProcessMemory(process_handle, address, data, size, ctypes.byref(bytes_written))
    kernel32.CloseHandle(process_handle)
    
    if not success:
        raise APIError(f"Failed to write memory. Error code: {kernel32.GetLastError()}")
        
    return {"success": True, "bytes_written": bytes_written.value}
