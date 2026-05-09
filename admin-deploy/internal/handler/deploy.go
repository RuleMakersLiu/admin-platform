package handler

import (
	"admin-deploy/internal/service"
	"net/http"
	"strconv"

	"github.com/gin-gonic/gin"
)

var deployService = service.NewDeployService()

// CreateTaskRequest 创建任务请求
type CreateTaskRequest struct {
	Project string `json:"project" binding:"required"`
	Env     string `json:"env" binding:"required"`
	Type    int    `json:"type" binding:"required"` // 1构建 2部署 3回滚
}

// CreateProjectRequest 创建项目请求
type CreateProjectRequest struct {
	Name         string `json:"name" binding:"required"`
	Code         string `json:"code" binding:"required"`
	Type         string `json:"type" binding:"required"`
	RepoURL      string `json:"repo_url"`
	Branch       string `json:"branch"`
	BuildCmd     string `json:"build_cmd"`
	Dockerfile   string `json:"dockerfile"`
	ImageName    string `json:"image_name"`
	DeployConfig string `json:"deploy_config"`
}

// ListProjects 获取项目列表
func ListProjects(c *gin.Context) {
	tenantID, _ := strconv.ParseInt(c.GetHeader("X-Tenant-Id"), 10, 64)
	page, _ := strconv.Atoi(c.DefaultQuery("page", "1"))
	pageSize, _ := strconv.Atoi(c.DefaultQuery("page_size", "10"))

	projects, total, err := deployService.ListProjects(tenantID, page, pageSize)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"code": 200, "message": "成功",
		"data": gin.H{"list": projects, "total": total, "page": page, "page_size": pageSize},
	})
}

// GetProject 获取项目详情
func GetProject(c *gin.Context) {
	id, _ := strconv.ParseInt(c.Param("id"), 10, 64)
	tenantID, _ := strconv.ParseInt(c.GetHeader("X-Tenant-Id"), 10, 64)

	project, err := deployService.GetProjectByID(id, tenantID)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"code": 404, "message": "项目不存在"})
		return
	}

	c.JSON(http.StatusOK, gin.H{"code": 200, "message": "成功", "data": project})
}

// CreateProject 创建项目
func CreateProject(c *gin.Context) {
	var req CreateProjectRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "参数错误"})
		return
	}

	tenantID, _ := strconv.ParseInt(c.GetHeader("X-Tenant-Id"), 10, 64)

	project := &service.DeployProject{
		Name:         req.Name,
		Code:         req.Code,
		Type:         req.Type,
		RepoURL:      req.RepoURL,
		Branch:       req.Branch,
		BuildCmd:     req.BuildCmd,
		Dockerfile:   req.Dockerfile,
		ImageName:    req.ImageName,
		DeployConfig: req.DeployConfig,
		TenantID:     tenantID,
		Status:       1,
	}

	if err := deployService.CreateProject(project); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{"code": 200, "message": "创建成功", "data": project})
}

// UpdateProject 更新项目
func UpdateProject(c *gin.Context) {
	id, _ := strconv.ParseInt(c.Param("id"), 10, 64)
	tenantID, _ := strconv.ParseInt(c.GetHeader("X-Tenant-Id"), 10, 64)

	var updates map[string]interface{}
	if err := c.ShouldBindJSON(&updates); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "参数错误"})
		return
	}

	// 白名单过滤，防止修改敏感字段
	allowedFields := map[string]bool{
		"name": true, "code": true, "type": true, "repo_url": true, "branch": true,
		"build_cmd": true, "dockerfile": true, "image_name": true, "deploy_config": true, "status": true,
	}
	filtered := make(map[string]interface{})
	for k, v := range updates {
		if allowedFields[k] {
			filtered[k] = v
		}
	}
	updates = filtered

	if err := deployService.UpdateProject(id, tenantID, updates); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{"code": 200, "message": "更新成功", "data": gin.H{"id": id}})
}

// DeleteProject 删除项目
func DeleteProject(c *gin.Context) {
	id, _ := strconv.ParseInt(c.Param("id"), 10, 64)
	tenantID, _ := strconv.ParseInt(c.GetHeader("X-Tenant-Id"), 10, 64)

	if err := deployService.DeleteProject(id, tenantID); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{"code": 200, "message": "删除成功", "data": gin.H{"id": id}})
}

