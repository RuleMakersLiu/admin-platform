package service

import (
	"admin-deploy/internal/config"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/docker/docker/api/types"
	"github.com/docker/docker/api/types/container"
	"github.com/docker/docker/client"
	"github.com/spf13/viper"
)

// TestTask 测试任务
type TestTask struct {
	ID          int64    `json:"id"`
	TaskNo      string   `json:"task_no"`
	ProjectID   int64    `json:"project_id"`
	Type        string   `json:"type"`
	DockerImage string   `json:"docker_image"`
	TestCmd     string   `json:"test_cmd"`
	Status      int      `json:"status"`
	Progress    int      `json:"progress"`
	TotalCases  int      `json:"total_cases"`
	PassedCases int      `json:"passed_cases"`
	FailedCases int      `json:"failed_cases"`
	Coverage    *float64 `json:"coverage"`
	Log         string   `json:"log"`
	ErrorMsg    string   `json:"error_msg"`
	ResultJSON  string   `json:"result_json"`
	Duration    int      `json:"duration"`
	AdminID     int64    `json:"admin_id"`
	TenantID    int64    `json:"tenant_id"`
	StartTime   int64    `json:"start_time"`
	EndTime     int64    `json:"end_time"`
	CreateTime  int64    `json:"create_time"`
	UpdateTime  int64    `json:"update_time"`
}

// TestConfig 测试配置
type TestConfig struct {
	DockerImage string `json:"docker_image"`
	TestCmd     string `json:"test_cmd"`
	CoverageCmd string `json:"coverage_cmd"`
}

// TestResult 测试结果
type TestResult struct {
	TotalCases  int                    `json:"total_cases"`
	PassedCases int                    `json:"passed_cases"`
	FailedCases int                    `json:"failed_cases"`
	Coverage    float64                `json:"coverage"`
	Suites      []TestSuite            `json:"suites"`
	Raw         map[string]interface{} `json:"raw"`
}

// TestSuite 测试套件
type TestSuite struct {
	Name   string     `json:"name"`
	Cases  []TestCase `json:"cases"`
	Status string     `json:"status"`
}

// TestCase 测试用例
type TestCase struct {
	Name     string  `json:"name"`
	Status   string  `json:"status"`
	Duration float64 `json:"duration"`
	Error    string  `json:"error,omitempty"`
}

// TestService 测试服务
type TestService struct {
	docker      *client.Client
	cancelFuncs sync.Map
}

// NewTestService 创建测试服务
func NewTestService() *TestService {
	return &TestService{
		docker: config.GetDocker(),
	}
}

// CreateTestTask 创建测试任务
func (s *TestService) CreateTestTask(projectID int64, testType string, dockerImage, testCmd string, adminID, tenantID int64) (*TestTask, error) {
	taskNo := fmt.Sprintf("TEST%s%d", time.Now().Format("20060102150405"), adminID)

	if dockerImage == "" || testCmd == "" {
		defaultCfg := s.getDefaultTestConfig(projectID)
		if dockerImage == "" {
			dockerImage = defaultCfg.DockerImage
		}
		if testCmd == "" {
			testCmd = defaultCfg.TestCmd
		}
	}

	if testType == "" {
		testType = "unit"
	}

	task := &TestTask{
		TaskNo:      taskNo,
		ProjectID:   projectID,
		Type:        testType,
		DockerImage: dockerImage,
		TestCmd:     testCmd,
		Status:      1,
		AdminID:     adminID,
		TenantID:    tenantID,
		CreateTime:  time.Now().UnixMilli(),
		UpdateTime:  time.Now().UnixMilli(),
	}

	db := config.GetDB()
	if err := db.Table("test_task").Create(task).Error; err != nil {
		return nil, err
	}

	return task, nil
}

