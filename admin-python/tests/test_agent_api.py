"""API Integration Tests for Agent System - Running against live server"""
import pytest
import httpx


class TestHealthCheck:
    """Tests for health check endpoint"""

    def test_health_check(self, client: httpx.Client):
        """Test health check endpoint"""
        response = client.get("http://localhost:8081/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["service"] == "admin-python"


class TestAuthAPI:
    """Tests for authentication endpoints"""

    def test_login_success(self, client: httpx.Client):
        """Test successful login"""
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
        assert "token" in data["data"]
        assert data["data"]["username"] == "admin"

    def test_login_invalid_password(self, client: httpx.Client):
        """Test login with invalid password"""
        response = client.post(
            "/api/auth/login",
            json={
                "username": "admin",
                "password": "wrongpassword",
                "tenantId": 1
            }
        )
        # API returns 200 with code in body for auth failures
        data = response.json()
        assert data["code"] == 401

    def test_login_invalid_user(self, client: httpx.Client):
        """Test login with non-existent user"""
        response = client.post(
            "/api/auth/login",
            json={
                "username": "nonexistent",
                "password": "password",
                "tenantId": 1
            }
        )
        # API returns 200 with code in body for auth failures
        data = response.json()
        assert data["code"] == 401


class TestProjectAPI:
    """Tests for project endpoints"""

    def test_create_project(self, client: httpx.Client, auth_headers: dict):
        """Test creating a new project"""
        response = client.post(
            "/api/agent/projects",
            json={
                "project_name": "Test Project API",
                "description": "Test project description",
                "priority": "P1"
            },
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200
        assert "projectCode" in data["data"]
        assert data["data"]["projectName"] == "Test Project API"

    def test_get_projects_list(self, client: httpx.Client, auth_headers: dict):
        """Test getting projects list"""
        response = client.get(
            "/api/agent/projects",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200
        assert "list" in data["data"]
        assert "total" in data["data"]

    def test_get_projects_with_pagination(self, client: httpx.Client, auth_headers: dict):
        """Test getting projects with pagination"""
        response = client.get(
            "/api/agent/projects?page=1&page_size=10",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200

    def test_get_projects_with_filter(self, client: httpx.Client, auth_headers: dict):
        """Test getting projects with status filter"""
        response = client.get(
            "/api/agent/projects?status=pending",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200

    def test_create_project_without_auth(self, client: httpx.Client):
        """Test creating project without authentication"""
        response = client.post(
            "/api/agent/projects",
            json={
                "project_name": "Test Project",
                "description": "Test project description"
            }
        )
        assert response.status_code == 401


class TestTaskAPI:
    """Tests for task endpoints"""

    def test_get_tasks_list(self, client: httpx.Client, auth_headers: dict):
        """Test getting tasks list"""
        response = client.get(
            "/api/agent/tasks",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200

    def test_create_task(self, client: httpx.Client, auth_headers: dict):
        """Test creating a new task"""
        # First create a project
        project_response = client.post(
            "/api/agent/projects",
            json={
                "project_name": "Task Test Project API",
                "description": "Project for task testing"
            },
            headers=auth_headers
        )
        project_data = project_response.json()
        project_id = project_data["data"]["id"]

        # Create task
        response = client.post(
            "/api/agent/tasks",
            json={
                "title": "Test Task",
                "description": "Test task description",
                "priority": "P2",
                "assignee_type": "BE",
                "project_id": str(project_id)
            },
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200

    def test_get_tasks_by_project(self, client: httpx.Client, auth_headers: dict):
        """Test getting tasks filtered by project"""
        response = client.get(
            "/api/agent/tasks?project_id=1",
            headers=auth_headers
        )
        assert response.status_code == 200


class TestBugAPI:
    """Tests for bug endpoints"""

    def test_get_bugs_list(self, client: httpx.Client, auth_headers: dict):
        """Test getting bugs list"""
        response = client.get(
            "/api/agent/bugs",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200

    def test_create_bug(self, client: httpx.Client, auth_headers: dict):
        """Test creating a new bug"""
        # First create a project
        project_response = client.post(
            "/api/agent/projects",
            json={
                "project_name": "Bug Test Project API",
                "description": "Project for bug testing"
            },
            headers=auth_headers
        )
        project_data = project_response.json()
        project_id = project_data["data"]["id"]

        # Create bug
        response = client.post(
            "/api/agent/bugs",
            json={
                "title": "Test Bug",
                "description": "Test bug description",
                "severity": "high",
                "project_id": str(project_id)
            },
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200

    def test_get_bugs_with_filter(self, client: httpx.Client, auth_headers: dict):
        """Test getting bugs with severity filter"""
        response = client.get(
            "/api/agent/bugs?severity=high",
            headers=auth_headers
        )
        assert response.status_code == 200


class TestAgentChatAPI:
    """Tests for agent chat endpoints"""

    def test_get_sessions(self, client: httpx.Client, auth_headers: dict):
        """Test getting chat sessions"""
        response = client.get(
            "/api/agent/chat/sessions",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200

    def test_create_session(self, client: httpx.Client, auth_headers: dict):
        """Test creating a new chat session"""
        response = client.post(
            "/api/agent/chat/sessions",
            json={
                "title": "Test Session"
            },
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200
