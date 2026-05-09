package handler

import (
	"net/http"

	"github.com/gin-gonic/gin"

	"admin-agent/internal/service"
)

// ProjectHandler 项目处理器
type ProjectHandler struct {
	projectService *service.AgentService
}

// NewProjectHandler 创建项目处理器
func NewProjectHandler(projectService *service.AgentService) *ProjectHandler {
	return &ProjectHandler{
		projectService: projectService,
	}
}

// CreateProjectRequest 创建项目请求
type CreateProjectRequest struct {
	ProjectName string `json:"project_name" binding:"required"`
	Description string `json:"description"`
	Priority    string `json:"priority"`
}

// CreateProject 创建项目
func (h *ProjectHandler) CreateProject(c *gin.Context) {
	var req CreateProjectRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	userID := c.GetUint64("user_id")
	tenantID := c.GetUint64("tenant_id")

	project, err := h.projectService.CreateProject(
		userID,
		tenantID,
		req.ProjectName,
		req.Description,
		req.Priority,
	)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, project)
}

// GetProject 获取项目详情
func (h *ProjectHandler) GetProject(c *gin.Context) {
	projectID := c.Param("id")

	project, err := h.projectService.GetProject(projectID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, project)
}

// ListProjects 获取项目列表
func (h *ProjectHandler) ListProjects(c *gin.Context) {
	tenantID := c.GetUint64("tenant_id")
	status := c.Query("status")

	projects, err := h.projectService.ListProjects(tenantID, status)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"total": len(projects),
		"list":  projects,
	})
}

// TaskHandler 任务处理器
type TaskHandler struct {
	taskService *service.AgentService
}

// NewTaskHandler 创建任务处理器
func NewTaskHandler(taskService *service.AgentService) *TaskHandler {
	return &TaskHandler{
		taskService: taskService,
	}
}

// ListTasks 获取任务列表
func (h *TaskHandler) ListTasks(c *gin.Context) {
	projectID := c.Query("project_id")
	status := c.Query("status")
	assignee := c.Query("assignee")

	tasks, err := h.taskService.ListTasks(projectID, status, assignee)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"total": len(tasks),
		"list":  tasks,
	})
}

// UpdateTaskStatus 更新任务状态
func (h *TaskHandler) UpdateTaskStatus(c *gin.Context) {
	taskID := c.Param("id")

	var req struct {
		Status   string `json:"status" binding:"required"`
		Progress int    `json:"progress"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	if err := h.taskService.UpdateTaskStatus(taskID, req.Status, req.Progress); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{"message": "更新成功"})
}

// BugHandler BUG处理器
type BugHandler struct {
	bugService *service.AgentService
}

// NewBugHandler 创建BUG处理器
func NewBugHandler(bugService *service.AgentService) *BugHandler {
	return &BugHandler{
		bugService: bugService,
	}
}

// ListBugs 获取BUG列表
func (h *BugHandler) ListBugs(c *gin.Context) {
	projectID := c.Query("project_id")
	status := c.Query("status")
	severity := c.Query("severity")

	bugs, err := h.bugService.ListBugs(projectID, status, severity)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"total": len(bugs),
		"list":  bugs,
	})
}

// UpdateBugStatus 更新BUG状态
func (h *BugHandler) UpdateBugStatus(c *gin.Context) {
	bugID := c.Param("id")

	var req struct {
		Status   string `json:"status" binding:"required"`
		FixNote  string `json:"fix_note"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	if err := h.bugService.UpdateBugStatus(bugID, req.Status, req.FixNote); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{"message": "更新成功"})
}