// ExecuteTestTask 执行测试任务
func (s *TestService) ExecuteTestTask(taskID int64) error {
	db := config.GetDB()

	var task TestTask
	if err := db.Table("test_task").Where("id = ?", taskID).First(&task).Error; err != nil {
		return err
	}

	db.Table("test_task").Where("id = ?", taskID).Updates(map[string]interface{}{
		"status":      2,
		"start_time":  time.Now().UnixMilli(),
		"update_time": time.Now().UnixMilli(),
	})

	s.addTestLog(taskID, "开始执行", fmt.Sprintf("测试类型: %s, 镜像: %s", task.Type, task.DockerImage))
	s.updateTestProgress(taskID, 5)

	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Minute)
	s.cancelFuncs.Store(taskID, cancel)
	defer func() {
		s.cancelFuncs.Delete(taskID)
		cancel()
	}()

	s.addTestLog(taskID, "准备代码", "获取项目代码")
	s.updateTestProgress(taskID, 10)

	projectDir, cleanup, err := s.prepareProjectDir(ctx, task.ProjectID)
	if err != nil {
		s.failTestTask(taskID, fmt.Sprintf("准备代码失败: %v", err))
		return err
	}
	defer cleanup()

	s.addTestLog(taskID, "代码就绪", projectDir)
	s.updateTestProgress(taskID, 20)

	s.addTestLog(taskID, "启动测试", fmt.Sprintf("使用镜像: %s", task.DockerImage))
	s.updateTestProgress(taskID, 30)

	output, err := s.runTestContainer(ctx, task.DockerImage, projectDir, task.TestCmd)
	s.updateTestProgress(taskID, 80)

	s.addTestLog(taskID, "测试输出", truncateString(output, 50000))

	if err != nil {
		s.addTestLog(taskID, "测试失败", err.Error())
		result := s.parseTestOutput(output)
		resultJSON, _ := json.Marshal(result)
		s.finishTestTask(taskID, 4, result, string(resultJSON))
		return fmt.Errorf("测试执行失败: %w", err)
	}

	s.addTestLog(taskID, "解析结果", "分析测试输出")
	s.updateTestProgress(taskID, 90)

	result := s.parseTestOutput(output)
	resultJSON, _ := json.Marshal(result)

	s.addTestLog(taskID, "测试完成", fmt.Sprintf("通过: %d/%d, 覆盖率: %.1f%%",
		result.PassedCases, result.TotalCases, result.Coverage))

	s.updateProjectTestInfo(task.ProjectID, result, task.TenantID)

	status := 3
	if result.FailedCases > 0 {
		status = 4
	}
	s.finishTestTask(taskID, status, result, string(resultJSON))

	s.updateTestProgress(taskID, 100)
	return nil
}

func (s *TestService) prepareProjectDir(ctx context.Context, projectID int64) (string, func(), error) {
	// 每次测试用独立沙箱目录，带时间戳，避免冲突
	sandboxDir := filepath.Join(viper.GetString("deploy.work_dir"), "sandbox",
		fmt.Sprintf("test_%d_%d", projectID, time.Now().UnixMilli()))

	db := config.GetDB()
	var project map[string]interface{}
	db.Table("gen_project").Where("id = ?", projectID).First(&project)

	repoURL, _ := project["repo_url"].(string)
	branch, _ := project["branch"].(string)
	if branch == "" {
		branch = "main"
	}

	if repoURL == "" {
		return "", func() {}, fmt.Errorf("项目未关联 Git 仓库，请先在项目列表中设置仓库地址")
	}

	// 查找匹配的 Git 配置获取 access_token
	cloneURL, err := s.injectGitCredentials(repoURL)
	if err != nil {
		return "", func() {}, fmt.Errorf("Git 认证失败: %v", err)
	}

	// 独立沙箱：每次全新 clone
	if err := os.MkdirAll(filepath.Dir(sandboxDir), 0755); err != nil {
		return "", func() {}, err
	}

	cloneCmd := exec.CommandContext(ctx, "git", "clone", "--depth", "1", "-b", branch, cloneURL, sandboxDir)
	if out, err := cloneCmd.CombinedOutput(); err != nil {
		return "", func() {}, fmt.Errorf("git clone 失败: %s", string(out))
	}

	// 返回沙箱目录和清理函数
	cleanup := func() {
		os.RemoveAll(sandboxDir)
	}

	return sandboxDir, cleanup, nil
}

