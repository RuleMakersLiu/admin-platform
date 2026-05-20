package service

import (
	cfg "admin-generator/internal/config"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"

)

// ProjectTemplate 项目模板
type ProjectTemplate struct {
	ID           int64       `json:"id"`
	Name         string      `json:"name"`
	Code         string      `json:"code"`
	Language     string      `json:"language"`
	Framework    string      `json:"framework"`
	Version      string      `json:"version"`
	Description  string      `json:"description"`
	Structure    string      `json:"structure"`
	Variables    string      `json:"variables"`
	TestConfig   string      `json:"test_config"`
	BuildConfig  string      `json:"build_config"`
	Icon         string      `json:"icon"`
	Sort         int         `json:"sort"`
	IsBuiltin    int         `json:"is_builtin"`
	TenantID     int64       `json:"tenant_id"`
	Status       int         `json:"status"`
	CreateTime   int64       `json:"create_time"`
	UpdateTime   int64       `json:"update_time"`
}

// TemplateFile 模板文件
type TemplateFile struct {
	Path       string `json:"path"`
	Content    string `json:"content"`
	IsTemplate bool   `json:"is_template"`
}

// TemplateVariable 模板变量
type TemplateVariable struct {
	Name     string `json:"name"`
	Label    string `json:"label"`
	Type     string `json:"type"`
	Default  string `json:"default"`
	Required bool   `json:"required"`
}

// TestConfig 测试配置
type TestConfig struct {
	DockerImage string `json:"docker_image"`
	TestCmd     string `json:"test_cmd"`
	CoverageCmd string `json:"coverage_cmd"`
}

// BuildConfig 构建配置
type BuildConfig struct {
	Dockerfile string `json:"dockerfile"`
	BuildCmd   string `json:"build_cmd"`
	OutputDir  string `json:"output_dir"`
}

// TemplateService 模板服务
type TemplateService struct{}

// NewTemplateService 创建服务
func NewTemplateService() *TemplateService {
	return &TemplateService{}
}

// ListTemplates 获取模板列表
func (s *TemplateService) ListTemplates(tenantID int64, language string) ([]ProjectTemplate, error) {
	db := cfg.GetDB()
	var templates []ProjectTemplate

	query := db.Table("gen_project_template").
		Where("status = 1 AND (tenant_id = 0 OR tenant_id = ?)", tenantID)

	if language != "" {
		query = query.Where("language = ?", language)
	}

	err := query.Order("sort ASC, id ASC").Find(&templates).Error
	return templates, err
}

// GetTemplateByID 根据ID获取模板
func (s *TemplateService) GetTemplateByID(id int64) (*ProjectTemplate, error) {
	db := cfg.GetDB()
	var t ProjectTemplate
	err := db.Table("gen_project_template").
		Where("id = ? AND status = 1", id).
		First(&t).Error
	return &t, err
}

// GetTemplateByCode 根据编码获取模板
func (s *TemplateService) GetTemplateByCode(code string) (*ProjectTemplate, error) {
	db := cfg.GetDB()
	var t ProjectTemplate
	err := db.Table("gen_project_template").
		Where("code = ? AND status = 1", code).
		First(&t).Error
	return &t, err
}

// CreateTemplate 创建模板
func (s *TemplateService) CreateTemplate(t *ProjectTemplate) error {
	db := cfg.GetDB()
	now := time.Now().UnixMilli()
	t.CreateTime = now
	t.UpdateTime = now
	t.Status = 1
	return db.Table("gen_project_template").Create(t).Error
}

// UpdateTemplate 更新模板
func (s *TemplateService) UpdateTemplate(id int64, updates map[string]interface{}) error {
	db := cfg.GetDB()
	updates["update_time"] = time.Now().UnixMilli()
	return db.Table("gen_project_template").
		Where("id = ?", id).
		Updates(updates).Error
}

// DeleteTemplate 删除模板
func (s *TemplateService) DeleteTemplate(id int64) error {
	db := cfg.GetDB()
	return db.Table("gen_project_template").
		Where("id = ? AND is_builtin = 0", id).
		Update("status", 0).Error
}

