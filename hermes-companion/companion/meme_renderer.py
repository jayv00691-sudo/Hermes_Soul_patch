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
    """Return a generic payload that other Hermes code can consume."""
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
