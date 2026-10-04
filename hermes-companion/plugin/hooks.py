"""Hermes companion hooks."""

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
    except Exception as exc:
        logger.warning("emotion 注入失败: %s", exc)

    try:
        roll_over_if_new_day()
        brief = format_today_brief()
        if brief:
            parts.append(f"[今日日程]\n{brief}")
    except Exception as exc:
        logger.warning("world_state 注入失败: %s", exc)

    try:
        pending = drain_pending()
        if pending:
            parts.append(f"[Companion主动消息]\n{pending}")
    except Exception as exc:
        logger.warning("pending 注入失败: %s", exc)

    try:
        manager = get_meme_manager()
        meme_block = manager.format_prompt_block()
        if meme_block:
            parts.append(meme_block)
    except Exception as exc:
        logger.warning("meme 注入失败: %s", exc)

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
    except Exception as exc:
        logger.warning("schedule_inference 失败: %s", exc)

    try:
        observe_interaction(
            user_message=user_message,
            assistant_response=assistant_response,
            conversation_history=conversation_history,
        )
    except Exception as exc:
        logger.warning("world_interaction 失败: %s", exc)

    try:
        if CURRENT_CTX is not None:
            emit_meme_payload(CURRENT_CTX, assistant_response)
    except Exception as exc:
        logger.warning("meme payload emit failed: %s", exc)


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
    except Exception as exc:
        logger.warning("emotion nudge 失败: %s", exc)


def on_session_start(*, session_id: str = "", platform: str = "", **kwargs) -> None:
    logger.info("companion: session_start sid=%s platform=%s", session_id, platform)


def register_hooks(ctx) -> None:
    set_runtime_ctx(ctx)
    ctx.register_hook("pre_llm_call", on_pre_llm_call)
    ctx.register_hook("post_llm_call", on_post_llm_call)
    ctx.register_hook("post_tool_call", on_post_tool_call)
    ctx.register_hook("on_session_start", on_session_start)
