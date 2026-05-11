# Antigravity Windows Bridge

A powerful local HTTP bridge granting AI agents (like Antigravity) advanced system-level capabilities on a Windows host via REST API.

## Features

- **System API**: Process enumeration, termination, hardware info, and raw WMI queries.
- **File System & Registry**: Read/write access to the Windows Registry (HKLM, HKCU, etc.).
- **UI Automation**: Screenshot capture, window enumeration, window focusing, and Win32 message boxes.
- **Low-level Input**: Hardware input synthesis (keyboard and mouse movement) via `SendInput`.
- **Memory Manipulation**: Read and write memory of external processes (useful for game hacking, reverse engineering).
- **Network Dump**: Retrieve active TCP/UDP connections mapped to PIDs.
- **RCE Endpoint**: Execute arbitrary Python scripts directly on the host system.

## Setup

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Run the bridge:
   ```bash
   python run_bridge.py
   ```

The server will start on `http://127.0.0.1:13371`.

## AI Integration
Check out `ai_instruction.json` for a ready-to-use LLM system prompt containing all endpoint schemas and usage instructions.

## License
MIT
