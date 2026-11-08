"""启动阶段埋点：仅当环境变量 MIKAN_DEBUG_STARTUP=1 时写入 data/logs/startup_trace.log。

正常运行时该函数第一行就 return，不会产生任何 IO 开销。
"""

from __future__ import annotations

import os
import time


def trace(stage: str) -> None:
    if os.environ.get("MIKAN_DEBUG_STARTUP") != "1":
        return
    try:
        from .config import LOG_DIR

        LOG_DIR.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%H:%M:%S") + f".{int(time.time() * 1000) % 1000:03d}"
        with open(LOG_DIR / "startup_trace.log", "a", encoding="utf-8") as handle:
            handle.write(f"{stamp}  {stage}\n")
    except Exception:  # noqa: BLE001 - 调试埋点失败不影响启动
        pass
