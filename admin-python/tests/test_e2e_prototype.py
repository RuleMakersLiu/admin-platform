"""Phase 2: prototype 阶段 E2E 浏览器断言的离线单测。

覆盖：
- e2e_expectations.derive_e2e_expectations：关键词→期望控件（登录/列表/表单/空）
- flow_manager._e2e_browser_check_issues：fail-open（harness 故障/异常不阻塞）+ issue 透传

真实浏览器 DOM 断言由端到端流水线验证，此处不打真实 chromium。
"""
import asyncio

from app.ai import e2e_expectations, flow_manager


def _run(coro):
    return asyncio.run(coro)


# ---------- 期望派生（启发式） ----------

def test_derive_login_expectations():
    exps = e2e_expectations.derive_e2e_expectations("生成一个登录页")
    kinds = {e["kind"] for e in exps}
    assert "password" in kinds, exps
    assert any(e["kind"] == "button_text" for e in exps), exps


def test_derive_register_expectations():
    exps = e2e_expectations.derive_e2e_expectations("用户注册页面")
    kinds = {e["kind"] for e in exps}
    assert "password" in kinds, exps


def test_derive_list_expectations():
    exps = e2e_expectations.derive_e2e_expectations("商品列表查询管理")
    assert any(e["kind"] == "table" for e in exps), exps
    assert any(e["kind"] == "button_text" for e in exps), exps


def test_derive_form_expectations():
    exps = e2e_expectations.derive_e2e_expectations("后台增加团购配置")
    kinds = {e["kind"] for e in exps}
    assert "has_input" in kinds, exps


def test_derive_add_button():
    exps = e2e_expectations.derive_e2e_expectations("用户新增管理")
    btns = [e for e in exps if e["kind"] == "button_text"]
    assert btns, exps
    # 新增按钮文案应含「新增」
    flat = [t for b in btns for t in b.get("texts", [])]
    assert "新增" in flat, flat


def test_derive_empty_when_no_signal():
    assert e2e_expectations.derive_e2e_expectations("") == []
    assert e2e_expectations.derive_e2e_expectations("   ") == []
    # 无任何页面类型关键词 → 空清单（调用方仍做渲染完整性检查）
    assert e2e_expectations.derive_e2e_expectations("随便一句不含关键词的话") == []


def test_derive_dedup():
    # 同时命中登录+注册不应重复产出密码框
    exps = e2e_expectations.derive_e2e_expectations("登录与注册")
    pw = [e for e in exps if e["kind"] == "password"]
    assert len(pw) == 1, exps


def test_derive_login_page_does_not_expect_crud():
    # 登录页（系统名含"管理"）不该期望数据表格/查询/新增/表单——修复正确登录页 E2E 误报
    exps = e2e_expectations.derive_e2e_expectations("后台管理系统的登录页，用户名密码登录")
    kinds = {e["kind"] for e in exps}
    labels = {e["label"] for e in exps}
    assert "password" in kinds  # 登录页该有密码框
    assert "登录提交按钮" in labels
    assert "table" not in kinds
    assert "数据表格" not in labels
    assert "新增按钮" not in labels
    assert "查询/搜索按钮" not in labels
    assert "表单输入控件" not in labels


# ---------- _e2e_browser_check_issues fail-open + 透传 ----------

def test_e2e_check_failopen_on_harness_error(monkeypatch):
    async def fake_run(*a, **k):
        return {"passed": True, "issues": [], "data_uri": None, "harness_error": "playwright missing"}

    monkeypatch.setattr("app.services.vision_eval_service.run_e2e_assertions", fake_run)
    issues = _run(flow_manager._e2e_browser_check_issues(
        {"src/views/login/index.vue": "<template>x</template>"}, "登录页", ""))
    assert issues == []


def test_e2e_check_failopen_on_exception(monkeypatch):
    async def boom(*a, **k):
        raise RuntimeError("browser exploded")

    monkeypatch.setattr("app.services.vision_eval_service.run_e2e_assertions", boom)
    issues = _run(flow_manager._e2e_browser_check_issues({}, "登录页", ""))
    assert issues == []


def test_e2e_check_returns_issues(monkeypatch):
    async def fake_run(*a, **k):
        return {"passed": False, "issues": ["缺少期望控件：密码输入框"], "data_uri": None}

    monkeypatch.setattr("app.services.vision_eval_service.run_e2e_assertions", fake_run)
    issues = _run(flow_manager._e2e_browser_check_issues(
        {"src/views/login/index.vue": "x"}, "登录页", ""))
    assert issues == ["缺少期望控件：密码输入框"]
