package handler

import (
	"admin-generator/internal/service"
	"admin-generator/pkg/parser"
	"archive/zip"
	"bytes"
	"fmt"
	"net/http"
	"strconv"
	"time"

	"github.com/gin-gonic/gin"
)

var generatorService = service.NewGeneratorService()

// ChatRequest 对话请求
type ChatRequest struct {
	SessionID string `json:"session_id"`
	Prompt    string `json:"prompt" binding:"required"`
}

// CreateConfigRequest 创建配置请求
type CreateConfigRequest struct {
	FunctionConfig service.FunctionConfig `json:"function_config"`
	Fields         []service.FieldConfig  `json:"fields"`
}

// UpdateConfigRequest 更新配置请求
type UpdateConfigRequest struct {
	FunctionConfig service.FunctionConfig `json:"function_config"`
	Fields         []service.FieldConfig  `json:"fields"`
}

// Chat 对话
func Chat(c *gin.Context) {
	var req ChatRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "参数错误"})
		return
	}

	adminID, _ := strconv.ParseInt(c.GetHeader("X-Admin-Id"), 10, 64)
	tenantID, _ := strconv.ParseInt(c.GetHeader("X-Tenant-Id"), 10, 64)

	if req.SessionID == "" {
		req.SessionID = time.Now().Format("20060102150405") + "_" + strconv.FormatInt(adminID, 10)
	}

	history, err := generatorService.ProcessChat(req.SessionID, adminID, tenantID, req.Prompt)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": err.Error()})
		return
	}

	generatorService.SaveChatHistory(history)

	c.JSON(http.StatusOK, gin.H{
		"code":    200,
		"message": "成功",
		"data": gin.H{
			"session_id":      req.SessionID,
			"type":           history.Type,
			"command":        history.Command,
			"response":       history.Response,
			"structured_data": history.StructuredData,
			"status":         history.Status,
		},
	})
}

// GetChatHistory 获取对话历史
func GetChatHistory(c *gin.Context) {
	sessionID := c.Param("sessionId")

	histories, err := generatorService.GetChatHistory(sessionID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"code":    200,
		"message": "成功",
		"data":    histories,
	})
}

// GenerateCodeRequest 生成代码请求
type GenerateCodeRequest struct {
	ConfigID int64 `json:"config_id" binding:"required"`
}

// GenerateCode 生成代码
func GenerateCode(c *gin.Context) {
	var req GenerateCodeRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "参数错误"})
		return
	}

	tenantID, _ := strconv.ParseInt(c.GetHeader("X-Tenant-Id"), 10, 64)

	config, err := generatorService.GetConfigByID(req.ConfigID, tenantID)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"code": 404, "message": "配置不存在"})
		return
	}

	files := generatorService.GenerateCodeFiles(config)
	c.JSON(http.StatusOK, gin.H{"code": 200, "message": "生成成功", "data": gin.H{"files": files}})
}

// PreviewCode 预览代码
func PreviewCode(c *gin.Context) {
	id, _ := strconv.ParseInt(c.Param("id"), 10, 64)
	tenantID, _ := strconv.ParseInt(c.GetHeader("X-Tenant-Id"), 10, 64)

	config, err := generatorService.GetConfigByID(id, tenantID)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"code": 404, "message": "配置不存在"})
		return
	}

	files := generatorService.GenerateCodeFiles(config)
	var fileList []gin.H
	for name, content := range files {
		fileList = append(fileList, gin.H{"name": name, "content": content})
	}

	c.JSON(http.StatusOK, gin.H{
		"code": 200, "message": "成功",
		"data": gin.H{"id": id, "files": fileList},
	})
}

// DownloadCode 下载代码
func DownloadCode(c *gin.Context) {
	id, _ := strconv.ParseInt(c.Param("id"), 10, 64)
	tenantID, _ := strconv.ParseInt(c.GetHeader("X-Tenant-Id"), 10, 64)

	config, err := generatorService.GetConfigByID(id, tenantID)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"code": 404, "message": "配置不存在"})
		return
	}

	files := generatorService.GenerateCodeFiles(config)

	buf := new(bytes.Buffer)
	w := zip.NewWriter(buf)
	for name, content := range files {
		f, err := w.Create(name)
		if err != nil {
			continue
		}
		f.Write([]byte(content))
	}
	w.Close()

	filename := fmt.Sprintf("%s_code.zip", config.TableName)
	c.Header("Content-Disposition", "attachment; filename="+filename)
	c.Data(http.StatusOK, "application/zip", buf.Bytes())
}

// ListConfig 列表配置
func ListConfig(c *gin.Context) {
	tenantID, _ := strconv.ParseInt(c.GetHeader("X-Tenant-Id"), 10, 64)
	page, _ := strconv.Atoi(c.DefaultQuery("page", "1"))
	pageSize, _ := strconv.Atoi(c.DefaultQuery("page_size", "10"))

	configs, total, err := generatorService.ListConfig(tenantID, page, pageSize)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"code": 200, "message": "成功",
		"data": gin.H{"list": configs, "total": total, "page": page, "page_size": pageSize},
	})
}

// CreateConfig 创建配置
func CreateConfig(c *gin.Context) {
	var req CreateConfigRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "参数错误"})
		return
	}

	tenantID, _ := strconv.ParseInt(c.GetHeader("X-Tenant-Id"), 10, 64)
	now := time.Now().UnixMilli()
	req.FunctionConfig.TenantID = tenantID
	req.FunctionConfig.CreateTime = now
	req.FunctionConfig.UpdateTime = now

	if err := generatorService.CreateConfig(&req.FunctionConfig, req.Fields); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{"code": 200, "message": "创建成功", "data": req.FunctionConfig})
}

// GetConfig 获取配置
func GetConfig(c *gin.Context) {
	id, _ := strconv.ParseInt(c.Param("id"), 10, 64)
	tenantID, _ := strconv.ParseInt(c.GetHeader("X-Tenant-Id"), 10, 64)

	config, err := generatorService.GetConfigByID(id, tenantID)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"code": 404, "message": "配置不存在"})
		return
	}

	c.JSON(http.StatusOK, gin.H{"code": 200, "message": "成功", "data": config})
}

// UpdateConfig 更新配置
func UpdateConfig(c *gin.Context) {
	id, _ := strconv.ParseInt(c.Param("id"), 10, 64)
	tenantID, _ := strconv.ParseInt(c.GetHeader("X-Tenant-Id"), 10, 64)

	var req UpdateConfigRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "参数错误"})
		return
	}

	if err := generatorService.UpdateConfig(id, tenantID, &req.FunctionConfig, req.Fields); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{"code": 200, "message": "更新成功", "data": gin.H{"id": id}})
}

// DeleteConfig 删除配置
func DeleteConfig(c *gin.Context) {
	id, _ := strconv.ParseInt(c.Param("id"), 10, 64)
	tenantID, _ := strconv.ParseInt(c.GetHeader("X-Tenant-Id"), 10, 64)

	if err := generatorService.DeleteConfig(id, tenantID); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{"code": 200, "message": "删除成功", "data": gin.H{"id": id}})
}

// Help 帮助
func Help(c *gin.Context) {
	c.JSON(http.StatusOK, gin.H{
		"code":    200,
		"message": "成功",
		"data":    parser.GetHelpText(),
	})
}
