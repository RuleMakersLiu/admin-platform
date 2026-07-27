"""Tests for eval golden case model + schema + storage helpers (offline)."""
import pytest

from app.models.eval_golden_case import EvalGoldenCase
from app.schemas.eval_golden import (
    GoldenCaseCreate,
    GoldenCaseUpdate,
    from_storage,
    to_storage,
)


def test_model_construction():
    c = EvalGoldenCase(
        tenant_id=1, name="登录页", category="frontend",
        input_spec="{}", expected_criteria="[]", enabled=0,
    )
    assert c.tenant_id == 1
    assert c.name == "登录页"
    assert c.category == "frontend"
    assert c.enabled == 0


def test_create_schema_requires_name():
    with pytest.raises(Exception):
        GoldenCaseCreate(input_spec="x", expected_criteria="y")  # name 缺失


def test_create_schema_accepts_structured_input():
    req = GoldenCaseCreate(
        name="商品列表页",
        input_spec={"requirement": "做一个可分页可搜索的商品列表"},
        expected_criteria=["有分页控件", "支持关键词搜索", "响应式"],
    )
    assert req.input_spec["requirement"].startswith("做一个")
    assert "有分页控件" in req.expected_criteria


def test_storage_roundtrip_dict():
    obj = {"a": 1, "b": [1, 2, {"c": "x"}]}
    assert from_storage(to_storage(obj)) == obj


def test_storage_roundtrip_list():
    lst = ["有分页", "可搜索", {"k": "v"}]
    assert from_storage(to_storage(lst)) == lst


def test_storage_plain_string_passthrough():
    s = "实现一个登录页面，支持手机号验证码登录"
    stored = to_storage(s)
    assert stored == s  # 字符串原样存
    assert from_storage(stored) == s  # 非 JSON 文本原样返回


def test_storage_none():
    assert from_storage(None) is None


def test_update_schema_exclude_unset():
    u = GoldenCaseUpdate(name="新名字")
    assert u.model_dump(exclude_unset=True) == {"name": "新名字"}


def test_eval_run_model_construction():
    from app.models.eval_run import EvalRun

    r = EvalRun(tenant_id=1, golden_case_id=5, pipeline_id="pipe_x", status="running")
    assert r.tenant_id == 1
    assert r.golden_case_id == 5
    assert r.pipeline_id == "pipe_x"
    assert r.status == "running"