// ListTasks 获取任务列表
func ListTasks(c *gin.Context) {
	adminID, _ := strconv.ParseInt(c.GetHeader("X-Admin-Id"), 10, 64)

	page, _ := strconv.Atoi(c.DefaultQuery("page", "1"))
	pageSize, _ := strconv.Atoi(c.DefaultQuery("page_size", "10"))

	tasks, total, err := deployService.ListTasks(adminID, page, pageSize)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"code": 200, "message": "成功",
		"data": gin.H{"list": tasks, "total": total, "page": page, "page_size": pageSize},
	})
}

// GetTask 获取任务详情
func GetTask(c *gin.Context) {
	id, _ := strconv.ParseInt(c.Param("id"), 10, 64)

	task, err := deployService.GetTask(id)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"code": 404, "message": "任务不存在"})
		return
	}

	c.JSON(http.StatusOK, gin.H{"code": 200, "message": "成功", "data": task})
}

// CreateTask 创建任务
func CreateTask(c *gin.Context) {
	var req CreateTaskRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "参数错误"})
		return
	}

	adminID, _ := strconv.ParseInt(c.GetHeader("X-Admin-Id"), 10, 64)
	tenantID, _ := strconv.ParseInt(c.GetHeader("X-Tenant-Id"), 10, 64)

	task, err := deployService.CreateTask(req.Project, req.Env, req.Type, adminID, tenantID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{"code": 200, "message": "创建成功", "data": task})
}

// ExecuteTask 执行任务
func ExecuteTask(c *gin.Context) {
	id, _ := strconv.ParseInt(c.Param("id"), 10, 64)

	go func() {
		deployService.ExecuteTask(id)
	}()

	c.JSON(http.StatusOK, gin.H{"code": 200, "message": "任务开始执行", "data": gin.H{"id": id}})
}

// CancelTask 取消任务
func CancelTask(c *gin.Context) {
	id, _ := strconv.ParseInt(c.Param("id"), 10, 64)
	if err := deployService.CancelTask(id); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"code": 200, "message": "任务已取消", "data": gin.H{"id": id}})
}

// GetTaskLogs 获取任务日志
func GetTaskLogs(c *gin.Context) {
	id, _ := strconv.ParseInt(c.Param("id"), 10, 64)

	task, err := deployService.GetTask(id)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"code": 404, "message": "任务不存在"})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"code": 200, "message": "成功",
		"data": gin.H{"id": id, "log": task.Log},
	})
}

// ListContainers 获取容器列表
func ListContainers(c *gin.Context) {
	containers, err := deployService.ListContainers()
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{"code": 200, "message": "成功", "data": containers})
}

// GetContainerLogs 获取容器日志
func GetContainerLogs(c *gin.Context) {
	containerID := c.Param("id")

	logs, err := deployService.GetContainerLogs(containerID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"code": 200, "message": "成功",
		"data": gin.H{"id": containerID, "logs": logs},
	})
}

// StartContainer 启动容器
func StartContainer(c *gin.Context) {
	containerID := c.Param("id")
	if err := deployService.StartContainerByID(containerID); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"code": 200, "message": "容器已启动", "data": gin.H{"id": containerID}})
}

// StopContainer 停止容器
func StopContainer(c *gin.Context) {
	containerID := c.Param("id")
	if err := deployService.StopContainerByID(containerID); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"code": 200, "message": "容器已停止", "data": gin.H{"id": containerID}})
}

// RemoveContainer 删除容器
func RemoveContainer(c *gin.Context) {
	containerID := c.Param("id")
	if err := deployService.RemoveContainerByID(containerID); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"code": 200, "message": "容器已删除", "data": gin.H{"id": containerID}})
}

// ListImages 获取镜像列表
func ListImages(c *gin.Context) {
	images, err := deployService.ListImages()
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{"code": 200, "message": "成功", "data": images})
}

// RemoveImage 删除镜像
func RemoveImage(c *gin.Context) {
	imageID := c.Param("id")
	if err := deployService.RemoveImageByID(imageID); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"code": 200, "message": "镜像已删除", "data": gin.H{"id": imageID}})
}

// 辅助函数
func parseInt64(s string) int64 {
	n, _ := strconv.ParseInt(s, 10, 64)
	return n
}
