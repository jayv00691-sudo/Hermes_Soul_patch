"""Hermes companion plugin entrypoint with meme support."""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
from pathlib import Path

_repo_root = Path(__file__).resolve().parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from .commands import register_commands
from .hooks import register_hooks
from .tools import register_tools

logger = logging.getLogger(__name__)


def _heartbeat_enabled() -> bool:
    return os.environ.get("HERMES_COMPANION_HEARTBEAT", "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def _truthy_env(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def _cron_delivery_enabled() -> bool:
    if _truthy_env("HERMES_COMPANION_HEARTBEAT_FORCE"):
        return False

    hermes_home = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
    jobs_path = hermes_home / "cron" / "jobs.json"
    try:
        data = json.loads(jobs_path.read_text(encoding="utf-8"))
    except Exception:
        return False

    for job in data.get("jobs", []):
        if not isinstance(job, dict) or not job.get("enabled", True):
            continue
        script = str(job.get("script") or "")
        name = str(job.get("name") or "")
        deliver = str(job.get("deliver") or "local").strip().lower()
        if deliver and deliver != "local" and (
            script.endswith("companion_heartbeat.py") or name == "companion-heartbeat"
        ):
            return True
    return False


def _start_heartbeat_thread(ctx) -> None:
    from companion.heartbeat import CHECK_INTERVAL, collect_heartbeat_messages, enqueue, queue_path

    interval = CHECK_INTERVAL

    def _emit(msg: str) -> None:
        ok = False
        try:
            ok = bool(ctx.inject_message(msg, role="user"))
        except Exception as exc:
            logger.warning("inject_message error: %s", exc)
        if ok:
            logger.info("heartbeat injected message")
            return
        try:
            enqueue(msg)
            logger.info("heartbeat fallback to queue: %s", queue_path())
        except Exception as exc:
            logger.warning("enqueue fallback failed: %s", exc)

    def _loop() -> None:
        logger.info("companion heartbeat thread started (interval=%ds)", interval)
        time.sleep(min(interval, 30))
        while True:
            try:
                for msg in collect_heartbeat_messages():
                    _emit(msg)
            except Exception as exc:
                logger.warning("heartbeat tick error: %s", exc)
            time.sleep(interval)

    t = threading.Thread(target=_loop, daemon=True, name="companion-heartbeat")
    t.start()


def register(ctx) -> None:
    register_hooks(ctx)
    register_commands(ctx)

    try:
        from companion.meme_store import get_meme_manager
        manager = get_meme_manager()
        manager.ensure_pack(manager.default_pack_id)
        logger.info("meme manager ready: %s", manager.get_default_memes_dir())
    except Exception as exc:
        logger.warning("meme manager init failed: %s", exc)

    try:
        register_tools(ctx)
    except Exception as exc:
        logger.warning("agenda 工具注册失败: %s", exc)

    try:
        from companion.world_state import start_daily_archiver
        start_daily_archiver()
    except Exception as exc:
        logger.warning("daily archiver 启动失败: %s", exc)

    if _heartbeat_enabled():
        try:
            if _cron_delivery_enabled():
                logger.info("companion heartbeat thread skipped: cron delivery is configured")
            else:
                _start_heartbeat_thread(ctx)
        except Exception as exc:
            logger.warning("heartbeat 线程启动失败: %s", exc)