// GetTemplateFiles 获取模板文件列表
func (s *TemplateService) GetTemplateFiles(t *ProjectTemplate) ([]TemplateFile, error) {
	var files []TemplateFile
	if err := json.Unmarshal([]byte(t.Structure), &files); err != nil {
		return nil, err
	}
	return files, nil
}

// GetTemplateVariables 获取模板变量列表
func (s *TemplateService) GetTemplateVariables(t *ProjectTemplate) ([]TemplateVariable, error) {
	if t.Variables == "" {
		return nil, nil
	}
	var vars []TemplateVariable
	if err := json.Unmarshal([]byte(t.Variables), &vars); err != nil {
		return nil, err
	}
	return vars, nil
}

// GetTestConfig 获取测试配置
func (s *TemplateService) GetTestConfig(t *ProjectTemplate) (*TestConfig, error) {
	if t.TestConfig == "" {
		return nil, nil
	}
	var cfg TestConfig
	if err := json.Unmarshal([]byte(t.TestConfig), &cfg); err != nil {
		return nil, err
	}
	return &cfg, nil
}

// GetBuildConfig 获取构建配置
func (s *TemplateService) GetBuildConfig(t *ProjectTemplate) (*BuildConfig, error) {
	if t.BuildConfig == "" {
		return nil, nil
	}
	var cfg BuildConfig
	if err := json.Unmarshal([]byte(t.BuildConfig), &cfg); err != nil {
		return nil, err
	}
	return &cfg, nil
}

// ListLanguages 获取支持的语言列表
func (s *TemplateService) ListLanguages() ([]map[string]interface{}, error) {
	db := cfg.GetDB()
	var results []map[string]interface{}
	err := db.Table("gen_project_template").
		Select("language, COUNT(*) as count").
		Where("status = 1").
		Group("language").
		Find(&results).Error
	return results, err
}

// GenProject 已生成项目
type GenProject struct {
	ID               int64   `json:"id"`
	Name             string  `json:"name"`
	Code             string  `json:"code"`
	Description      string  `json:"description"`
	TemplateID       int64   `json:"template_id"`
	Language         string  `json:"language"`
	Framework        string  `json:"framework"`
	Variables        *string  `json:"variables"`
	ConfigJSON       *string  `json:"config_json"`
	RepoURL          string  `json:"repo_url"`
	Branch           string  `json:"branch"`
	DeployProjectID  *int64  `json:"deploy_project_id"`
	TestPassRate     *float64 `json:"test_pass_rate"`
	LastTestTime     *int64  `json:"last_test_time"`
	AdminID          int64   `json:"admin_id"`
	TenantID         int64   `json:"tenant_id"`
	Status           int     `json:"status"`
	CreateTime       int64   `json:"create_time"`
	UpdateTime       int64   `json:"update_time"`
}

// ProjectService 项目生成服务
type ProjectService struct {
	templateSvc *TemplateService
}

// NewProjectService 创建服务
func NewProjectService() *ProjectService {
	return &ProjectService{
		templateSvc: NewTemplateService(),
	}
}

// CreateProjectRequest 创建项目请求
type CreateProjectRequest struct {
	Name        string            `json:"name" binding:"required"`
	Code        string            `json:"code" binding:"required"`
	Description string            `json:"description"`
	TemplateID  int64             `json:"template_id" binding:"required"`
	Variables   map[string]string `json:"variables"`
	RepoURL     string            `json:"repo_url"`
	Branch      string            `json:"branch"`
}

