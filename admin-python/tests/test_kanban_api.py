"""
看板 API 测试
测试任务、项目、看板相关的 API 端点
"""
import pytest
import httpx
from typing import Dict

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
    assert data["code"] == 200
    return data["data"]["token"]


@pytest.fixture
def auth_headers(auth_token: str) -> Dict[str, str]:
    """获取认证请求头"""
    return {"Authorization": f"Bearer {auth_token}"}


class TestKanbanHealthCheck:
    """健康检查测试"""

    def test_health_check(self, client: httpx.Client):
        """测试健康检查端点"""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["service"] == "admin-python"


class TestKanbanProjectAPI:
    """项目 API 测试"""

    def test_list_projects(self, client: httpx.Client, auth_headers: Dict[str, str]):
        """测试获取项目列表"""
        response = client.get("/api/agent/projects", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200
        assert "list" in data["data"]
        assert "total" in data["data"]

    def test_list_projects_with_pagination(self, client: httpx.Client, auth_headers: Dict[str, str]):
        """测试分页获取项目列表"""
        response = client.get(
            "/api/agent/projects?page=1&page_size=10",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200

    def test_list_projects_with_status_filter(self, client: httpx.Client, auth_headers: Dict[str, str]):
        """测试按状态过滤项目"""
        response = client.get(
            "/api/agent/projects?status=pending",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200

    def test_create_project(self, client: httpx.Client, auth_headers: Dict[str, str]):
        """测试创建项目"""
        response = client.post(
            "/api/agent/projects",
            json={
                "project_name": "测试看板项目",
                "description": "这是一个用于看板测试的项目",
                "priority": "P1"
            },
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200
        assert "id" in data["data"] or "projectId" in data["data"]

    def test_create_project_without_auth(self, client: httpx.Client):
        """测试未授权创建项目"""
        response = client.post(
            "/api/agent/projects",
            json={
                "project_name": "未授权项目",
                "description": "测试未授权创建"
            }
        )
        assert response.status_code == 401

    def test_get_project_detail(self, client: httpx.Client, auth_headers: Dict[str, str]):
        """测试获取项目详情"""
        # 先创建一个项目
        create_response = client.post(
            "/api/agent/projects",
            json={
                "project_name": "详情测试项目",
                "description": "测试获取项目详情"
            },
            headers=auth_headers
        )
        create_data = create_response.json()
        project_id = create_data["data"].get("id") or create_data["data"].get("projectId")

        if project_id:
            # 获取项目详情
            response = client.get(
                f"/api/agent/projects/{project_id}",
                headers=auth_headers
            )
            assert response.status_code == 200
            data = response.json()
            assert data["code"] == 200


class TestKanbanTaskAPI:
    """任务 API 测试"""

    def test_list_tasks(self, client: httpx.Client, auth_headers: Dict[str, str]):
        """测试获取任务列表"""
        response = client.get("/api/agent/tasks", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200
        assert "list" in data["data"]
        assert "total" in data["data"]

    def test_list_tasks_with_project_filter(self, client: httpx.Client, auth_headers: Dict[str, str]):
        """测试按项目过滤任务"""
        response = client.get(
            "/api/agent/tasks?project_id=1",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200

    def test_list_tasks_with_status_filter(self, client: httpx.Client, auth_headers: Dict[str, str]):
        """测试按状态过滤任务"""
        response = client.get(
            "/api/agent/tasks?status=pending",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200

    def test_create_task(self, client: httpx.Client, auth_headers: Dict[str, str]):
        """测试创建任务"""
        # 先创建项目
        project_response = client.post(
            "/api/agent/projects",
            json={
                "project_name": "任务测试项目",
                "description": "用于任务测试"
            },
            headers=auth_headers
        )
        project_data = project_response.json()
        project_id = project_data["data"].get("id") or project_data["data"].get("projectId", 1)

        # 创建任务
        response = client.post(
            "/api/agent/tasks",
            json={
                "title": "测试任务标题",
                "description": "测试任务描述",
                "priority": "P2",
                "assignee_type": "BE",
                "project_id": str(project_id)
            },
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200

    def test_update_task_status(self, client: httpx.Client, auth_headers: Dict[str, str]):
        """测试更新任务状态"""
        # 创建项目和任务
        project_response = client.post(
            "/api/agent/projects",
            json={
                "project_name": "状态更新测试项目",
                "description": "用于测试状态更新"
            },
            headers=auth_headers
        )
        project_data = project_response.json()
        project_id = project_data["data"].get("id") or project_data["data"].get("projectId", 1)

        task_response = client.post(
            "/api/agent/tasks",
            json={
                "title": "状态测试任务",
                "description": "测试状态更新",
                "priority": "P1",
                "assignee_type": "PM",
                "project_id": str(project_id)
            },
            headers=auth_headers
        )
        task_data = task_response.json()
        task_id = task_data["data"].get("id") or task_data["data"].get("taskId")

        if task_id:
            # 更新状态
            response = client.put(
                f"/api/agent/tasks/{task_id}/status",
                json={"status": "in_progress", "note": "开始处理"},
                headers=auth_headers
            )
            assert response.status_code == 200
            data = response.json()
            assert data["code"] == 200


class TestKanbanBugAPI:
    """Bug API 测试"""

    def test_list_bugs(self, client: httpx.Client, auth_headers: Dict[str, str]):
        """测试获取 Bug 列表"""
        response = client.get("/api/agent/bugs", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200
        assert "list" in data["data"]
        assert "total" in data["data"]

    def test_create_bug(self, client: httpx.Client, auth_headers: Dict[str, str]):
        """测试创建 Bug"""
        # 先创建项目
        project_response = client.post(
            "/api/agent/projects",
            json={
                "project_name": "Bug 测试项目",
                "description": "用于 Bug 测试"
            },
            headers=auth_headers
        )
        project_data = project_response.json()
        project_id = project_data["data"].get("id") or project_data["data"].get("projectId", 1)

        # 创建 Bug
        response = client.post(
            "/api/agent/bugs",
            json={
                "title": "测试 Bug 标题",
                "description": "测试 Bug 描述",
                "severity": "high",
                "project_id": str(project_id)
            },
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200


class TestKanbanStatistics:
    """看板统计测试"""

    def test_project_statistics(self, client: httpx.Client, auth_headers: Dict[str, str]):
        """测试获取项目统计"""
        # 创建项目
        project_response = client.post(
            "/api/agent/projects",
            json={
                "project_name": "统计测试项目",
                "description": "用于统计测试"
            },
            headers=auth_headers
        )
        project_data = project_response.json()
        project_id = project_data["data"].get("id") or project_data["data"].get("projectId")

        if project_id:
            response = client.get(
                f"/api/agent/projects/{project_id}/statistics",
                headers=auth_headers
            )
            assert response.status_code == 200
            data = response.json()
            assert data["code"] == 200
