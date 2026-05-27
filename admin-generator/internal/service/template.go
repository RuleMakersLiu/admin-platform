package service

import (
	cfg "admin-generator/internal/config"
	"encoding/json"
	"fmt"
	"log"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"

	"gorm.io/gorm"
)

// ProjectTemplate 项目模板
type ProjectTemplate struct {
	ID          int64  `json:"id"`
	Name        string `json:"name"`
	Code        string `json:"code"`
	Language    string `json:"language"`
	Framework   string `json:"framework"`
	Version     string `json:"version"`
	Description string `json:"description"`
	Structure   string `json:"structure"`
	Variables   string `json:"variables"`
	TestConfig  string `json:"test_config"`
	BuildConfig string `json:"build_config"`
	Icon        string `json:"icon"`
	Sort        int    `json:"sort"`
	IsBuiltin   int    `json:"is_builtin"`
	TenantID    int64  `json:"tenant_id"`
	Status      int    `json:"status"`
	CreateTime  int64  `json:"create_time"`
	UpdateTime  int64  `json:"update_time"`
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
	ID              int64    `json:"id"`
	Name            string   `json:"name"`
	Code            string   `json:"code"`
	Description     string   `json:"description"`
	TemplateID      int64    `json:"template_id"`
	Language        string   `json:"language"`
	Framework       string   `json:"framework"`
	Variables       *string  `json:"variables"`
	ConfigJSON      *string  `json:"config_json"`
	RepoURL         string   `json:"repo_url"`
	Branch          string   `json:"branch"`
	DeployProjectID *int64   `json:"deploy_project_id"`
	TestPassRate    *float64 `json:"test_pass_rate"`
	LastTestTime    *int64   `json:"last_test_time"`
	GitConfigID     *int64   `json:"git_config_id"`
	LlmConfigID     *int64   `json:"llm_config_id"`
	AdminID         int64    `json:"admin_id"`
	TenantID        int64    `json:"tenant_id"`
	Status          int      `json:"status"`
	CreateTime      int64    `json:"create_time"`
	UpdateTime      int64    `json:"update_time"`
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
	Name           string            `json:"name" binding:"required"`
	Code           string            `json:"code" binding:"required"`
	Description    string            `json:"description"`
	TemplateID     int64             `json:"template_id" binding:"required"`
	Variables      map[string]string `json:"variables"`
	RepoURL        string            `json:"repo_url"`
	Branch         string            `json:"branch"`
	TenantScopeIDs []int64           `json:"tenant_scope_ids"`
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
	scopeIDs, err := s.normalizeProjectTenantScopes(adminID, tenantID, req.TenantScopeIDs)
	if err != nil {
		return nil, nil, err
	}
	if err := replaceProjectTenantScopes(db, project.ID, scopeIDs, adminID); err != nil {
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

	// Also include tenant_id=0 projects (created before header injection was fixed)
	query := db.Table("gen_project").Where("tenant_id = ? OR tenant_id = 0", tenantID)
	if adminID > 0 {
		query = query.Where("admin_id = ? OR admin_id = 0", adminID)
	}
	// Filter out soft-deleted
	query = query.Where("status != 0")

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
	query := db.Table("gen_project").Where("id = ?", id)
	if tenantID > 0 {
		query = query.Where("tenant_id = ? OR tenant_id = 0", tenantID)
	}
	err := query.First(&project).Error
	return &project, err
}

// DeleteProject 删除项目
func (s *ProjectService) DeleteProject(id int64, tenantID int64) error {
	db := cfg.GetDB()
	query := db.Table("gen_project").Where("id = ?", id)
	if tenantID > 0 {
		query = query.Where("tenant_id = ? OR tenant_id = 0", tenantID)
	}
	return query.Update("status", 0).Error
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

	// 导入的项目没有 template_id，尝试从 Git 重新 clone 获取文件
	if project.TemplateID == 0 {
		files, err := s.getImportedProjectFiles(project)
		return project, files, err
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

// getImportedProjectFiles 从 Git 仓库 clone 获取项目文件（用于预览/下载）
func (s *ProjectService) getImportedProjectFiles(project *GenProject) (map[string]string, error) {
	if project.RepoURL == "" {
		return nil, fmt.Errorf("导入项目未关联仓库，无法获取文件")
	}

	tmpDir := filepath.Join(os.TempDir(), fmt.Sprintf("admin-preview-%d", time.Now().UnixMilli()))
	defer os.RemoveAll(tmpDir)

	cloneURL, err := injectGitCredentials(project.RepoURL)
	if err != nil {
		return nil, err
	}

	branch := project.Branch
	if branch == "" {
		branch = "main"
	}

	if out, err := cloneRepository(cloneURL, branch, tmpDir); err != nil {
		return nil, fmt.Errorf("git clone 失败: %s", string(out))
	}

	files := make(map[string]string)
	maxSize := int64(500 * 1024) // 单文件最大 500KB
	fileCount := 0
	maxFiles := 200

	filepath.Walk(tmpDir, func(path string, info os.FileInfo, err error) error {
		if err != nil || info.IsDir() || fileCount >= maxFiles {
			return nil
		}
		// 跳过 .git 目录
		if strings.Contains(path, string(filepath.Separator)+".git"+string(filepath.Separator)) ||
			strings.HasSuffix(path, string(filepath.Separator)+".git") {
			return nil
		}
		if info.Size() > maxSize {
			return nil
		}

		relPath, err := filepath.Rel(tmpDir, path)
		if err != nil {
			return nil
		}
		content, err := os.ReadFile(path)
		if err != nil {
			return nil
		}

		// 跳过二进制文件
		if !isTextContent(content) {
			return nil
		}

		files[relPath] = string(content)
		fileCount++
		return nil
	})

	return files, nil
}

// isTextContent 简单判断内容是否为文本
func isTextContent(data []byte) bool {
	if len(data) == 0 {
		return true
	}
	// 检查前 512 字节是否有 NULL 字符（二进制标志）
	checkLen := len(data)
	if checkLen > 512 {
		checkLen = 512
	}
	for i := 0; i < checkLen; i++ {
		if data[i] == 0 {
			return false
		}
	}
	return true
}

// UpdateProject 更新项目基本信息
func (s *ProjectService) UpdateProject(id int64, tenantID int64, updates map[string]interface{}) error {
	db := cfg.GetDB()
	updates["update_time"] = time.Now().UnixMilli()
	query := db.Table("gen_project").Where("id = ?", id)
	if tenantID > 0 {
		query = query.Where("tenant_id = ? OR tenant_id = 0", tenantID)
	}
	return query.Updates(updates).Error
}

func (s *ProjectService) UpdateProjectTenantScopes(id int64, tenantID int64, tenantScopeIDs []int64, adminID int64) error {
	db := cfg.GetDB()
	query := db.Table("gen_project").Where("id = ?", id)
	if tenantID > 0 {
		query = query.Where("tenant_id = ? OR tenant_id = 0", tenantID)
	}
	var count int64
	if err := query.Count(&count).Error; err != nil {
		return err
	}
	if count == 0 {
		return fmt.Errorf("项目不存在或无权限")
	}
	scopeIDs, err := s.normalizeProjectTenantScopes(adminID, tenantID, tenantScopeIDs)
	if err != nil {
		return err
	}
	return replaceProjectTenantScopes(db, id, scopeIDs, adminID)
}

// ImportProjectRequest 从 Git 导入项目请求
type ImportProjectRequest struct {
	Name           string  `json:"name" binding:"required"`
	Code           string  `json:"code" binding:"required"`
	Description    string  `json:"description"`
	RepoURL        string  `json:"repo_url" binding:"required"`
	Branch         string  `json:"branch"`
	GitConfigID    *int64  `json:"git_config_id"`
	TenantScopeIDs []int64 `json:"tenant_scope_ids"`
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
	if out, err := cloneRepository(cloneURL, req.Branch, tmpDir); err != nil {
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
		GitConfigID: req.GitConfigID,
		TenantID:    tenantID,
		Status:      1,
		CreateTime:  time.Now().UnixMilli(),
		UpdateTime:  time.Now().UnixMilli(),
	}

	db := cfg.GetDB()
	if err := db.Table("gen_project").Create(project).Error; err != nil {
		return nil, err
	}
	scopeIDs, err := s.normalizeProjectTenantScopes(adminID, tenantID, req.TenantScopeIDs)
	if err != nil {
		return nil, err
	}
	if err := replaceProjectTenantScopes(db, project.ID, scopeIDs, adminID); err != nil {
		return nil, err
	}

	return project, nil
}

func (s *ProjectService) normalizeProjectTenantScopes(adminID int64, defaultTenantID int64, requested []int64) ([]int64, error) {
	if len(requested) == 0 {
		return []int64{defaultTenantID}, nil
	}

	db := cfg.GetDB()
	allowed := map[int64]bool{}
	var superCount int64
	if adminID > 0 {
		db.Table("sys_admin").
			Joins("JOIN sys_admin_group ON sys_admin_group.id = sys_admin.admin_group_id").
			Where("sys_admin.id = ? AND sys_admin.is_deleted = 0 AND sys_admin_group.status = 1 AND sys_admin_group.is_super = 1", adminID).
			Count(&superCount)
	}

	if superCount > 0 {
		var tenantIDs []int64
		if err := db.Table("sys_tenant").
			Where("status = 1 AND is_deleted = 0").
			Pluck("id", &tenantIDs).Error; err != nil {
			return nil, err
		}
		for _, tenantID := range tenantIDs {
			allowed[tenantID] = true
		}
		allowed[0] = true
	} else {
		var tenantIDs []int64
		if adminID > 0 {
			if err := db.Table("sys_admin_tenant").
				Where("admin_id = ?", adminID).
				Pluck("tenant_id", &tenantIDs).Error; err != nil {
				return nil, err
			}
		}
		for _, tenantID := range tenantIDs {
			allowed[tenantID] = true
		}
		if defaultTenantID > 0 {
			allowed[defaultTenantID] = true
		}
	}

	seen := map[int64]bool{}
	var normalized []int64
	for _, tenantID := range requested {
		if tenantID < 0 {
			return nil, fmt.Errorf("租户范围不合法")
		}
		if !allowed[tenantID] {
			return nil, fmt.Errorf("无权配置租户: %d", tenantID)
		}
		if !seen[tenantID] {
			seen[tenantID] = true
			normalized = append(normalized, tenantID)
		}
	}
	if len(normalized) == 0 && defaultTenantID > 0 {
		normalized = append(normalized, defaultTenantID)
	}
	return normalized, nil
}

func replaceProjectTenantScopes(db *gorm.DB, projectID int64, tenantScopeIDs []int64, adminID int64) error {
	now := time.Now().UnixMilli()
	seen := map[int64]bool{}
	if err := db.Table("project_tenant_scope").Where("project_id = ?", projectID).Delete(map[string]interface{}{}).Error; err != nil {
		return err
	}
	for _, tenantID := range tenantScopeIDs {
		if tenantID < 0 || seen[tenantID] {
			continue
		}
		seen[tenantID] = true
		if err := db.Table("project_tenant_scope").Create(map[string]interface{}{
			"project_id":  projectID,
			"tenant_id":   tenantID,
			"enabled":     1,
			"created_by":  adminID,
			"create_time": now,
			"update_time": now,
		}).Error; err != nil {
			return err
		}
	}
	return nil
}

func cloneRepository(cloneURL, branch, tmpDir string) ([]byte, error) {
	args := []string{"clone", "--depth", "1"}
	if branch != "" {
		args = append(args, "-b", branch)
	}
	args = append(args, cloneURL, tmpDir)
	out, err := exec.Command("git", args...).CombinedOutput()
	if err == nil || branch == "" {
		return out, err
	}

	log.Printf("git clone branch %s failed, retry default branch: %s", branch, string(out))
	os.RemoveAll(tmpDir)
	if mkdirErr := os.MkdirAll(tmpDir, 0755); mkdirErr != nil {
		return out, mkdirErr
	}
	return exec.Command("git", "clone", "--depth", "1", cloneURL, tmpDir).CombinedOutput()
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
		content, _ := os.ReadFile(filepath.Join(dir, "pom.xml"))
		pom := string(content)
		if strings.Contains(pom, "spring-boot") {
			return "java", "spring-boot"
		}
		return "java", "maven"
	}
	if _, err := os.Stat(filepath.Join(dir, "build.gradle")); err == nil {
		return "java", "gradle"
	}
	if _, err := os.Stat(filepath.Join(dir, "build.gradle.kts")); err == nil {
		return "java", "gradle"
	}

	// Go
	if _, err := os.Stat(filepath.Join(dir, "go.mod")); err == nil {
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
		if strings.Contains(mod, "fiber") {
			return "go", "fiber"
		}
		if strings.Contains(mod, "echo") {
			return "go", "echo"
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
		if strings.Contains(composer, "thinkphp") || strings.Contains(composer, "topthink") {
			return "php", "thinkphp"
		}
		if strings.Contains(composer, "yii") {
			return "php", "yii"
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
		content, _ := os.ReadFile(filepath.Join(dir, "pyproject.toml"))
		toml := string(content)
		if strings.Contains(toml, "fastapi") {
			return "python", "fastapi"
		}
		if strings.Contains(toml, "flask") {
			return "python", "flask"
		}
		if strings.Contains(toml, "django") {
			return "python", "django"
		}
		return "python", "python"
	}
	if _, err := os.Stat(filepath.Join(dir, "setup.py")); err == nil {
		return "python", "python"
	}

	// Node.js / Vue / React
	if _, err := os.Stat(filepath.Join(dir, "package.json")); err == nil {
		content, _ := os.ReadFile(filepath.Join(dir, "package.json"))
		pkg := string(content)
		if strings.Contains(pkg, "\"vue\"") || strings.Contains(pkg, "\"vue\"") {
			if strings.Contains(pkg, "nuxt") {
				return "javascript", "nuxt"
			}
			return "javascript", "vue"
		}
		if strings.Contains(pkg, "\"react\"") {
			if strings.Contains(pkg, "next") {
				return "javascript", "next.js"
			}
			return "javascript", "react"
		}
		if strings.Contains(pkg, "\"angular\"") || strings.Contains(pkg, "\"@angular/core\"") {
			return "javascript", "angular"
		}
		if strings.Contains(pkg, "express") {
			return "node", "express"
		}
		if strings.Contains(pkg, "koa") {
			return "node", "koa"
		}
		if strings.Contains(pkg, "nestjs") || strings.Contains(pkg, "@nestjs") {
			return "node", "nestjs"
		}
		return "node", "node"
	}

	// Rust
	if _, err := os.Stat(filepath.Join(dir, "Cargo.toml")); err == nil {
		return "rust", "rust"
	}

	// C# / .NET
	if _, err := os.Stat(filepath.Join(dir, "*.sln")); err == nil {
		return "csharp", "dotnet"
	}

	return "unknown", "unknown"
}