// CreateProject 创建项目并生成代码
func (s *ProjectService) CreateProject(req *CreateProjectRequest, adminID, tenantID int64) (*GenProject, map[string]string, error) {
	// 获取模板
	tmpl, err := s.templateSvc.GetTemplateByID(req.TemplateID)
	if err != nil {
		return nil, nil, err
	}

	// 获取模板变量定义
	tmplVars, _ := s.templateSvc.GetTemplateVariables(tmpl)

	// 合并默认值
	mergedVars := make(map[string]string)
	for _, v := range tmplVars {
		mergedVars[v.Name] = v.Default
	}
	for k, v := range req.Variables {
		mergedVars[k] = v
	}

	varsJSON, _ := json.Marshal(mergedVars)
	varsStr := string(varsJSON)

	project := &GenProject{
		Name:        req.Name,
		Code:        req.Code,
		Description: req.Description,
		TemplateID:  req.TemplateID,
		Language:    tmpl.Language,
		Framework:   tmpl.Framework,
		Variables:   &varsStr,
		RepoURL:     req.RepoURL,
		Branch:      req.Branch,
		AdminID:     adminID,
		TenantID:    tenantID,
		Status:      1,
		CreateTime:  time.Now().UnixMilli(),
		UpdateTime:  time.Now().UnixMilli(),
	}
	if project.Branch == "" {
		project.Branch = "main"
	}

	db := cfg.GetDB()
	if err := db.Table("gen_project").Create(project).Error; err != nil {
		return nil, nil, err
	}

	// 生成代码文件
	files, err := s.GenerateProjectFiles(tmpl, mergedVars)
	if err != nil {
		return project, nil, err
	}

	return project, files, nil
}

// GenerateProjectFiles 根据模板和变量生成项目文件
func (s *ProjectService) GenerateProjectFiles(tmpl *ProjectTemplate, vars map[string]string) (map[string]string, error) {
	files, err := s.templateSvc.GetTemplateFiles(tmpl)
	if err != nil {
		return nil, err
	}

	result := make(map[string]string)
	for _, f := range files {
		content := f.Content
		path := f.Path

		if f.IsTemplate {
			content = replaceVariables(content, vars)
			path = replaceVariables(path, vars)
		}
		result[path] = content
	}

	return result, nil
}

// replaceVariables 替换模板变量 {{.VarName}}
func replaceVariables(s string, vars map[string]string) string {
	result := s
	for k, v := range vars {
		result = replaceAll(result, "{{."+k+"}}", v)
	}
	return result
}

// replaceAll 简单字符串替换
func replaceAll(s, old, new string) string {
	result := ""
	for {
		idx := indexOf(s, old)
		if idx == -1 {
			return result + s
		}
		result += s[:idx] + new
		s = s[idx+len(old):]
	}
}

func indexOf(s, substr string) int {
	for i := 0; i <= len(s)-len(substr); i++ {
		if s[i:i+len(substr)] == substr {
			return i
		}
	}
	return -1
}

// ListProjects 获取项目列表
func (s *ProjectService) ListProjects(tenantID, adminID int64, page, pageSize int) ([]GenProject, int64, error) {
	db := cfg.GetDB()
	var total int64
	var projects []GenProject

	query := db.Table("gen_project").Where("tenant_id = ?", tenantID)
	if adminID > 0 {
		query = query.Where("admin_id = ?", adminID)
	}

	query.Count(&total)
	offset := (page - 1) * pageSize
	err := query.Order("create_time desc").
		Offset(offset).Limit(pageSize).
		Find(&projects).Error

	return projects, total, err
}

// GetProjectByID 根据ID获取项目
func (s *ProjectService) GetProjectByID(id int64, tenantID int64) (*GenProject, error) {
	db := cfg.GetDB()
	var project GenProject
	err := db.Table("gen_project").
		Where("id = ? AND tenant_id = ?", id, tenantID).
		First(&project).Error
	return &project, err
}

// DeleteProject 删除项目
func (s *ProjectService) DeleteProject(id int64, tenantID int64) error {
	db := cfg.GetDB()
	return db.Table("gen_project").
		Where("id = ? AND tenant_id = ?", id, tenantID).
		Update("status", 0).Error
}

// RegenerateProject 重新生成项目代码
func (s *ProjectService) RegenerateProject(id int64, tenantID int64) (map[string]string, error) {
	project, err := s.GetProjectByID(id, tenantID)
	if err != nil {
		return nil, err
	}

	tmpl, err := s.templateSvc.GetTemplateByID(project.TemplateID)
	if err != nil {
		return nil, err
	}

	var vars map[string]string
	if project.Variables != nil {
		if err := json.Unmarshal([]byte(*project.Variables), &vars); err != nil {
			return nil, err
		}
	}

	return s.GenerateProjectFiles(tmpl, vars)
}

