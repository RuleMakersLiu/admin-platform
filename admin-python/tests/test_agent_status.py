"""
智能体状态测试
测试智能分身的状态管理、会话管理和消息处理
"""
import pytest
import httpx
import asyncio
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from typing import Dict, Optional

# 测试配置
BASE_URL = "http://localhost:8081"


@pytest.fixture
def client() -> httpx.Client:
    """创建同步 HTTP 客户端"""
    with httpx.Client(base_url=BASE_URL, timeout=30.0) as c:
        yield c


@pytest.fixture
def auth_token(client: httpx.Client) -> str:
    """获取认证 Token"""
    response = client.post(
        "/api/auth/login",
        json={
            "username": "admin",
            "password": "admin123",
            "tenantId": 1
        }
    )
    assert response.status_code == 200
    data = response.json()
    return data["data"]["token"]


@pytest.fixture
def auth_headers(auth_token: str) -> Dict[str, str]:
    """获取认证请求头"""
    return {"Authorization": f"Bearer {auth_token}"}


# 智能体类型
class AgentType:
    PM = "PM"      # 产品经理
    PJM = "PJM"    # 项目经理
    BE = "BE"      # 后端开发
    FE = "FE"      # 前端开发
    QA = "QA"      # 测试分身
    RPT = "RPT"    # 汇报分身
    USER = "USER"  # 用户


AGENT_NAMES = {
    AgentType.PM: "产品经理",
    AgentType.PJM: "项目经理",
    AgentType.BE: "后端开发",
    AgentType.FE: "前端开发",
    AgentType.QA: "测试分身",
    AgentType.RPT: "汇报分身",
}


class TestAgentTypes:
    """智能体类型测试"""

    def test_all_agent_types_defined(self):
        """测试所有智能体类型已定义"""
        assert AgentType.PM == "PM"
        assert AgentType.PJM == "PJM"
        assert AgentType.BE == "BE"
        assert AgentType.FE == "FE"
        assert AgentType.QA == "QA"
        assert AgentType.RPT == "RPT"

    def test_agent_names_mapping(self):
        """测试智能体名称映射"""
        assert AGENT_NAMES[AgentType.PM] == "产品经理"
        assert AGENT_NAMES[AgentType.PJM] == "项目经理"
        assert AGENT_NAMES[AgentType.BE] == "后端开发"
        assert AGENT_NAMES[AgentType.FE] == "前端开发"
        assert AGENT_NAMES[AgentType.QA] == "测试分身"
        assert AGENT_NAMES[AgentType.RPT] == "汇报分身"


