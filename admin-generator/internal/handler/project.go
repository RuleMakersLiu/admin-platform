package handler

import (
	"admin-generator/internal/service"
	"archive/zip"
	"bytes"
	"fmt"
	"net/http"
	"strconv"

	"github.com/gin-gonic/gin"
)

var templateService = service.NewTemplateService()
var projectService = service.NewProjectService()

// ========== 模板相关 ==========

// ListTemplates 获取模板列表
func ListTemplates(c *gin.Context) {
	tenantID, _ := strconv.ParseInt(c.GetHeader("X-Tenant-Id"), 10, 64)
	language := c.Query("language")

	templates, err := templateService.ListTemplates(tenantID, language)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{"code": 200, "message": "成功", "data": templates})
}

// GetTemplate 获取模板详情
func GetTemplate(c *gin.Context) {
	id, _ := strconv.ParseInt(c.Param("id"), 10, 64)

	tmpl, err := templateService.GetTemplateByID(id)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"code": 404, "message": "模板不存在"})
		return
	}

	c.JSON(http.StatusOK, gin.H{"code": 200, "message": "成功", "data": tmpl})
}

// CreateTemplateRequest 创建模板请求
type CreateTemplateRequest struct {
	Name        string `json:"name" binding:"required"`
	Code        string `json:"code" binding:"required"`
	Language    string `json:"language" binding:"required"`
	Framework   string `json:"framework" binding:"required"`
	Description string `json:"description"`
	Structure   string `json:"structure" binding:"required"`
	Variables   string `json:"variables"`
	TestConfig  string `json:"test_config"`
	BuildConfig string `json:"build_config"`
	Icon        string `json:"icon"`
}

// CreateTemplate 创建模板
func CreateTemplate(c *gin.Context) {
	var req CreateTemplateRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "参数错误"})
		return
	}

	tenantID, _ := strconv.ParseInt(c.GetHeader("X-Tenant-Id"), 10, 64)

	tmpl := &service.ProjectTemplate{
		Name:        req.Name,
		Code:        req.Code,
		Language:    req.Language,
		Framework:   req.Framework,
		Description: req.Description,
		Structure:   req.Structure,
		Variables:   req.Variables,
		TestConfig:  req.TestConfig,
		BuildConfig: req.BuildConfig,
		Icon:        req.Icon,
		TenantID:    tenantID,
	}

	if err := templateService.CreateTemplate(tmpl); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{"code": 200, "message": "创建成功", "data": tmpl})
}

// UpdateTemplate 更新模板
func UpdateTemplate(c *gin.Context) {
	id, _ := strconv.ParseInt(c.Param("id"), 10, 64)

	var updates map[string]interface{}
	if err := c.ShouldBindJSON(&updates); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "参数错误"})
		return
	}

	allowedFields := map[string]bool{
		"name": true, "code": true, "language": true, "framework": true,
		"description": true, "structure": true, "variables": true,
		"test_config": true, "build_config": true, "icon": true, "sort": true, "status": true,
	}
	filtered := make(map[string]interface{})
	for k, v := range updates {
		if allowedFields[k] {
			filtered[k] = v
		}
	}

	if err := templateService.UpdateTemplate(id, filtered); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{"code": 200, "message": "更新成功", "data": gin.H{"id": id}})
}

// DeleteTemplate 删除模板
func DeleteTemplate(c *gin.Context) {
	id, _ := strconv.ParseInt(c.Param("id"), 10, 64)

	if err := templateService.DeleteTemplate(id); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{"code": 200, "message": "删除成功", "data": gin.H{"id": id}})
}

// ListLanguages 获取支持的语言列表
func ListLanguages(c *gin.Context) {
	languages, err := templateService.ListLanguages()
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{"code": 200, "message": "成功", "data": languages})
}

// ========== 项目生成相关 ==========

// CreateProject 创建项目
func CreateProject(c *gin.Context) {
	var req service.CreateProjectRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "参数错误: " + err.Error()})
		return
	}

	adminID, _ := strconv.ParseInt(c.GetHeader("X-Admin-Id"), 10, 64)
	tenantID, _ := strconv.ParseInt(c.GetHeader("X-Tenant-Id"), 10, 64)

	project, files, err := projectService.CreateProject(&req, adminID, tenantID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"code":    200,
		"message": "创建成功",
		"data": gin.H{
			"project": project,
			"files":   files,
		},
	})
}

// ListProjects 获取项目列表
func ListProjects(c *gin.Context) {
	tenantID, _ := strconv.ParseInt(c.GetHeader("X-Tenant-Id"), 10, 64)
	adminID, _ := strconv.ParseInt(c.GetHeader("X-Admin-Id"), 10, 64)
	page, _ := strconv.Atoi(c.DefaultQuery("page", "1"))
	pageSize, _ := strconv.Atoi(c.DefaultQuery("page_size", "10"))

	projects, total, err := projectService.ListProjects(tenantID, adminID, page, pageSize)
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

	project, err := projectService.GetProjectByID(id, tenantID)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"code": 404, "message": "项目不存在"})
		return
	}

	c.JSON(http.StatusOK, gin.H{"code": 200, "message": "成功", "data": project})
}