// CreateProjectWithGit 创建项目并推送到Git仓库
func (s *ProjectService) CreateProjectWithGit(req *CreateProjectRequest, adminID, tenantID int64) (*GenProject, map[string]string, error) {
	project, files, err := s.CreateProject(req, adminID, tenantID)
	if err != nil {
		return nil, nil, err
	}

	// Git push logic would go here if repo_url is provided
	// For now, just return the generated files

	return project, files, nil
}

// GetProjectWithFiles 获取项目详情及其生成的文件
func (s *ProjectService) GetProjectWithFiles(id int64, tenantID int64) (*GenProject, map[string]string, error) {
	project, err := s.GetProjectByID(id, tenantID)
	if err != nil {
		return nil, nil, err
	}

	tmpl, err := s.templateSvc.GetTemplateByID(project.TemplateID)
	if err != nil {
		return project, nil, err
	}

	var vars map[string]string
	if project.Variables != nil {
		if err := json.Unmarshal([]byte(*project.Variables), &vars); err != nil {
			return project, nil, err
		}
	}

	files, err := s.GenerateProjectFiles(tmpl, vars)
	return project, files, err
}

// UpdateProject 更新项目基本信息
func (s *ProjectService) UpdateProject(id int64, tenantID int64, updates map[string]interface{}) error {
	db := cfg.GetDB()
	updates["update_time"] = time.Now().UnixMilli()
	return db.Table("gen_project").
		Where("id = ? AND tenant_id = ?", id, tenantID).
		Updates(updates).Error
}

// ImportProjectRequest 从 Git 导入项目请求
type ImportProjectRequest struct {
	Name        string `json:"name" binding:"required"`
	Code        string `json:"code" binding:"required"`
	Description string `json:"description"`
	RepoURL     string `json:"repo_url" binding:"required"`
	Branch      string `json:"branch"`
}

// ImportProject 从 Git 仓库导入项目
func (s *ProjectService) ImportProject(req *ImportProjectRequest, adminID, tenantID int64) (*GenProject, error) {
	if req.Branch == "" {
		req.Branch = "main"
	}

	// 创建临时目录用于 clone
	tmpDir := filepath.Join(os.TempDir(), fmt.Sprintf("admin-import-%d", time.Now().UnixMilli()))
	defer os.RemoveAll(tmpDir)

	// 注入 Git 凭据
	cloneURL, err := injectGitCredentials(req.RepoURL)
	if err != nil {
		return nil, fmt.Errorf("Git 认证失败: %v", err)
	}

	// git clone
	cmd := exec.Command("git", "clone", "--depth", "1", "-b", req.Branch, cloneURL, tmpDir)
	if out, err := cmd.CombinedOutput(); err != nil {
		return nil, fmt.Errorf("git clone 失败: %s", string(out))
	}

	// 检测语言和框架
	language, framework := detectProjectLanguage(tmpDir)

	project := &GenProject{
		Name:        req.Name,
		Code:        req.Code,
		Description: req.Description,
		Language:    language,
		Framework:   framework,
		RepoURL:     req.RepoURL,
		Branch:      req.Branch,
		AdminID:     adminID,
		TenantID:    tenantID,
		Status:      1,
		CreateTime:  time.Now().UnixMilli(),
		UpdateTime:  time.Now().UnixMilli(),
	}

	db := cfg.GetDB()
	if err := db.Table("gen_project").Create(project).Error; err != nil {
		return nil, err
	}

	return project, nil
}

