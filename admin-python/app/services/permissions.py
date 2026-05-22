"""Permission helpers shared by auth and system APIs.

The project stores role permissions in sys_admin_group.power as a JSON array.
These helpers keep backward compatibility with the old underscore keys while
also supporting the common admin-system convention: module:resource:action.
"""
import json
from typing import Any, Iterable, List, Sequence, Set


SUPER_PERMISSION = "*"


def normalize_permission(permission: str) -> str:
    """Normalize a permission key to module:resource:action when possible."""
    value = (permission or "").strip()
    if not value or value == SUPER_PERMISSION:
        return value
    if ":" in value:
        return value.lower()
    parts = [part for part in value.replace("-", "_").split("_") if part]
    if len(parts) >= 3:
        return ":".join(parts).lower()
    return value.lower()


def permission_aliases(permission: str) -> Set[str]:
    """Return colon and underscore aliases for compatibility with old data."""
    normalized = normalize_permission(permission)
    aliases = {permission.strip(), normalized}
    if normalized and normalized != SUPER_PERMISSION:
        aliases.add(normalized.replace(":", "_"))
    return {item for item in aliases if item}


def parse_power(power: Any) -> List[str]:
    """Parse sys_admin_group.power into a stable, deduplicated list."""
    if power is None:
        return []
    if isinstance(power, str):
        text = power.strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = [part.strip() for part in text.split(",")]
    elif isinstance(power, Sequence) and not isinstance(power, (bytes, bytearray)):
        parsed = list(power)
    else:
        parsed = [power]

    result: List[str] = []
    seen: Set[str] = set()
    for item in parsed:
        value = str(item).strip()
        if not value:
            continue
        normalized = normalize_permission(value)
        for alias in permission_aliases(normalized):
            if alias not in seen:
                result.append(alias)
                seen.add(alias)
    return result


def serialize_power(permissions: Iterable[str]) -> str:
    """Serialize permissions in the canonical colon-key form."""
    result: List[str] = []
    seen: Set[str] = set()
    for item in permissions:
        normalized = normalize_permission(str(item))
        if normalized and normalized not in seen:
            result.append(normalized)
            seen.add(normalized)
    return json.dumps(result, ensure_ascii=False)


def has_permission(permissions: Iterable[str], required: str, is_super: bool = False) -> bool:
    """Check a required permission against canonical and legacy aliases."""
    if is_super:
        return True
    granted = set()
    for permission in permissions:
        granted.update(permission_aliases(permission))
    if SUPER_PERMISSION in granted:
        return True
    return bool(granted.intersection(permission_aliases(required)))


def filter_menu_nodes(menus: Sequence[Any], permissions: Iterable[str], is_super: bool = False) -> List[Any]:
    """Keep visible directories only when they have visible children."""
    allowed: List[Any] = []
    for menu in menus:
        permission = getattr(menu, "permission", None)
        menu_type = getattr(menu, "menu_type", None)
        is_button = menu_type == 3 or menu_type == 2 and not getattr(menu, "path", None)
        if is_button:
            continue
        if is_super or not permission or has_permission(permissions, permission):
            allowed.append(menu)
    return allowed
