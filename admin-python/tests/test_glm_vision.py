"""Offline tests for the multimodal (vision) foundation in glm_provider.

No network: these verify model registration, message construction, and that
the request payload serializes the OpenAI-compatible content-array correctly.
"""
from app.ai.glm_provider import MODEL_CONFIG, ChatGLM, build_vision_messages


def test_vision_models_registered():
    assert "glm-4v" in MODEL_CONFIG
    assert "glm-4v-plus" in MODEL_CONFIG
    assert "glm-4v-flash" in MODEL_CONFIG


def test_build_vision_messages_structure():
    msgs = build_vision_messages("描述这张图", ["data:image/png;base64,AAAA"])
    assert len(msgs) == 1
    assert msgs[0]["role"] == "user"
    content = msgs[0]["content"]
    assert isinstance(content, list)
    assert content[0] == {"type": "text", "text": "描述这张图"}
    assert content[1] == {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}}


def test_build_vision_messages_with_system():
    msgs = build_vision_messages("hi", ["data:image/png;base64,B"], system="你是 UI 评审")
    assert msgs[0]["role"] == "system"
    assert msgs[0]["content"] == "你是 UI 评审"
    assert msgs[1]["role"] == "user"
    assert isinstance(msgs[1]["content"], list)


def test_build_vision_messages_multiple_images():
    msgs = build_vision_messages("对比", ["data:image/png;base64,A", "data:image/jpeg;base64,B"])
    user_content = msgs[0]["content"]
    assert sum(1 for p in user_content if p.get("type") == "image_url") == 2


def test_payload_serializes_vision_content_array():
    glm = ChatGLM(model="glm-4v-plus", api_key="test-key")
    msgs = build_vision_messages("describe the UI", ["data:image/png;base64,AAA"])
    payload = glm._build_payload(msgs)
    assert payload["model"] == "glm-4v-plus"
    assert isinstance(payload["messages"][0]["content"], list)
    parts = payload["messages"][0]["content"]
    assert parts[0]["type"] == "text"
    assert parts[1]["type"] == "image_url"
    assert "url" in parts[1]["image_url"]


def test_payload_keeps_plain_text_content_as_string():
    glm = ChatGLM(model="glm-4-flash", api_key="test-key")
    payload = glm._build_payload([{"role": "user", "content": "纯文本仍为字符串"}])
    assert payload["messages"][0]["content"] == "纯文本仍为字符串"
