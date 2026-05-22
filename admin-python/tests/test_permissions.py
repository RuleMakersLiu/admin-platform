from app.services.permissions import has_permission, normalize_permission, parse_power, serialize_power


def test_normalize_permission_supports_legacy_underscore_keys():
    assert normalize_permission("system_admin_list") == "system:admin:list"
    assert normalize_permission("system:admin:list") == "system:admin:list"


def test_parse_power_expands_aliases_for_gateway_compatibility():
    permissions = parse_power('["system_admin_list", "system:group:edit"]')

    assert "system:admin:list" in permissions
    assert "system_admin_list" in permissions
    assert "system:group:edit" in permissions
    assert "system_group_edit" in permissions


def test_has_permission_accepts_colon_and_underscore_aliases():
    permissions = parse_power(["system_admin_list"])

    assert has_permission(permissions, "system:admin:list")
    assert has_permission(permissions, "system_admin_list")
    assert not has_permission(permissions, "system:admin:delete")


def test_serialize_power_keeps_canonical_colon_keys():
    assert serialize_power(["system_admin_list", "system:group:edit"]) == (
        '["system:admin:list", "system:group:edit"]'
    )
