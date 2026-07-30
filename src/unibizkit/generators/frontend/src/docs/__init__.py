from typing import Any, Dict, List

from ...context import Context


def _linked_pages(items: List[Dict[str, Any]]) -> List[str]:
    pages = []
    for item in items:
        if "docs" in item:
            pages.append(item["docs"])
        pages.extend(_linked_pages(item.get("children", [])))
    return pages


def linked_from_menu(ctx: Context) -> bool:
    """Whether the model links a documentation page from its menu.

    The pages are only generated when something points at them; an overlay may
    be the one adding the entry, so its 'add' ops count too.
    """
    items = list(ctx.presentation_config.get("menu") or [])
    for overlay in ctx.presentation_custom_config["overlays"]:
        items.extend(op["item"] for op in overlay.get("menu", []) if op["op"] == "add")
    return bool(_linked_pages(items))
