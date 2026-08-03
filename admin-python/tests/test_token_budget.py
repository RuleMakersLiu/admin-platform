"""token_budget + context-length 错误处理单测（A1：防上下文超窗失败）。"""
from app.ai.token_budget import estimate_tokens, model_input_window, trim_message_for_window
from app.ai.glm_provider import MODEL_INPUT_WINDOWS
from app.ai.flow_manager import _is_context_length_error, _is_retriable_error


def test_estimate_tokens():
    assert estimate_tokens(None) == 1
    assert estimate_tokens("") == 1
    assert estimate_tokens("x" * 100) == 50  # len/2


def test_model_input_windows():
    assert model_input_window("glm-4") == 128000
    assert model_input_window("glm-4-long") == 1_000_000
    assert model_input_window("glm-4v-plus") == 8192  # 视觉模型窗口小
    assert model_input_window("unknown-model") == 128000  # 默认


def test_trim_message_keeps_tail_when_over_window():
    """超窗 → 截断头部（丢 memory/fix 上下文），保尾部核心 + 加截断标记。"""
    big = "HEAD_CONTEXT_" * 100000 + "TAIL_CORE_REQUIREMENT"
    trimmed = trim_message_for_window(big, "glm-4v")  # 8k 窗口 → 必裁
    assert trimmed != big
    assert trimmed.endswith("TAIL_CORE_REQUIREMENT")  # 保尾部核心
    assert "截断" in trimmed  # 截断标记


def test_trim_message_unchanged_when_within_budget():
    assert trim_message_for_window("short message", "glm-4") == "short message"
    # glm-4 128k 窗口 × 0.6 × 2 字符 = ~150k 字符以内不裁
    assert trim_message_for_window("x" * 100000, "glm-4") == "x" * 100000


def test_is_context_length_error_detects_glm_1301():
    """GLM context-length 错误（1301 / maximum context / 中文）能被识别。"""
    assert _is_context_length_error(Exception("This model's maximum context length is 8192 tokens"))
    assert _is_context_length_error(Exception("输入过长，超出模型上下文"))
    assert _is_context_length_error(Exception('{"code":"1301","message":"context length exceeded"}'))


def test_is_context_length_error_not_false_positive():
    """普通错误（timeout/rate-limit）不算 context-length。"""
    assert not _is_context_length_error(Exception("connection timeout"))
    assert not _is_context_length_error(Exception("rate limit exceeded"))


def test_retriable_and_context_length_independent():
    """context-length 不在 _is_retriable_error（它走专属截断重试路径，非盲目重发）。"""
    ctx_err = Exception("maximum context length exceeded")
    assert _is_context_length_error(ctx_err)
    assert not _is_retriable_error(ctx_err)