// injectGitCredentials 根据 repoURL 匹配 sys_git_config，注入认证信息
func (s *TestService) injectGitCredentials(repoURL string) (string, error) {
	db := config.GetDB()
	var configs []map[string]interface{}
	db.Table("sys_git_config").Where("status = 1").Find(&configs)

	for _, cfg := range configs {
		baseURL, _ := cfg["base_url"].(string)
		if baseURL == "" || !strings.Contains(repoURL, strings.TrimSuffix(baseURL, "/")) {
			continue
		}

		accessToken, _ := cfg["access_token"].(string)
		if accessToken == "" {
			continue
		}

		platform, _ := cfg["platform"].(string)
		switch platform {
		case "gitlab":
			// https://host/group/repo.git → https://oauth2:TOKEN@host/group/repo.git
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

	// 没有匹配的 Git 配置，返回原始 URL（公开仓库）
	return repoURL, nil
}

func (s *TestService) runTestContainer(ctx context.Context, image, projectDir, testCmd string) (string, error) {
	_, err := s.docker.ImagePull(ctx, image, types.ImagePullOptions{})
	if err != nil {
		log.Printf("镜像拉取失败(可能已存在): %v", err)
	}

	resp, err := s.docker.ContainerCreate(ctx, &container.Config{
		Image:      image,
		Cmd:        []string{"sh", "-c", testCmd},
		WorkingDir: "/app",
		Tty:        false,
	}, &container.HostConfig{
		Binds: []string{projectDir + ":/app"},
	}, nil, nil, "")
	if err != nil {
		return "", fmt.Errorf("创建测试容器失败: %w", err)
	}

	defer s.docker.ContainerRemove(ctx, resp.ID, container.RemoveOptions{Force: true})

	if err := s.docker.ContainerStart(ctx, resp.ID, container.StartOptions{}); err != nil {
		return "", fmt.Errorf("启动测试容器失败: %w", err)
	}

	statusCh, errCh := s.docker.ContainerWait(ctx, resp.ID, container.WaitConditionNotRunning)
	select {
	case err := <-errCh:
		if err != nil {
			return "", fmt.Errorf("等待容器完成失败: %w", err)
		}
	case <-statusCh:
	}

	out, err := s.docker.ContainerLogs(ctx, resp.ID, container.LogsOptions{
		ShowStdout: true,
		ShowStderr: true,
	})
	if err != nil {
		return "", fmt.Errorf("获取容器日志失败: %w", err)
	}
	defer out.Close()

	data, err := io.ReadAll(out)
	if err != nil {
		return "", fmt.Errorf("读取容器日志失败: %w", err)
	}

	return string(data), nil
}

// ========== 测试输出解析 ==========

func (s *TestService) parseTestOutput(output string) *TestResult {
	if jsonResult := s.parseJSONOutput(output); jsonResult != nil {
		return jsonResult
	}
	if strings.Contains(output, "PASS") || strings.Contains(output, "FAIL") {
		if r := s.parseGoTestOutput(output); r != nil && r.TotalCases > 0 {
			return r
		}
	}
	if strings.Contains(output, "Tests run:") {
		return s.parseJavaTestOutput(output)
	}
	if strings.Contains(output, "passed") || strings.Contains(output, "failed") {
		return s.parsePytestOutput(output)
	}
	if strings.Contains(output, "OK (") {
		return s.parsePHPUnitOutput(output)
	}
	if strings.Contains(output, "Test Suites:") {
		return s.parseJestOutput(output)
	}
	return s.parseGenericOutput(output)
}

func (s *TestService) parseJSONOutput(output string) *TestResult {
	start := strings.Index(output, "{")
	end := strings.LastIndex(output, "}")
	if start == -1 || end == -1 || end <= start {
		return nil
	}

	var raw map[string]interface{}
	if err := json.Unmarshal([]byte(output[start:end+1]), &raw); err != nil {
		return nil
	}

	result := &TestResult{Raw: raw}
	if v, ok := raw["numPassedTests"]; ok {
		result.PassedCases = int(toFloat64(v))
		result.TotalCases = result.PassedCases
	}
	if v, ok := raw["numFailedTests"]; ok {
		result.FailedCases = int(toFloat64(v))
		result.TotalCases += result.FailedCases
	}
	if covData, ok := raw["coverage"]; ok {
		switch v := covData.(type) {
		case float64:
			result.Coverage = v
		case map[string]interface{}:
			if t, ok := v["total"]; ok {
				if lines, ok := t.(map[string]interface{}); ok {
					if pct, ok := lines["pct"]; ok {
						result.Coverage = toFloat64(pct)
					}
				}
			}
		}
	}
	if result.TotalCases > 0 {
		return result
	}
	return nil
}

func (s *TestService) parseGoTestOutput(output string) *TestResult {
	result := &TestResult{}
	passedRe := regexp.MustCompile(`^--- PASS:`)
	failedRe := regexp.MustCompile(`^--- FAIL:`)
	for _, line := range strings.Split(output, "\n") {
		if passedRe.MatchString(line) {
			result.PassedCases++
			result.TotalCases++
		} else if failedRe.MatchString(line) {
			result.FailedCases++
			result.TotalCases++
		}
	}
	covRe := regexp.MustCompile(`coverage:\s+(\d+\.\d+)%`)
	if m := covRe.FindStringSubmatch(output); len(m) > 1 {
		result.Coverage, _ = strconv.ParseFloat(m[1], 64)
	}
	return result
}

func (s *TestService) parseJavaTestOutput(output string) *TestResult {
	result := &TestResult{}
	re := regexp.MustCompile(`Tests run:\s*(\d+),\s*Failures:\s*(\d+),\s*Errors:\s*(\d+)`)
	if m := re.FindStringSubmatch(output); len(m) >= 4 {
		result.TotalCases, _ = strconv.Atoi(m[1])
		result.FailedCases, _ = strconv.Atoi(m[2])
		result.PassedCases = result.TotalCases - result.FailedCases
	}
	return result
}

func (s *TestService) parsePytestOutput(output string) *TestResult {
	result := &TestResult{}
	if m := regexp.MustCompile(`(\d+) passed`).FindStringSubmatch(output); len(m) > 1 {
		result.PassedCases, _ = strconv.Atoi(m[1])
	}
	if m := regexp.MustCompile(`(\d+) failed`).FindStringSubmatch(output); len(m) > 1 {
		result.FailedCases, _ = strconv.Atoi(m[1])
	}
	result.TotalCases = result.PassedCases + result.FailedCases
	covRe := regexp.MustCompile(`(\d+)%`)
	for _, line := range strings.Split(output, "\n") {
		if strings.Contains(line, "coverage") || strings.Contains(line, "TOTAL") {
			if m := covRe.FindStringSubmatch(line); len(m) > 1 {
				result.Coverage, _ = strconv.ParseFloat(m[1], 64)
			}
		}
	}
	return result
}

func (s *TestService) parsePHPUnitOutput(output string) *TestResult {
	result := &TestResult{}
	if m := regexp.MustCompile(`OK \((\d+) tests`).FindStringSubmatch(output); len(m) > 1 {
		result.TotalCases, _ = strconv.Atoi(m[1])
		result.PassedCases = result.TotalCases
		return result
	}
	if m := regexp.MustCompile(`Tests:\s*(\d+).*Failures:\s*(\d+)`).FindStringSubmatch(output); len(m) >= 3 {
		result.TotalCases, _ = strconv.Atoi(m[1])
		result.FailedCases, _ = strconv.Atoi(m[2])
		result.PassedCases = result.TotalCases - result.FailedCases
	}
	return result
}

func (s *TestService) parseJestOutput(output string) *TestResult {
	result := &TestResult{}
	re := regexp.MustCompile(`Tests:\s*(\d+) failed,\s*(\d+) passed,\s*(\d+) total`)
	if m := re.FindStringSubmatch(output); len(m) >= 4 {
		result.FailedCases, _ = strconv.Atoi(m[1])
		result.PassedCases, _ = strconv.Atoi(m[2])
		result.TotalCases, _ = strconv.Atoi(m[3])
	}
	return result
}

func (s *TestService) parseGenericOutput(output string) *TestResult {
	result := &TestResult{}
	for _, line := range strings.Split(output, "\n") {
		upper := strings.ToUpper(line)
		if strings.Contains(upper, "PASS") && !strings.Contains(upper, "FAIL") {
			result.PassedCases++
			result.TotalCases++
		} else if strings.Contains(upper, "FAIL") {
			result.FailedCases++
			result.TotalCases++
		}
	}
	return result
}

// ========== CRUD ==========

// CancelTestTask 取消测试任务
func (s *TestService) CancelTestTask(taskID int64) error {
	if cancelFn, ok := s.cancelFuncs.LoadAndDelete(taskID); ok {
		cancelFn.(context.CancelFunc)()
	}
	db := config.GetDB()
	return db.Table("test_task").Where("id = ?", taskID).Updates(map[string]interface{}{
		"status":      5,
		"update_time": time.Now().UnixMilli(),
	}).Error
}

// GetTestTask 获取测试任务
func (s *TestService) GetTestTask(taskID int64) (*TestTask, error) {
	db := config.GetDB()
	var task TestTask
	err := db.Table("test_task").Where("id = ?", taskID).First(&task).Error
	return &task, err
}

// ListTestTasks 获取测试任务列表
func (s *TestService) ListTestTasks(projectID int64, adminID int64, page, pageSize int) ([]TestTask, int64, error) {
	db := config.GetDB()
	var total int64
	var tasks []TestTask

	query := db.Table("test_task")
	if projectID > 0 {
		query = query.Where("project_id = ?", projectID)
	}
	if adminID > 0 {
		query = query.Where("admin_id = ?", adminID)
	}

	query.Count(&total)
	offset := (page - 1) * pageSize
	err := query.Order("create_time desc").
		Offset(offset).Limit(pageSize).
		Find(&tasks).Error

	return tasks, total, err
}

// ========== 辅助方法 ==========

func (s *TestService) addTestLog(taskID int64, step, msg string) {
	db := config.GetDB()
	db.Table("test_task").Where("id = ?", taskID).UpdateColumn("log",
		fmt.Sprintf("%s[%s] %s: %s\n",
			s.getCurrentLog(taskID),
			time.Now().Format("15:04:05"), step, msg))
}

func (s *TestService) updateTestProgress(taskID int64, progress int) {
	db := config.GetDB()
	db.Table("test_task").Where("id = ?", taskID).Update("progress", progress)
}

func (s *TestService) failTestTask(taskID int64, errMsg string) {
	db := config.GetDB()
	db.Table("test_task").Where("id = ?", taskID).Updates(map[string]interface{}{
		"status":      4,
		"error_msg":   truncateString(errMsg, 1000),
		"end_time":    time.Now().UnixMilli(),
		"update_time": time.Now().UnixMilli(),
	})
}

func (s *TestService) finishTestTask(taskID int64, status int, result *TestResult, resultJSON string) {
	db := config.GetDB()
	updates := map[string]interface{}{
		"status":       status,
		"total_cases":  result.TotalCases,
		"passed_cases": result.PassedCases,
		"failed_cases": result.FailedCases,
	// MySQL json column rejects empty string — use empty object
	rj := truncateString(resultJSON, 50000)
	if rj == "" {
		rj = "{}"
	}

	updates := map[string]interface{}{
		"status":       status,
		"total_cases":  result.TotalCases,
		"passed_cases": result.PassedCases,
		"failed_cases": result.FailedCases,
		"result_json":  rj,
		"end_time":     time.Now().UnixMilli(),
		"update_time":  time.Now().UnixMilli(),
	}
	if result.Coverage > 0 {
		updates["coverage"] = result.Coverage
	}
	db.Table("test_task").Where("id = ?", taskID).Updates(updates)
}

func (s *TestService) updateProjectTestInfo(projectID int64, result *TestResult, tenantID int64) {
	db := config.GetDB()
	updates := map[string]interface{}{
		"last_test_time": time.Now().UnixMilli(),
	}
	if result.TotalCases > 0 {
		rate := float64(result.PassedCases) / float64(result.TotalCases) * 100
		updates["test_pass_rate"] = rate
	}
	db.Table("gen_project").Where("id = ? AND tenant_id = ?", projectID, tenantID).Updates(updates)
}

func (s *TestService) getDefaultTestConfig(projectID int64) *TestConfig {
	db := config.GetDB()
	var project map[string]interface{}
	if err := db.Table("gen_project").Where("id = ?", projectID).First(&project).Error; err != nil {
		return &TestConfig{}
	}

	templateID := project["template_id"]
	if templateID == nil {
		return &TestConfig{}
	}

	var tmpl map[string]interface{}
	if err := db.Table("gen_project_template").Where("id = ?", templateID).First(&tmpl).Error; err != nil {
		return &TestConfig{}
	}

	testConfigStr, _ := tmpl["test_config"].(string)
	if testConfigStr == "" {
		return &TestConfig{}
	}

	var cfg TestConfig
	if err := json.Unmarshal([]byte(testConfigStr), &cfg); err != nil {
		return &TestConfig{}
	}
	return &cfg
}

func (s *TestService) getCurrentLog(taskID int64) string {
	db := config.GetDB()
	var task TestTask
	db.Table("test_task").Where("id = ?", taskID).First(&task)
	return task.Log
}

func truncateString(s string, maxLen int) string {
	if len(s) <= maxLen {
		return s
	}
	return s[:maxLen] + "...(truncated)"
}

func toFloat64(v interface{}) float64 {
	switch val := v.(type) {
	case float64:
		return val
	case int:
		return float64(val)
	case string:
		f, _ := strconv.ParseFloat(val, 64)
		return f
	default:
		return 0
	}
}
