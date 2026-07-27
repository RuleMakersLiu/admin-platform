"""Tests for A2: vision input wiring in chat agents (offline)."""
import asyncio

from app.ai.agents import AgentFactory
from app.ai.glm_provider import GLMMessage


class _FakeLLM:
    def __init__(self, model="fake-model"):
        self.model = model
        self.captured = None

    async def ainvoke(self, messages):
        self.captured = messages
        return GLMMessage(content="ok", usage={})


def _run(coro):
    return asyncio.run(coro)


def test_build_messages_plain_text_unchanged():
    agent = AgentFactory.get_agent("PM")
    msgs = agent._build_messages("hello", None)
    assert msgs[0]["role"] == "system"
    assert msgs[-1] == {"role": "user", "content": "hello"}
    assert isinstance(msgs[-1]["content"], str)


def test_build_messages_with_images_uses_content_array():
    agent = AgentFactory.get_agent("FE")
    msgs = agent._build_messages("照这张图改", None, ["data:image/png;base64,AAA"])
    user = msgs[-1]
    assert user["role"] == "user"
    assert isinstance(user["content"], list)
    assert user["content"][0] == {"type": "text", "text": "照这张图改"}
    assert user["content"][1] == {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAA"}}


def test_build_messages_history_strings_plus_vision_user():
    agent = AgentFactory.get_agent("PM")
    history = [{"role": "user", "content": "旧问题"}, {"role": "assistant", "content": "旧回答"}]
    msgs = agent._build_messages("新问题", history, ["data:image/png;base64,B"])
    assert len(msgs) == 4  # system + 2 history + 1 vision user
    assert isinstance(msgs[1]["content"], str)  # history stays string
    assert isinstance(msgs[-1]["content"], list)  # user is vision


def test_process_with_image_attachment_uses_vision_llm_and_content_array():
    agent = AgentFactory.get_agent("FE")
    fake = _FakeLLM(model="glm-4v-plus")
    agent._get_vision_llm = lambda: fake
    attachments = [{"type": "image", "mime": "image/png", "filename": "a.png", "data_uri": "data:image/png;base64,AAA"}]
    reply = _run(agent.process("describe the UI", None, attachments))
    assert reply == "ok"
    assert isinstance(fake.captured[-1]["content"], list)
    assert fake.captured[-1]["content"][1]["type"] == "image_url"


def test_process_without_attachments_uses_text_llm_string_content():
    agent = AgentFactory.get_agent("PM")
    fake = _FakeLLM(model="glm-4-flash")
    agent._get_llm = lambda: fake
    reply = _run(agent.process("plain question"))
    assert reply == "ok"
    assert isinstance(fake.captured[-1]["content"], str)


def test_process_with_text_document_merges_into_prompt():
    import base64

    agent = AgentFactory.get_agent("PM")
    fake = _FakeLLM()
    agent._get_llm = lambda: fake
    payload = base64.b64encode("需求：实现登录页面".encode("utf-8")).decode()
    attachments = [{"type": "document", "mime": "text/plain", "filename": "req.txt",
                    "data_uri": f"data:text/plain;base64,{payload}"}]
    _run(agent.process("按附件实现", None, attachments))
    user_content = fake.captured[-1]["content"]
    assert isinstance(user_content, str)
    assert "需求：实现登录页面" in user_content


def test_get_vision_llm_returns_chatglm_when_key_set(monkeypatch):
    from app.ai.glm_provider import ChatGLM
    from app.core.config import settings

    monkeypatch.setattr(settings, "zai_api_key", "test-key")
    agent = AgentFactory.get_agent("PM")
    llm = agent._get_vision_llm()
    assert isinstance(llm, ChatGLM)
    assert llm.model == settings.zai_vision_model


def test_get_vision_llm_none_without_key(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "zai_api_key", None)
    agent = AgentFactory.get_agent("PM")
    assert agent._get_vision_llm() is None