// injectGitCredentials 根据 repoURL 匹配 sys_git_config，注入认证信息
func injectGitCredentials(repoURL string) (string, error) {
	db := cfg.GetDB()
	var configs []map[string]interface{}
	db.Table("sys_git_config").Where("status = 1").Find(&configs)

	for _, c := range configs {
		baseURL, _ := c["base_url"].(string)
		if baseURL == "" || !strings.Contains(repoURL, strings.TrimSuffix(baseURL, "/")) {
			continue
		}
		accessToken, _ := c["access_token"].(string)
		if accessToken == "" {
			continue
		}
		platform, _ := c["platform"].(string)
		switch platform {
		case "gitlab":
			if strings.HasPrefix(repoURL, "https://") {
				return strings.Replace(repoURL, "https://",
					fmt.Sprintf("https://oauth2:%s@", accessToken), 1), nil
			}
			if strings.HasPrefix(repoURL, "http://") {
				return strings.Replace(repoURL, "http://",
					fmt.Sprintf("http://oauth2:%s@", accessToken), 1), nil
			}
		case "github":
			if strings.HasPrefix(repoURL, "https://") {
				return strings.Replace(repoURL, "https://",
					fmt.Sprintf("https://%s@", accessToken), 1), nil
			}
		case "gitee":
			if strings.HasPrefix(repoURL, "https://") {
				return strings.Replace(repoURL, "https://",
					fmt.Sprintf("https://%s@", accessToken), 1), nil
			}
		}
	}

	// 没有匹配的 Git 配置，返回原始 URL（公开仓库可能不需要认证）
	return repoURL, nil
}

// detectProjectLanguage 从项目文件检测语言和框架
func detectProjectLanguage(dir string) (string, string) {
	// Java / Spring Boot
	if _, err := os.Stat(filepath.Join(dir, "pom.xml")); err == nil {
		return "java", "spring-boot"
	}
	if _, err := os.Stat(filepath.Join(dir, "build.gradle")); err == nil {
		return "java", "spring-boot"
	}

	// Go
	if _, err := os.Stat(filepath.Join(dir, "go.mod")); err == nil {
		// 检测框架
		content, _ := os.ReadFile(filepath.Join(dir, "go.mod"))
		mod := string(content)
		if strings.Contains(mod, "gin-gonic") {
			return "go", "gin"
		}
		if strings.Contains(mod, "go-kratos") {
			return "go", "kratos"
		}
		if strings.Contains(mod, "go-zero") {
			return "go", "go-zero"
		}
		return "go", "go"
	}

	// PHP / Laravel
	if _, err := os.Stat(filepath.Join(dir, "composer.json")); err == nil {
		content, _ := os.ReadFile(filepath.Join(dir, "composer.json"))
		composer := string(content)
		if strings.Contains(composer, "laravel") {
			return "php", "laravel"
		}
		if strings.Contains(composer, "symfony") {
			return "php", "symfony"
		}
		if strings.Contains(composer, "thinkphp") {
			return "php", "thinkphp"
		}
		return "php", "php"
	}

	// Python
	if _, err := os.Stat(filepath.Join(dir, "requirements.txt")); err == nil {
		content, _ := os.ReadFile(filepath.Join(dir, "requirements.txt"))
		reqs := string(content)
		if strings.Contains(reqs, "fastapi") {
			return "python", "fastapi"
		}
		if strings.Contains(reqs, "flask") {
			return "python", "flask"
		}
		if strings.Contains(reqs, "django") {
			return "python", "django"
		}
		return "python", "python"
	}
	if _, err := os.Stat(filepath.Join(dir, "pyproject.toml")); err == nil {
		return "python", "python"
	}

	// Node.js / Vue / React
	if _, err := os.Stat(filepath.Join(dir, "package.json")); err == nil {
		content, _ := os.ReadFile(filepath.Join(dir, "package.json"))
		pkg := string(content)
		if strings.Contains(pkg, "vue") {
			return "javascript", "vue"
		}
		if strings.Contains(pkg, "react") {
			return "javascript", "react"
		}
		if strings.Contains(pkg, "next") {
			return "javascript", "next.js"
		}
		if strings.Contains(pkg, "express") || strings.Contains(pkg, "koa") {
			return "node", "express"
		}
		if strings.Contains(pkg, "nestjs") || strings.Contains(pkg, "@nestjs") {
			return "node", "nestjs"
		}
		return "node", "node"
	}

	return "unknown", "unknown"
}
