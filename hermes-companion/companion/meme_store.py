import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
DEFAULT_PACK_ID = "builtin-default"


def _safe_category_name(raw: str) -> str:
    name = str(raw or "").strip()
    if not name or name in {".", ".."}:
        raise ValueError("分类名不能为空")
    if "/" in name or "\\" in name:
        raise ValueError("分类名不能包含路径分隔符")
    if Path(name).name != name:
        raise ValueError("分类名包含非法路径")
    return name


class MemeManager:
    """轻量版表情包管理器：实现 AstrBot 式的分类 + 存储 + 去重。"""

    def __init__(self, hermes_home: str | os.PathLike[str] | None = None):
        base = (
            hermes_home
            if hermes_home is not None
            else os.environ.get("HERMES_HOME", str(Path.home() / ".hermes"))
        )
        self.hermes_home = Path(base).expanduser().resolve()
        self.root = self.hermes_home / "companion" / "memes"
        self.registry_path = self.hermes_home / "companion" / "meme_registry.json"
        self.root.mkdir(parents=True, exist_ok=True)
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_registry()

    def _load_registry(self) -> dict:
        if not self.registry_path.exists():
            self._ensure_registry()
        try:
            data = json.loads(self.registry_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception:
            pass
        return {"schema_version": 1, "installed_packs": [], "default_pack_id": DEFAULT_PACK_ID}

    def _save_registry(self, payload: dict) -> None:
        self.registry_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _ensure_registry(self) -> None:
        payload = self._load_registry()
        if not payload.get("installed_packs"):
            payload = {
                "schema_version": 1,
                "installed_packs": [
                    {
                        "id": DEFAULT_PACK_ID,
                        "name": "Default Hermes Meme Pack",
                        "version": "1.0.0",
                        "enabled": True,
                        "installed_at": datetime.now(timezone.utc).isoformat(),
                    }
                ],
                "default_pack_id": DEFAULT_PACK_ID,
            }
        elif not payload.get("default_pack_id"):
            payload["default_pack_id"] = DEFAULT_PACK_ID
        self._save_registry(payload)
        self.ensure_pack(DEFAULT_PACK_ID)

    @property
    def default_pack_id(self) -> str:
        registry = self._load_registry()
        pack_id = str(registry.get("default_pack_id") or DEFAULT_PACK_ID).strip()
        if not pack_id:
            pack_id = DEFAULT_PACK_ID
        self.ensure_pack(pack_id)
        return pack_id

    def ensure_pack(self, pack_id: str) -> Path:
        pack_name = str(pack_id or DEFAULT_PACK_ID).strip() or DEFAULT_PACK_ID
        pack_dir = self.root / pack_name
        pack_dir.mkdir(parents=True, exist_ok=True)
        memes_dir = pack_dir / "memes"
        memes_dir.mkdir(parents=True, exist_ok=True)
        return memes_dir

    def get_default_memes_dir(self) -> Path:
        return self.ensure_pack(self.default_pack_id)

    def scan_categories(self, pack_id: str | None = None) -> dict[str, list[str]]:
        memes_dir = self.ensure_pack(pack_id or self.default_pack_id)
        result: dict[str, list[str]] = {}
        if not memes_dir.exists():
            return result
        for child in sorted(memes_dir.iterdir(), key=lambda p: p.name):
            if not child.is_dir():
                continue
            images = sorted(
                p.name
                for p in child.iterdir()
                if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
            )
            if images:
                result[child.name] = images
        return result

    def get_meme_path(self, category: str, filename: str) -> Path:
        category_name = _safe_category_name(category)
        memes_dir = self.get_default_memes_dir()
        safe_filename = Path(str(filename or "")).name
        path = (memes_dir / category_name / safe_filename).resolve()
        try:
            path.relative_to(memes_dir.resolve())
        except ValueError as exc:
            raise ValueError(f"非法表情路径: {category_name}/{safe_filename}") from exc
        return path

    @staticmethod
    def _hash_bytes(content: bytes) -> str:
        return hashlib.sha256(content).hexdigest()

    def _unique_path(self, category_dir: Path, filename: str) -> Path:
        base = Path(filename)
        if not base.name:
            base = Path("meme.png")
        candidate = category_dir / base.name
        if not candidate.exists():
            return candidate
        stem = base.stem
        suffix = base.suffix.lower() or ".png"
        index = 1
        while True:
            new_path = category_dir / f"{stem}_{index}{suffix}"
            if not new_path.exists():
                return new_path
            index += 1

    def add_meme(self, category: str, filename: str, content: bytes) -> dict:
        category_name = _safe_category_name(category)
        memes_dir = self.get_default_memes_dir()
        category_dir = (memes_dir / category_name).resolve()
        category_dir.mkdir(parents=True, exist_ok=True)
        try:
            category_dir.relative_to(memes_dir.resolve())
        except ValueError as exc:
            raise ValueError(f"分类目录越界: {category_name}") from exc

        if not filename:
            filename = "meme.png"
        file_name = Path(str(filename)).name
        if not file_name:
            file_name = "meme.png"
        suffix = Path(file_name).suffix.lower()
        if suffix not in IMAGE_EXTENSIONS:
            raise ValueError(f"不支持的图片扩展名: {suffix or '空'}")

        content_hash = self._hash_bytes(content)
        for item in category_dir.iterdir():
            if not item.is_file() or item.suffix.lower() not in IMAGE_EXTENSIONS:
                continue
            try:
                if self._hash_bytes(item.read_bytes()) == content_hash:
                    raise ValueError(f"同一分类中已存在相同内容的文件: {item.name}")
            except Exception:
                continue

        destination = self._unique_path(category_dir, file_name)
        destination.write_bytes(content)
        return {"category": category_name, "filename": destination.name, "path": str(destination)}

    def remove_meme(self, category: str, filename: str) -> bool:
        try:
            path = self.get_meme_path(category, filename)
        except ValueError:
            return False
        if not path.exists() or not path.is_file():
            return False
        path.unlink()
        return True

    def format_prompt_block(self) -> str:
        categories = self.scan_categories()
        if not categories:
            return ""
        lines = ["[表情包可用分类]"]
        for category, files in sorted(categories.items()):
            preview = ", ".join(files[:3]) if files else "无"
            lines.append(f"- {category}: {len(files)} 张（示例: {preview}）")
        lines.append("需要插入图片时，请在回复末尾用 &&分类名:文件名&& 标记，例如 &&happy:smile.png&&")
        return "\n".join(lines)

    def extract_markers(self, text: str) -> list[tuple[str, str]]:
        if not text:
            return []
        return re.findall(r"&&([A-Za-z0-9_\-]+):([A-Za-z0-9_.\-]+)&&", text)


_meme_manager: MemeManager | None = None


def get_meme_manager() -> MemeManager:
    global _meme_manager
    if _meme_manager is None:
        _meme_manager = MemeManager()
    return _meme_manager


__all__ = ["MemeManager", "IMAGE_EXTENSIONS", "get_meme_manager", "DEFAULT_PACK_ID"]


"""
A small, Hermes-friendly renderer for meme markers.
It keeps the meme system safe and platform-agnostic even when the exact Hermes
message API is not known at runtime.
"""

from __future__ import annotations

import re
from pathlib import Path

from companion.meme_store import get_meme_manager


def strip_meme_markers(text: str) -> str:
    if not text:
        return ""
    return re.sub(r"&&[A-Za-z0-9_\-]+:[A-Za-z0-9_.\-]+&&", "", text).strip()


def resolve_markers(text: str) -> list[dict]:
    manager = get_meme_manager()
    markers = []
    for category, filename in manager.extract_markers(text):
        try:
            path = manager.get_meme_path(category, filename)
            if path.exists():
                markers.append({"category": category, "filename": filename, "path": str(path)})
        except Exception:
            continue
    return markers


def render_image_payload_for_hermes(ctx, text: str) -> dict:
    """Return a generic payload that other Hermes code can consume.

    Supported patterns:
      - ctx.send_image(file_path)
      - ctx.send_message(text)
      - ctx.inject_message(text)
      - ctx.add_image(...) or ctx.images.append(...)
    """
    markers = resolve_markers(text)
    if not markers:
        return {"text": strip_meme_markers(text), "images": []}

    payload = {"text": strip_meme_markers(text), "images": []}
    for item in markers:
        payload["images"].append({
            "category": item["category"],
            "filename": item["filename"],
            "path": item["path"],
        })
    return payload


def emit_meme_payload(ctx, text: str) -> bool:
    payload = render_image_payload_for_hermes(ctx, text)
    if not payload["images"]:
        return False

    if ctx is None:
        return False

    if hasattr(ctx, "send_image"):
        for image in payload["images"]:
            try:
                ctx.send_image(image["path"])
            except Exception:
                pass
        return True

    if hasattr(ctx, "send_message"):
        try:
            text_out = payload["text"] or "[表情]"
            if text_out:
                ctx.send_message(text_out)
            for image in payload["images"]:
                try:
                    ctx.send_image(image["path"])
                except Exception:
                    pass
            return True
        except Exception:
            pass

    if hasattr(ctx, "inject_message"):
        try:
            if payload["text"]:
                ctx.inject_message(payload["text"], role="user")
            for image in payload["images"]:
                try:
                    ctx.inject_message(f"![{image['filename']}]({image['path']})", role="user")
                except Exception:
                    pass
            return True
        except Exception:
            pass

    if hasattr(ctx, "images") and isinstance(ctx.images, list):
        for image in payload["images"]:
            ctx.images.append(image["path"])
        return True

    return False


__all__ = ["strip_meme_markers", "resolve_markers", "render_image_payload_for_hermes", "emit_meme_payload"]


"""
Hermes Companion 插件注册入口（v0.2 完整版：时间 + 情感 + 主动消息 + v0.4 推断 + 表情包管理）。

Hermes 自动发现 ~/.hermes/plugins/hermes-companion/ 并调用 register(ctx)。
"""

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
    """Return True when Hermes cron is already responsible for Telegram heartbeat."""
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
        except Exception as e:
            logger.warning("inject_message error: %s", e)
        if ok:
            logger.info("heartbeat injected message")
            return
        try:
            enqueue(msg)
            logger.info("heartbeat fallback to queue: %s", queue_path())
        except Exception as e:
            logger.warning("enqueue fallback failed: %s", e)

    def _loop() -> None:
        logger.info("companion heartbeat thread started (interval=%ds)", interval)
        time.sleep(min(interval, 30))
        while True:
            try:
                for msg in collect_heartbeat_messages():
                    _emit(msg)
            except Exception as e:
                logger.warning("heartbeat tick error: %s", e)
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
    except Exception as e:
        logger.warning("meme manager init failed: %s", e)

    try:
        register_tools(ctx)
    except Exception as e:
        logger.warning("agenda 工具注册失败: %s", e)

    try:
        from companion.world_state import start_daily_archiver

        start_daily_archiver()
    except Exception as e:
        logger.warning("daily archiver 启动失败: %s", e)

    if _heartbeat_enabled():
        try:
            if _cron_delivery_enabled():
                logger.info("companion heartbeat thread skipped: cron delivery is configured")
            else:
                _start_heartbeat_thread(ctx)
        except Exception as e:
            logger.warning("heartbeat 线程启动失败: %s", e)


"""
Companion slash commands.

   /mood              显示当前情感状态
   /mood-set ...      手动设置情感状态（调试）
   /heartbeat         显示主动消息队列状态 + 控制 / 触发心跳
   /agenda            显示今日事件列表（世界状态模拟器，见 core.md §4.8）
   /agenda-add ...    添加事件
   /agenda-done <id>  标记事件完成
   /agenda-ambient    追加一条环境事件
   /recall <date>     调取某日归档摘要
   /meme-list         列出当前表情包分类和图片
   /meme-add <cat> <url> 下载并加入表情包
   /meme-del <cat> <name> 删除表情

handler 签名约定（hermes_cli/plugins.py）：fn(raw_args: str, **kw) -> str | None
"""

from __future__ import annotations

import logging
import shlex
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen

from companion.emotion_state import load_emotion_state, update_emotion
from companion.heartbeat import enqueue, queue_path
from companion.meme_store import get_meme_manager
from companion.world_state import (
    add_ambient,
    add_event,
    list_today,
    mark_done,
    recall,
)

logger = logging.getLogger(__name__)


def cmd_mood_show(raw_args: str = "", **kwargs) -> str:
    return load_emotion_state()


def cmd_mood_set(raw_args: str = "", **kwargs) -> str:
    """用法: /mood-set <valence> <arousal> <dominant> <note>
    例:   /mood-set 0.6 0.3 content 完成了一个困难问题
    """
    parts = (raw_args or "").strip().split(None, 3)
    if len(parts) < 4:
        return "用法: /mood-set <valence:-1~1> <arousal:0~1> <dominant> <note>"
    try:
        valence = float(parts[0])
        arousal = float(parts[1])
    except ValueError:
        return "valence / arousal 必须是数字"
    dominant = parts[2].strip()
    note = parts[3].strip().strip("'\"")
    state = update_emotion(valence, arousal, dominant, note)
    return (
        "✓ 情感状态已更新：\n"
        f"  valence={state['valence']:+.2f} "
        f"arousal={state['arousal']:.2f} "
        f"dominant={state['dominant']}"
    )


def cmd_heartbeat(raw_args: str = "", **kwargs) -> str:
    """无参=显示队列；'push <msg>' = 手动入队一条主动消息（调试用）。"""
    args = (raw_args or "").strip()
    if args.startswith("push "):
        msg = args[5:].strip()
        if not msg:
            return "用法: /heartbeat push <消息正文>"
        enqueue(msg)
        return f"✓ 已入队：{msg[:60]}"

    qp = queue_path()
    if not qp.exists() or qp.stat().st_size == 0:
        return f"队列为空（{qp}）。"
    text = qp.read_text(encoding="utf-8").strip()
    n = len([ln for ln in text.splitlines() if ln.strip()])
    return f"队列中有 {n} 条待注入消息（{qp}）。"


def cmd_meme_list(raw_args: str = "", **_kw) -> str:
    try:
        manager = get_meme_manager()
        categories = manager.scan_categories()
        if not categories:
            return "当前表情包为空。可用 /meme-add <category> <url> 导入图片。"
        lines = ["# 表情包列表"]
        for category, files in sorted(categories.items()):
            lines.append(f"- {category}: {len(files)} 张")
            for file_name in files[:5]:
                lines.append(f"    · {file_name}")
            if len(files) > 5:
                lines.append(f"    · ... 还有 {len(files)-5} 张")
        return "\n".join(lines)
    except Exception as exc:  # pragma: no cover
        logger.warning("meme-list failed: %s", exc)
        return f"读取表情包失败：{exc}"


def cmd_meme_add(raw_args: str = "", **_kw) -> str:
    parts = shlex.split(raw_args or "")
    if len(parts) < 2:
        return "用法: /meme-add <category> <image_url>"
    category, url = parts[0], parts[1]
    try:
        req = Request(url, headers={"User-Agent": "HermesCompanion/1.0"})
        with urlopen(req, timeout=20) as resp:
            payload = resp.read()
        if not payload:
            return "下载失败：空内容"
        file_name = Path(url.split("?", 1)[0]).name or "meme.png"
        manager = get_meme_manager()
        result = manager.add_meme(category, file_name, payload)
        return f"✓ 已添加表情：{result['category']}/{result['filename']}"
    except Exception as exc:  # pragma: no cover
        logger.warning("meme-add failed: %s", exc)
        return f"添加失败：{exc}"


def cmd_meme_del(raw_args: str = "", **_kw) -> str:
    parts = shlex.split(raw_args or "")
    if len(parts) < 2:
        return "用法: /meme-del <category> <filename>"
    category, filename = parts[0], parts[1]
    try:
        manager = get_meme_manager()
        ok = manager.remove_meme(category, filename)
        return "✓ 已删除表情" if ok else f"未找到 {category}/{filename}"
    except Exception as exc:  # pragma: no cover
        logger.warning("meme-del failed: %s", exc)
        return f"删除失败：{exc}"


def register_commands(ctx) -> None:
    ctx.register_command("mood", cmd_mood_show, description="显示当前情感状态")
    ctx.register_command(
        "mood-set",
        cmd_mood_set,
        description="手动设置情感状态（调试）",
        args_hint="<valence> <arousal> <dominant> <note>",
    )
    ctx.register_command(
        "heartbeat",
        cmd_heartbeat,
        description="显示/控制 companion 主动消息队列",
        args_hint="[push <msg>]",
    )
    ctx.register_command("agenda", cmd_agenda, description="显示今日事件列表")
    ctx.register_command(
        "agenda-add",
        cmd_agenda_add,
        description="添加事件",
        args_hint="<start> <end> <title> [kind]",
    )
    ctx.register_command(
        "agenda-done",
        cmd_agenda_done,
        description="标记事件完成",
        args_hint="<event_id>",
    )
    ctx.register_command(
        "agenda-ambient",
        cmd_agenda_ambient,
        description="追加一条环境事件",
        args_hint="<note>",
    )
    ctx.register_command(
        "recall",
        cmd_recall,
        description="读取某日归档摘要",
        args_hint="<YYYY-MM-DD>",
    )
    ctx.register_command("meme-list", cmd_meme_list, description="列出当前表情包分类和图片")
    ctx.register_command(
        "meme-add",
        cmd_meme_add,
        description="下载并加入表情包",
        args_hint="<category> <image_url>",
    )
    ctx.register_command(
        "meme-del",
        cmd_meme_del,
        description="删除指定表情",
        args_hint="<category> <filename>",
    )


# ---------------- /agenda 系列 ----------------


def cmd_agenda(raw_args: str = "", **_kw) -> str:
    """显示今日事件列表（人类可读）。"""
    doc = list_today()
    schedule = doc.get("schedule", [])
    ambient = doc.get("ambient", [])
    lines = [f"# 今日日程（{doc.get('date', '?')}）"]

    if not schedule:
        lines.append("（无日程）")
    else:
        for ev in schedule:
            marker = {
                "done": "✓",
                "missed": "✗",
                "pending": "·",
            }.get(ev.get("status", "?"), "?")
            start = ev.get("start", "")
            end = ev.get("end", "")
            clock = start[-5:] if "T" in start else start
            end_clock = end[-5:] if "T" in end else end
            time_seg = f"{clock}–{end_clock}" if end_clock else clock
            lines.append(
                f"  {marker} [{ev.get('id', '?')}] {time_seg} "
                f"{ev.get('title', '(未命名)')}  «{ev.get('kind', 'self')}»"
            )

    if ambient:
        lines.append("")
        lines.append("# 环境")
        for a in ambient[-5:]:
            t = a.get("time", "")
            clock = t[-5:] if "T" in t else t
            lines.append(f"  · {clock} {a.get('note', '')}")
    return "\n".join(lines)


def cmd_agenda_add(raw_args: str = "", **_kw) -> str:
    """
    /agenda-add <start> <end> <title> [kind]

    时间格式：ISO（YYYY-MM-DDTHH:MM）或 HH:MM（自动补今天日期）。
    end 可填 "-" 表示不设结束时间。
    title 含空格请用引号包裹。kind 可选 self / interaction / ambient（默认 self）。
    """
    try:
        parts = shlex.split(raw_args or "")
    except ValueError as e:
        return f"参数解析失败：{e}"
    if len(parts) < 3:
        return (
            "用法: /agenda-add <start> <end> <title> [kind]\n"
            "示例: /agenda-add 14:00 15:00 \"和 Jifeng 讨论\" interaction"
        )

    start = _normalize_time(parts[0])
    end_raw = parts[1]
    end = "" if end_raw in ("-", "_", "none", "None") else _normalize_time(end_raw)
    title = parts[2]
    kind = parts[3] if len(parts) >= 4 else "self"

    try:
        eid = add_event(start=start, end=end, title=title, kind=kind)
    except ValueError as e:
        return f"参数错误：{e}"
    except Exception as e:
        logger.warning("agenda-add failed: %s", e)
        return f"添加失败：{e}"
    return f"✓ 已添加事件 [{eid}] {title}"


def cmd_agenda_done(raw_args: str = "", **_kw) -> str:
    ev_id = (raw_args or "").strip()
    if not ev_id:
        return "用法: /agenda-done <event_id>"
    ok = mark_done(ev_id)
    return f"✓ 已标记 [{ev_id}] 完成" if ok else f"未找到事件 [{ev_id}]"


def cmd_agenda_ambient(raw_args: str = "", **_kw) -> str:
    note = (raw_args or "").strip()
    if not note:
        return "用法: /agenda-ambient <note>"
    try:
        add_ambient(note)
    except ValueError as e:
        return f"参数错误：{e}"
    return f"✓ 已记录环境事件：{note}"


def cmd_recall(raw_args: str = "", **_kw) -> str:
    date = (raw_args or "").strip()
    if not date:
        return "用法: /recall <YYYY-MM-DD>"
    return recall(date)


def _normalize_time(s: str) -> str:
    """HH:MM → 今天 ISO；其它原样返回让 add_event 校验。"""
    s = s.strip()
    if "T" in s or len(s) >= 10:
        return s
    today = datetime.now().strftime("%Y-%m-%d")
    if len(s) in (5, 8) and s[2] == ":":
        return f"{today}T{s[:5]}"
    return s


"""
Hermes Companion hooks.

- pre_llm_call: 注入时间、状态、待处理消息、表情包分类
- post_llm_call: 解析 &&category:file&& 并尝试发送图片
- post_tool_call: 情感下调
"""

from __future__ import annotations

import json
import logging

from companion.emotion_inference import schedule_inference
from companion.emotion_state import load_emotion_state, nudge_emotion
from companion.heartbeat import drain_pending
from companion.meme_renderer import emit_meme_payload
from companion.meme_store import get_meme_manager
from companion.time_context import format_current_time
from companion.world_interaction import observe_interaction
from companion.world_state import format_today_brief, roll_over_if_new_day

logger = logging.getLogger(__name__)
CURRENT_CTX = None


def set_runtime_ctx(ctx) -> None:
    global CURRENT_CTX
    CURRENT_CTX = ctx


def on_pre_llm_call(
    *,
    session_id: str = "",
    user_message: str = "",
    conversation_history=None,
    is_first_turn: bool = False,
    model: str = "",
    platform: str = "",
    sender_id: str = "",
    **kwargs,
) -> dict:
    parts: list[str] = [format_current_time()]

    try:
        parts.append(f"[Companion状态]\n{load_emotion_state()}")
    except Exception as e:
        logger.warning("emotion 注入失败: %s", e)

    try:
        roll_over_if_new_day()
        brief = format_today_brief()
        if brief:
            parts.append(f"[今日日程]\n{brief}")
    except Exception as e:
        logger.warning("world_state 注入失败: %s", e)

    try:
        pending = drain_pending()
        if pending:
            parts.append(f"[Companion主动消息]\n{pending}")
    except Exception as e:
        logger.warning("pending 注入失败: %s", e)

    try:
        manager = get_meme_manager()
        meme_block = manager.format_prompt_block()
        if meme_block:
            parts.append(meme_block)
    except Exception as e:
        logger.warning("meme 注入失败: %s", e)

    return {"context": "\n\n".join(parts)}


def on_post_llm_call(
    *,
    session_id: str = "",
    user_message: str = "",
    assistant_response: str = "",
    conversation_history=None,
    model: str = "",
    platform: str = "",
    **kwargs,
) -> None:
    try:
        schedule_inference(
            user_message=user_message,
            assistant_response=assistant_response,
            conversation_history=conversation_history,
        )
    except Exception as e:
        logger.warning("schedule_inference 失败: %s", e)

    try:
        observe_interaction(
            user_message=user_message,
            assistant_response=assistant_response,
            conversation_history=conversation_history,
        )
    except Exception as e:
        logger.warning("world_interaction 失败: %s", e)

    try:
        if CURRENT_CTX is not None:
            emit_meme_payload(CURRENT_CTX, assistant_response)
    except Exception as e:
        logger.warning("meme payload emit failed: %s", e)


def _result_has_error(result) -> bool:
    if result is None:
        return False
    if isinstance(result, dict):
        return bool(result.get("error") or result.get("is_error"))
    if isinstance(result, str):
        s = result.lstrip()
        if s.startswith("{"):
            try:
                obj = json.loads(s)
                if isinstance(obj, dict):
                    return bool(obj.get("error") or obj.get("is_error"))
            except Exception:
                pass
        return '"error"' in s or '"is_error": true' in s
    return False


def on_post_tool_call(
    *,
    tool_name: str = "",
    args=None,
    result=None,
    session_id: str = "",
    duration_ms: int = 0,
    task_id: str = "",
    tool_call_id: str = "",
    **kwargs,
) -> None:
    if not _result_has_error(result):
        return
    try:
        nudge_emotion(
            valence_delta=-0.1,
            arousal_delta=0.05,
            confidence_delta=-0.05,
            dominant="mildly_frustrated",
            note=f"工具 {tool_name} 执行失败。",
            source="tool_failure",
        )
    except Exception as e:
        logger.warning("emotion nudge 失败: %s", e)


def on_session_start(*, session_id: str = "", platform: str = "", **kwargs) -> None:
    logger.info("companion: session_start sid=%s platform=%s", session_id, platform)


def register_hooks(ctx) -> None:
    set_runtime_ctx(ctx)
    ctx.register_hook("pre_llm_call", on_pre_llm_call)
    ctx.register_hook("post_llm_call", on_post_llm_call)
    ctx.register_hook("post_tool_call", on_post_tool_call)
    ctx.register_hook("on_session_start", on_session_start)


"""
This is a compact mime manager comment; no-op for runtime.
"""

__all__ = [
    "MemeManager",
    "IMAGE_EXTENSIONS",
    "get_meme_manager",
    "DEFAULT_PACK_ID",
    "strip_meme_markers",
    "resolve_markers",
    "render_image_payload_for_hermes",
    "emit_meme_payload",
]

