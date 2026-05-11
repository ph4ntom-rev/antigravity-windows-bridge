import psutil
from server import router, APIError
import socket

@router.get(r"/api/network/connections")
def get_connections(req, **kwargs):
    pid = req.get("pid")
    results = []
    
    for conn in psutil.net_connections(kind='all'):
        if pid and str(conn.pid) != str(pid):
            continue
            
        laddr = f"{conn.laddr.ip}:{conn.laddr.port}" if conn.laddr else ""
        raddr = f"{conn.raddr.ip}:{conn.raddr.port}" if conn.raddr else ""
        
        results.append({
            "fd": conn.fd,
            "family": conn.family.name if hasattr(conn.family, 'name') else str(conn.family),
            "type": conn.type.name if hasattr(conn.type, 'name') else str(conn.type),
            "laddr": laddr,
            "raddr": raddr,
            "status": conn.status,
            "pid": conn.pid
        })
        
    return {"connections": results, "count": len(results)}
