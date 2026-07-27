"""Tests for eval_judge (offline; LLM mocked)."""
import asyncio

from app.ai import eval_judge
from app.ai.glm_provider import GLMMessage


def _run(coro):
    return asyncio.run(coro)


def test_build_judge_prompt_includes_all_sections():
    p = eval_judge.build_judge_prompt({"r": "登录页"}, "产物代码", ["有登录表单", "有验证码"])
    assert "登录页" in p
    assert "产物代码" in p
    assert "有验证码" in p
    assert "per_criterion" in p


def test_parse_judgment_valid_json():
    content = (
        '{"overall_score": 85, "per_criterion": ['
        '{"criterion":"有登录表单","score":90,"passed":true,"reason":"有"},'
        '{"criterion":"有验证码","score":60,"passed":true,"reason":"有"}],'
        '"summary":"ok"}'
    )
    r = eval_judge.parse_judgment(content)
    assert r["overall_score"] == 85
    assert len(r["per_criterion"]) == 2
    assert r["per_criterion"][1]["passed"] is True
    assert r["summary"] == "ok"


def test_parse_judgment_derives_overall_when_missing():
    r = eval_judge.parse_judgment('{"per_criterion": [{"score":80},{"score":60}]}')
    assert r["overall_score"] == 70  # 80,60 的均值
    assert r["per_criterion"][0]["passed"] is True
    assert r["per_criterion"][1]["passed"] is True  # 60 >= 60


def test_parse_judgment_extracts_json_from_markdown():
    content = '评审：\n```json\n{"overall_score": 50, "per_criterion": [{"criterion":"x","score":50,"passed":false}]}\n```\n完成'
    r = eval_judge.parse_judgment(content)
    assert r["overall_score"] == 50
    assert r["per_criterion"][0]["passed"] is False


def test_parse_judgment_empty():
    r = eval_judge.parse_judgment("")
    assert r["overall_score"] is None
    assert "error" in r


def test_parse_judgment_garbage():
    r = eval_judge.parse_judgment("这根本不是 JSON")
    assert r["overall_score"] is None
    assert "error" in r


class _FakeLLM:
    def __init__(self, content):
        self.model = "glm-test"
        self._content = content

    async def ainvoke(self, messages):
        return GLMMessage(content=self._content, usage={})


def test_judge_output_with_fake_llm():
    fake = _FakeLLM(
        '{"overall_score":88,"per_criterion":[{"criterion":"c1","score":88,"passed":true,"reason":"r"}],"summary":"good"}'
    )
    r = _run(eval_judge.judge_output({"r": "需求"}, "产物", ["c1"], llm=fake))
    assert r["overall_score"] == 88
    assert r["model"] == "glm-test"
    assert r["per_criterion"][0]["passed"] is True


def test_judge_output_without_llm_returns_error(monkeypatch):
    # 无 api_key -> build_judge_llm 返回 None
    from app.core.config import settings
    monkeypatch.setattr(settings, "zai_api_key", None)
    r = _run(eval_judge.judge_output("需求", "产物", ["c1"], llm=None))
    assert "error" in r