// DeleteProject 删除项目
func DeleteProject(c *gin.Context) {
	id, _ := strconv.ParseInt(c.Param("id"), 10, 64)
	tenantID, _ := strconv.ParseInt(c.GetHeader("X-Tenant-Id"), 10, 64)

	if err := projectService.DeleteProject(id, tenantID); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{"code": 200, "message": "删除成功", "data": gin.H{"id": id}})
}

// RegenerateProject 重新生成项目代码
func RegenerateProject(c *gin.Context) {
	id, _ := strconv.ParseInt(c.Param("id"), 10, 64)
	tenantID, _ := strconv.ParseInt(c.GetHeader("X-Tenant-Id"), 10, 64)

	files, err := projectService.RegenerateProject(id, tenantID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{"code": 200, "message": "重新生成成功", "data": gin.H{"files": files}})
}

// DownloadProject 下载项目代码(ZIP)
func DownloadProject(c *gin.Context) {
	id, _ := strconv.ParseInt(c.Param("id"), 10, 64)
	tenantID, _ := strconv.ParseInt(c.GetHeader("X-Tenant-Id"), 10, 64)

	project, files, err := projectService.GetProjectWithFiles(id, tenantID)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"code": 404, "message": "项目不存在"})
		return
	}

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

	filename := fmt.Sprintf("%s.zip", project.Code)
	c.Header("Content-Disposition", "attachment; filename="+filename)
	c.Data(http.StatusOK, "application/zip", buf.Bytes())
}

// PreviewProject 预览项目文件
func PreviewProject(c *gin.Context) {
	id, _ := strconv.ParseInt(c.Param("id"), 10, 64)
	tenantID, _ := strconv.ParseInt(c.GetHeader("X-Tenant-Id"), 10, 64)

	project, files, err := projectService.GetProjectWithFiles(id, tenantID)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"code": 404, "message": "项目不存在"})
		return
	}

	var fileList []gin.H
	for name, content := range files {
		fileList = append(fileList, gin.H{"name": name, "content": content})
	}

	c.JSON(http.StatusOK, gin.H{
		"code": 200, "message": "成功",
		"data": gin.H{"project": project, "files": fileList},
	})
}

// GetProjectTestConfig 获取项目的测试配置
func GetProjectTestConfig(c *gin.Context) {
	id, _ := strconv.ParseInt(c.Param("id"), 10, 64)
	tenantID, _ := strconv.ParseInt(c.GetHeader("X-Tenant-Id"), 10, 64)

	project, err := projectService.GetProjectByID(id, tenantID)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"code": 404, "message": "项目不存在"})
		return
	}

	tmpl, err := templateService.GetTemplateByID(project.TemplateID)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"code": 404, "message": "模板不存在"})
		return
	}

	testCfg, _ := templateService.GetTestConfig(tmpl)
	buildCfg, _ := templateService.GetBuildConfig(tmpl)

	c.JSON(http.StatusOK, gin.H{
		"code": 200, "message": "成功",
		"data": gin.H{
			"project":      project,
			"test_config":  testCfg,
			"build_config": buildCfg,
		},
	})
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

	allowedFields := map[string]bool{
		"name": true, "description": true, "repo_url": true, "branch": true, "status": true, "git_config_id": true, "llm_config_id": true, "language": true, "framework": true,
	}
	filtered := make(map[string]interface{})
	var tenantScopeIDs []int64
	for k, v := range updates {
		if k == "tenant_scope_ids" {
			if rawList, ok := v.([]interface{}); ok {
				for _, item := range rawList {
					switch value := item.(type) {
					case float64:
						tenantScopeIDs = append(tenantScopeIDs, int64(value))
					case int64:
						tenantScopeIDs = append(tenantScopeIDs, value)
					case int:
						tenantScopeIDs = append(tenantScopeIDs, int64(value))
					}
				}
			}
			continue
		}
		if allowedFields[k] {
			filtered[k] = v
		}
	}

	if err := projectService.UpdateProject(id, tenantID, filtered); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": err.Error()})
		return
	}
	if len(tenantScopeIDs) > 0 {
		adminID, _ := strconv.ParseInt(c.GetHeader("X-Admin-Id"), 10, 64)
		if err := projectService.UpdateProjectTenantScopes(id, tenantID, tenantScopeIDs, adminID); err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": err.Error()})
			return
		}
	}

	c.JSON(http.StatusOK, gin.H{"code": 200, "message": "更新成功", "data": gin.H{"id": id}})
}

// ImportProject 从 Git 导入项目
func ImportProject(c *gin.Context) {
	var req service.ImportProjectRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "参数错误: " + err.Error()})
		return
	}

	adminID, _ := strconv.ParseInt(c.GetHeader("X-Admin-Id"), 10, 64)
	tenantID, _ := strconv.ParseInt(c.GetHeader("X-Tenant-Id"), 10, 64)

	project, err := projectService.ImportProject(&req, adminID, tenantID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"code":    200,
		"message": "导入成功",
		"data":    project,
	})
}