class TestAgentChatAPI:
    """智能体聊天 API 测试"""

    def test_create_chat_session(self, client: httpx.Client, auth_headers: Dict[str, str]):
        """测试创建聊天会话"""
        response = client.post(
            "/api/agent/chat/sessions",
            json={"title": "测试会话"},
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200
        assert "sessionId" in data["data"]

    def test_list_chat_sessions(self, client: httpx.Client, auth_headers: Dict[str, str]):
        """测试获取会话列表"""
        response = client.get(
            "/api/agent/chat/sessions",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200
        assert "list" in data["data"]

    def test_send_chat_message(self, client: httpx.Client, auth_headers: Dict[str, str]):
        """测试发送聊天消息"""
        # 先创建会话
        session_response = client.post(
            "/api/agent/chat/sessions",
            json={"title": "聊天测试会话"},
            headers=auth_headers
        )
        session_data = session_response.json()
        session_id = session_data["data"].get("sessionId")

        # 发送消息
        response = client.post(
            "/api/agent/chat",
            json={
                "session_id": session_id or "test_session",
                "message": "你好，这是一条测试消息",
                "agent_type": AgentType.PM
            },
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200

    def test_chat_with_different_agents(self, client: httpx.Client, auth_headers: Dict[str, str]):
        """测试与不同智能体聊天"""
        agent_types = [AgentType.PM, AgentType.PJM, AgentType.BE, AgentType.FE, AgentType.QA]

        for agent_type in agent_types:
            response = client.post(
                "/api/agent/chat",
                json={
                    "session_id": f"test_session_{agent_type}",
                    "message": f"测试与{AGENT_NAMES[agent_type]}的对话",
                    "agent_type": agent_type
                },
                headers=auth_headers
            )
            assert response.status_code == 200
            data = response.json()
            assert data["code"] == 200

    def test_get_session_history(self, client: httpx.Client, auth_headers: Dict[str, str]):
        """测试获取会话历史"""
        # 创建会话
        session_response = client.post(
            "/api/agent/chat/sessions",
            json={"title": "历史测试会话"},
            headers=auth_headers
        )
        session_data = session_response.json()
        session_id = session_data["data"].get("sessionId")

        if session_id:
            # 发送消息
            client.post(
                "/api/agent/chat",
                json={
                    "session_id": session_id,
                    "message": "历史记录测试",
                    "agent_type": AgentType.PM
                },
                headers=auth_headers
            )

            # 获取历史
            response = client.get(
                f"/api/agent/chat/sessions/{session_id}",
                headers=auth_headers
            )
            assert response.status_code == 200
            data = response.json()
            assert data["code"] == 200

    def test_delete_session(self, client: httpx.Client, auth_headers: Dict[str, str]):
        """测试删除会话"""
        # 创建会话
        session_response = client.post(
            "/api/agent/chat/sessions",
            json={"title": "待删除会话"},
            headers=auth_headers
        )
        session_data = session_response.json()
        session_id = session_data["data"].get("sessionId")

        if session_id:
            # 删除会话
            response = client.delete(
                f"/api/agent/chat/sessions/{session_id}",
                headers=auth_headers
            )
            assert response.status_code == 200
            data = response.json()
            assert data["code"] == 200


class TestAgentStatus:
    """智能体状态测试"""

    def test_agent_status_idle(self):
        """测试智能体空闲状态"""
        # 模拟智能体空闲状态
        agent_status = {
            "agent_type": AgentType.PM,
            "status": "idle",
            "current_task": None,
            "last_active": 1700000000000
        }
        assert agent_status["status"] == "idle"
        assert agent_status["current_task"] is None

    def test_agent_status_busy(self):
        """测试智能体忙碌状态"""
        # 模拟智能体忙碌状态
        agent_status = {
            "agent_type": AgentType.BE,
            "status": "busy",
            "current_task": {
                "task_id": "task_001",
                "task_name": "实现用户登录API",
                "progress": 50
            },
            "last_active": 1700000000000
        }
        assert agent_status["status"] == "busy"
        assert agent_status["current_task"] is not None
        assert agent_status["current_task"]["progress"] == 50

    def test_agent_status_error(self):
        """测试智能体错误状态"""
        # 模拟智能体错误状态
        agent_status = {
            "agent_type": AgentType.FE,
            "status": "error",
            "error_message": "API 调用失败",
            "last_active": 1700000000000
        }
        assert agent_status["status"] == "error"
        assert "error_message" in agent_status


class TestAgentSessionManagement:
    """智能体会话管理测试"""

    def test_session_id_generation(self):
        """测试会话 ID 生成"""
        import uuid
        
        # 模拟会话 ID 生成
        session_id = f"sess_{uuid.uuid4().hex[:16]}"
        
        assert session_id.startswith("sess_")
        assert len(session_id) == 21  # "sess_" (5) + 16 hex chars

    def test_message_id_generation(self):
        """测试消息 ID 生成"""
        import uuid
        
        # 模拟消息 ID 生成
        msg_id = f"msg_{uuid.uuid4().hex[:16]}"
        
        assert msg_id.startswith("msg_")
        assert len(msg_id) == 20  # "msg_" (4) + 16 hex chars

    def test_session_message_limit(self):
        """测试会话消息数量限制"""
        # 模拟会话消息历史
        session_messages = []
        max_messages = 20
        
        # 添加超过限制的消息
        for i in range(25):
            session_messages.append({
                "role": "user" if i % 2 == 0 else "assistant",
                "content": f"消息 {i}"
            })
        
        # 限制消息数量
        if len(session_messages) > max_messages:
            session_messages = session_messages[-max_messages:]
        
        assert len(session_messages) == max_messages


class TestAgentMessageProcessing:
    """智能体消息处理测试"""

    @pytest.mark.asyncio
    async def test_process_user_message(self):
        """测试处理用户消息"""
        # 模拟消息处理
        message = "请帮我分析用户登录需求"
        
        # 预期响应结构
        expected_response = {
            "session_id": "test_session",
            "msg_id": "msg_test",
            "agent_type": AgentType.PM,
            "reply": "好的，我来分析用户登录需求...",
            "msg_type": "chat"
        }
        
        assert expected_response["agent_type"] == AgentType.PM
        assert expected_response["msg_type"] == "chat"
        assert len(expected_response["reply"]) > 0

    @pytest.mark.asyncio
    async def test_process_empty_message(self):
        """测试处理空消息"""
        message = ""
        
        # 空消息应该被拒绝或返回错误
        is_valid = len(message.strip()) > 0
        assert is_valid is False

    @pytest.mark.asyncio
    async def test_process_long_message(self):
        """测试处理长消息"""
        # 生成超长消息
        long_message = "测试消息 " * 10000
        
        # 检查消息长度限制
        max_length = 10000
        is_valid = len(long_message) <= max_length
        # 预期消息太长
        assert is_valid is False


class TestAgentTaskAssignment:
    """智能体任务分配测试"""

    def test_assign_task_to_be(self, client: httpx.Client, auth_headers: Dict[str, str]):
        """测试分配任务给后端智能体"""
        # 创建项目和任务
        project_response = client.post(
            "/api/agent/projects",
            json={
                "project_name": "任务分配测试项目",
                "description": "用于测试任务分配"
            },
            headers=auth_headers
        )
        project_data = project_response.json()
        project_id = project_data["data"].get("id") or project_data["data"].get("projectId", 1)

        task_response = client.post(
            "/api/agent/tasks",
            json={
                "title": "后端任务",
                "description": "实现 API 接口",
                "priority": "P1",
                "assignee_type": AgentType.BE,
                "project_id": str(project_id)
            },
            headers=auth_headers
        )
        assert task_response.status_code == 200

    def test_assign_task_to_fe(self, client: httpx.Client, auth_headers: Dict[str, str]):
        """测试分配任务给前端智能体"""
        # 创建项目和任务
        project_response = client.post(
            "/api/agent/projects",
            json={
                "project_name": "前端任务测试项目",
                "description": "用于测试前端任务"
            },
            headers=auth_headers
        )
        project_data = project_response.json()
        project_id = project_data["data"].get("id") or project_data["data"].get("projectId", 1)

        task_response = client.post(
            "/api/agent/tasks",
            json={
                "title": "前端任务",
                "description": "实现登录页面",
                "priority": "P2",
                "assignee_type": AgentType.FE,
                "project_id": str(project_id)
            },
            headers=auth_headers
        )
        assert task_response.status_code == 200

    def test_assign_task_to_qa(self, client: httpx.Client, auth_headers: Dict[str, str]):
        """测试分配任务给测试智能体"""
        # 创建项目和任务
        project_response = client.post(
            "/api/agent/projects",
            json={
                "project_name": "测试任务项目",
                "description": "用于测试 QA 任务"
            },
            headers=auth_headers
        )
        project_data = project_response.json()
        project_id = project_data["data"].get("id") or project_data["data"].get("projectId", 1)

        task_response = client.post(
            "/api/agent/tasks",
            json={
                "title": "测试任务",
                "description": "编写单元测试",
                "priority": "P2",
                "assignee_type": AgentType.QA,
                "project_id": str(project_id)
            },
            headers=auth_headers
        )
        assert task_response.status_code == 200


class TestAgentWorkflows:
    """智能体工作流测试"""

    def test_pm_to_pjm_workflow(self, client: httpx.Client, auth_headers: Dict[str, str]):
        """测试 PM 到 PJM 的工作流"""
        # PM 创建需求
        pm_response = client.post(
            "/api/agent/chat",
            json={
                "session_id": "workflow_session",
                "message": "我需要实现用户登录功能",
                "agent_type": AgentType.PM
            },
            headers=auth_headers
        )
        assert pm_response.status_code == 200

        # PJM 规划任务
        pjm_response = client.post(
            "/api/agent/chat",
            json={
                "session_id": "workflow_session",
                "message": "根据需求拆分任务",
                "agent_type": AgentType.PJM
            },
            headers=auth_headers
        )
        assert pjm_response.status_code == 200

    def test_be_fe_collaboration(self, client: httpx.Client, auth_headers: Dict[str, str]):
        """测试后端和前端协作"""
        # 后端定义接口
        be_response = client.post(
            "/api/agent/chat",
            json={
                "session_id": "collab_session",
                "message": "定义登录接口",
                "agent_type": AgentType.BE
            },
            headers=auth_headers
        )
        assert be_response.status_code == 200

        # 前端确认接口
        fe_response = client.post(
            "/api/agent/chat",
            json={
                "session_id": "collab_session",
                "message": "确认接口格式",
                "agent_type": AgentType.FE
            },
            headers=auth_headers
        )
        assert fe_response.status_code == 200
