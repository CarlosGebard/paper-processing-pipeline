from __future__ import annotations

from typing import Any


def ref_index(ref: str) -> int:
    return int(ref.rsplit("/", 1)[-1])


def resolve_ref(doc: dict[str, Any], ref: str) -> dict[str, Any] | None:
    if ref.startswith("#/texts/"):
        return doc["texts"][ref_index(ref)]
    if ref.startswith("#/groups/"):
        return doc["groups"][ref_index(ref)]
    if ref.startswith("#/pictures/"):
        return doc["pictures"][ref_index(ref)]
    if ref.startswith("#/tables/"):
        return doc["tables"][ref_index(ref)]
    if ref.startswith("#/key_value_items/"):
        return doc["key_value_items"][ref_index(ref)]
    return None


def iter_body_refs(node: dict[str, Any]) -> list[str]:
    children = node.get("children", [])
    refs: list[str] = []
    if not isinstance(children, list):
        return refs

    for child in children:
        if not isinstance(child, dict):
            continue
        ref = child.get("$ref")
        if isinstance(ref, str):
            refs.append(ref)
    return refs


def is_furniture_item(item: dict[str, Any]) -> bool:
    return item.get("content_layer") == "furniture" or item.get("label") in {
        "page_header",
        "page_footer",
    }
