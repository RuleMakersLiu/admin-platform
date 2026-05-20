package handler

import (
	"admin-deploy/internal/service"
	"net/http"
	"strconv"

	"github.com/gin-gonic/gin"
)

var testService = service.NewTestService()

// CreateTestTaskRequest 创建测试任务请求
type CreateTestTaskRequest struct {
	ProjectID   int64  `json:"project_id" binding:"required"`
	Type        string `json:"type"`
	DockerImage string `json:"docker_image"`
	TestCmd     string `json:"test_cmd"`
}

// CreateTestTask 创建测试任务
func CreateTestTask(c *gin.Context) {
	var req CreateTestTaskRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "参数错误: " + err.Error()})
		return
	}

	adminID, _ := strconv.ParseInt(c.GetHeader("X-Admin-Id"), 10, 64)
	tenantID, _ := strconv.ParseInt(c.GetHeader("X-Tenant-Id"), 10, 64)

	task, err := testService.CreateTestTask(req.ProjectID, req.Type, req.DockerImage, req.TestCmd, adminID, tenantID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{"code": 200, "message": "创建成功", "data": task})
}

// ExecuteTestTask 执行测试任务
func ExecuteTestTask(c *gin.Context) {
	id, _ := strconv.ParseInt(c.Param("id"), 10, 64)

	go func() {
		testService.ExecuteTestTask(id)
	}()

	c.JSON(http.StatusOK, gin.H{"code": 200, "message": "测试任务开始执行", "data": gin.H{"id": id}})
}

// CancelTestTask 取消测试任务
func CancelTestTask(c *gin.Context) {
	id, _ := strconv.ParseInt(c.Param("id"), 10, 64)

	if err := testService.CancelTestTask(id); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{"code": 200, "message": "任务已取消", "data": gin.H{"id": id}})
}

// GetTestTask 获取测试任务详情
func GetTestTask(c *gin.Context) {
	id, _ := strconv.ParseInt(c.Param("id"), 10, 64)

	task, err := testService.GetTestTask(id)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"code": 404, "message": "任务不存在"})
		return
	}

	c.JSON(http.StatusOK, gin.H{"code": 200, "message": "成功", "data": task})
}

// ListTestTasks 获取测试任务列表
func ListTestTasks(c *gin.Context) {
	projectID, _ := strconv.ParseInt(c.Query("project_id"), 10, 64)
	adminID, _ := strconv.ParseInt(c.GetHeader("X-Admin-Id"), 10, 64)
	page, _ := strconv.Atoi(c.DefaultQuery("page", "1"))
	pageSize, _ := strconv.Atoi(c.DefaultQuery("page_size", "10"))

	tasks, total, err := testService.ListTestTasks(projectID, adminID, page, pageSize)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"code": 200, "message": "成功",
		"data": gin.H{"list": tasks, "total": total, "page": page, "page_size": pageSize},
	})
}

// GetTestTaskLogs 获取测试任务日志
func GetTestTaskLogs(c *gin.Context) {
	id, _ := strconv.ParseInt(c.Param("id"), 10, 64)

	task, err := testService.GetTestTask(id)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"code": 404, "message": "任务不存在"})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"code": 200, "message": "成功",
		"data": gin.H{"id": id, "log": task.Log},
	})
}
