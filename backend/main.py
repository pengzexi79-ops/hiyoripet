# backend/main.py
# Frozen sidecar entry point used by the Tauri desktop application.
import ctypes
import multiprocessing
import os
import threading

import uvicorn

from config_manager import load_config
from server import app


def _watch_parent() -> None:
    """Exit the sidecar if the Tauri parent disappears, including crash cases."""
    raw_pid = os.environ.get("PET_PARENT_PID", "")
    if not raw_pid.isdigit() or os.name != "nt":
        return
    synchronize = 0x00100000
    infinite = 0xFFFFFFFF
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(synchronize, False, int(raw_pid))
    if not handle:
        return

    def wait_for_parent() -> None:
        try:
            kernel32.WaitForSingleObject(handle, infinite)
        finally:
            kernel32.CloseHandle(handle)
        os._exit(0)

    threading.Thread(target=wait_for_parent, name="pet-parent-watch", daemon=True).start()


def main() -> None:
    _watch_parent()
    config = load_config()
    uvicorn.run(
        app,
        host=config.server.host,
        port=config.server.port,
        log_level="warning",
        access_log=False,
        log_config=None,
    )


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
