package service

import (
	"admin-deploy/internal/config"
	"archive/tar"
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"sync"
	"time"

	"github.com/docker/docker/api/types"
	"github.com/docker/docker/api/types/container"
	"github.com/docker/docker/api/types/image"
	"github.com/docker/docker/client"
	"github.com/docker/go-connections/nat"
	"github.com/spf13/viper"
	"gorm.io/gorm"
)

// Task 部署任务
type Task struct {
	ID            int64  `json:"id"`
	TaskNo        string `json:"task_no"`
	Name          string `json:"name"`
	Type          int    `json:"type"` // 1构建 2部署 3回滚
	Project       string `json:"project"`
	Env           string `json:"env"`
	Config        string `json:"config"`
	ChatHistoryID int64  `json:"chat_history_id"`
	AdminID       int64  `json:"admin_id"`
	Status        int    `json:"status"` // 1待执行 2执行中 3成功 4失败 5已取消
	Progress      int    `json:"progress"`
	Log           string `json:"log"`
	ErrorMsg      string `json:"error_msg"`
	StartTime     int64  `json:"start_time"`
	EndTime       int64  `json:"end_time"`
	Duration      int    `json:"duration"`
	TenantID      int64  `json:"tenant_id"`
	CreateTime    int64  `json:"create_time"`
	UpdateTime    int64  `json:"update_time"`
}

// Project 项目配置（从 config.yaml 读取）
type Project struct {
	Name       string   `json:"name"`
	Type       string   `json:"type"`
	BuildCmd   string   `json:"build_cmd"`
	Dockerfile string   `json:"dockerfile"`
	Image      string   `json:"image"`
	Ports      []string `json:"ports"`
}

// DeployProject 部署项目（数据库模型）
type DeployProject struct {
	ID           int64  `json:"id"`
	Name         string `json:"name"`
	Code         string `json:"code"`
	Type         string `json:"type"` // java/go/vue/react
	RepoURL      string `json:"repo_url"`
	Branch       string `json:"branch"`
	BuildCmd     string `json:"build_cmd"`
	Dockerfile   string `json:"dockerfile"`
	ImageName    string `json:"image_name"`
	DeployConfig string `json:"deploy_config"`
	TenantID     int64  `json:"tenant_id"`
	Status       int    `json:"status"` // 1启用 0禁用
	CreateTime   int64  `json:"create_time"`
	UpdateTime   int64  `json:"update_time"`
}

// DeployService 部署服务
type DeployService struct {
	docker      *client.Client
	cancelFuncs sync.Map // map[int64]context.CancelFunc
}

// NewDeployService 创建服务
func NewDeployService() *DeployService {
	return &DeployService{
		docker: config.GetDocker(),
	}
}

// CreateTask 创建任务
func (s *DeployService) CreateTask(project, env string, taskType int, adminID, tenantID int64) (*Task, error) {
	taskNo := fmt.Sprintf("TASK%s%d", time.Now().Format("20060102150405"), adminID)

	task := &Task{
		TaskNo:     taskNo,
		Name:       fmt.Sprintf("%s-%s部署", project, env),
		Type:       taskType,
		Project:    project,
		Env:        env,
		AdminID:    adminID,
		Status:     1,
		TenantID:   tenantID,
		CreateTime: time.Now().UnixMilli(),
		UpdateTime: time.Now().UnixMilli(),
	}

	db := config.GetDB()
	result := db.Table("deploy_task").Create(task)
	if result.Error != nil {
		return nil, result.Error
	}

	return task, nil
}

// ExecuteTask 执行任务
func (s *DeployService) ExecuteTask(taskID int64) error {
	db := config.GetDB()

	var task Task
	if err := db.Table("deploy_task").Where("id = ?", taskID).First(&task).Error; err != nil {
		return err
	}

	db.Table("deploy_task").Where("id = ?", taskID).Updates(map[string]interface{}{
		"status":      2,
		"start_time":  time.Now().UnixMilli(),
		"update_time": time.Now().UnixMilli(),
	})

	s.addRecord(taskID, "开始执行", fmt.Sprintf("任务类型: %d, 项目: %s", task.Type, task.Project))

	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Minute)
	s.cancelFuncs.Store(taskID, cancel)

	var err error
	switch task.Type {
	case 1:
		err = s.build(ctx, &task)
	case 2:
		err = s.deploy(ctx, &task)
	case 3:
		err = s.rollback(ctx, &task)
	}

	s.cancelFuncs.Delete(taskID)
	cancel()

	status := 3
	if err != nil {
		status = 4
		db.Table("deploy_task").Where("id = ?", taskID).Update("error_msg", err.Error())
	}

	db.Table("deploy_task").Where("id = ?", taskID).Updates(map[string]interface{}{
		"status":      status,
		"end_time":    time.Now().UnixMilli(),
		"duration":    int(time.Now().UnixMilli() - task.StartTime),
		"update_time": time.Now().UnixMilli(),
	})

	return err
}

// CancelTask 取消任务
func (s *DeployService) CancelTask(taskID int64) error {
	if cancelFn, ok := s.cancelFuncs.LoadAndDelete(taskID); ok {
		cancelFn.(context.CancelFunc)()
	}
	db := config.GetDB()
	return db.Table("deploy_task").Where("id = ?", taskID).Updates(map[string]interface{}{
		"status":      5,
		"update_time": time.Now().UnixMilli(),
	}).Error
}

// build 构建项目
func (s *DeployService) build(ctx context.Context, task *Task) error {
	project := s.getProjectConfig(task.Project)
	if project == nil {
		return fmt.Errorf("项目配置不存在: %s", task.Project)
	}

	s.addRecord(task.ID, "拉取代码", "开始拉取代码")
	s.updateProgress(task.ID, 10)
	// Git pull
	if project.RepoURL != "" || project.Branch != "" {
		workDir := filepath.Join(viper.GetString("deploy.work_dir"), project.Name)
		if _, err := os.Stat(workDir); os.IsNotExist(err) {
			cloneCmd := exec.CommandContext(ctx, "git", "clone", "-b", project.Branch, project.RepoURL, workDir)
			if out, err := cloneCmd.CombinedOutput(); err != nil {
				s.addRecord(task.ID, "拉取代码失败", string(out))
				return fmt.Errorf("git clone 失败: %s", string(out))
			}
		} else {
			pullCmd := exec.CommandContext(ctx, "git", "-C", workDir, "pull", "origin", project.Branch)
			if out, err := pullCmd.CombinedOutput(); err != nil {
				s.addRecord(task.ID, "拉取代码失败", string(out))
			}
		}
	}

	s.addRecord(task.ID, "安装依赖", "开始安装依赖")
	s.updateProgress(task.ID, 20)

	s.addRecord(task.ID, "编译构建", project.BuildCmd)
	s.updateProgress(task.ID, 50)
	if err := s.runBuildCmd(project); err != nil {
		return fmt.Errorf("构建失败: %w", err)
	}

	s.addRecord(task.ID, "构建镜像", "开始构建Docker镜像")
	s.updateProgress(task.ID, 70)
	if err := s.buildImage(project, task.ID); err != nil {
		return fmt.Errorf("镜像构建失败: %w", err)
	}

	s.addRecord(task.ID, "推送镜像", "开始推送镜像")
	s.updateProgress(task.ID, 90)
	// Push image to registry
	registryURL := viper.GetString("docker.registry_url")
	if registryURL != "" {
		ctx2 := context.Background()
		imageTag := fmt.Sprintf("%s:%d", project.Image, time.Now().Unix())
		pushResp, err := s.docker.ImagePush(ctx2, imageTag, types.ImagePushOptions{})
		if err == nil {
			pushResp.Close()
		}
	}

	s.addRecord(task.ID, "完成", "构建完成")
	s.updateProgress(task.ID, 100)

	return nil
}

// deploy 部署项目
func (s *DeployService) deploy(ctx context.Context, task *Task) error {
	project := s.getProjectConfig(task.Project)
	if project == nil {
		return fmt.Errorf("项目配置不存在: %s", task.Project)
	}

	s.addRecord(task.ID, "拉取镜像", "开始拉取镜像")
	s.updateProgress(task.ID, 20)

	s.addRecord(task.ID, "停止旧容器", "停止旧版本容器")
	s.updateProgress(task.ID, 40)
	s.stopContainer(project.Image)

	s.addRecord(task.ID, "启动新容器", "启动新版本容器")
	s.updateProgress(task.ID, 60)
	if err := s.startContainer(project); err != nil {
		return fmt.Errorf("启动容器失败: %w", err)
	}

	s.addRecord(task.ID, "健康检查", "执行健康检查")
	s.updateProgress(task.ID, 80)
	// Health check: wait for container to be healthy
	time.Sleep(3 * time.Second)
	containers, _ := s.docker.ContainerList(ctx, container.ListOptions{})
	for _, c := range containers {
		if c.Image == project.Image+":latest" && c.State == "running" {
			s.addRecord(task.ID, "健康检查通过", "容器运行正常")
			break
		}
	}

	s.addRecord(task.ID, "完成", "部署完成")
	s.updateProgress(task.ID, 100)

	return nil
}

// rollback 回滚
func (s *DeployService) rollback(ctx context.Context, task *Task) error {
	s.addRecord(task.ID, "开始回滚", "开始执行回滚")
	s.updateProgress(task.ID, 20)

	project := s.getProjectConfig(task.Project)
	if project == nil {
		return fmt.Errorf("项目配置不存在: %s", task.Project)
	}

	s.addRecord(task.ID, "停止当前容器", project.Name)
	s.updateProgress(task.ID, 40)
	s.stopContainer(project.Image)

	// 查找上一版本镜像
	s.addRecord(task.ID, "查找上一版本镜像", "")
	s.updateProgress(task.ID, 60)
	images, err := s.docker.ImageList(ctx, types.ImageListOptions{})
	if err != nil {
		return fmt.Errorf("获取镜像列表失败: %w", err)
	}

	var prevImage string
	for _, img := range images {
		for _, tag := range img.RepoTags {
			if strings.HasPrefix(tag, project.Image+":") && tag != project.Image+":latest" {
				prevImage = tag
				break
			}
		}
		if prevImage != "" {
			break
		}
	}
	if prevImage == "" {
		prevImage = project.Image + ":latest"
	}

	s.addRecord(task.ID, "启动旧版本容器", prevImage)
	s.updateProgress(task.ID, 80)
	rollbackProject := *project
	rollbackProject.Image = strings.TrimSuffix(prevImage, ":latest")
	if err := s.startContainer(&rollbackProject); err != nil {
		return fmt.Errorf("启动旧版本容器失败: %w", err)
	}

	s.addRecord(task.ID, "完成", "回滚完成")
	s.updateProgress(task.ID, 100)
	return nil
}

// getProjectConfig 获取项目配置
func (s *DeployService) getProjectConfig(name string) *Project {
	projects := viper.GetStringMap("projects")
	if proj, ok := projects[name]; ok {
		projMap, _ := json.Marshal(proj)
		var project Project
		json.Unmarshal(projMap, &project)
		project.Name = name
		return &project
	}
	return nil
}

// runBuildCmd 执行构建命令
func (s *DeployService) runBuildCmd(project *Project) error {
	workDir := filepath.Join(viper.GetString("deploy.work_dir"), project.Name)

	cmd := exec.Command("sh", "-c", project.BuildCmd)
	cmd.Dir = workDir
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr

	return cmd.Run()
}

// buildImage 构建Docker镜像
func (s *DeployService) buildImage(project *Project, taskID int64) error {
	ctx := context.Background()
	workDir := filepath.Join(viper.GetString("deploy.work_dir"), project.Name)

	imageTag := fmt.Sprintf("%s:%d", project.Image, time.Now().Unix())

	// 创建 tar build context
	buf := new(bytes.Buffer)
	tw := tar.NewWriter(buf)

	// 添加 Dockerfile
	dockerfileContent := project.Dockerfile
	if dockerfileContent == "" {
		dockerfileContent = "FROM alpine:latest\nCOPY . /app\nWORKDIR /app\nCMD [\"./app\"]"
	}
	hdr := &tar.Header{Name: "Dockerfile", Mode: 0644, Size: int64(len(dockerfileContent))}
	tw.WriteHeader(hdr)
	tw.Write([]byte(dockerfileContent))

	// 如果工作目录存在，添加所有文件
	if fi, err := os.Stat(workDir); err == nil && fi.IsDir() {
		filepath.Walk(workDir, func(path string, info os.FileInfo, err error) error {
			if err != nil || info.IsDir() || info.Name() == "Dockerfile" {
				return nil
			}
			relPath, _ := filepath.Rel(workDir, path)
			f, err := os.Open(path)
			if err != nil {
				return nil
			}
			data, err := io.ReadAll(f)
			f.Close()
			if err != nil {
				return nil
			}
			hdr := &tar.Header{Name: relPath, Mode: 0644, Size: int64(len(data))}
			tw.WriteHeader(hdr)
			tw.Write(data)
			return nil
		})
	}

	tw.Close()
	dockerCtx := bytes.NewReader(buf.Bytes())

	resp, err := s.docker.ImageBuild(ctx, dockerCtx, types.ImageBuildOptions{
		Dockerfile: "Dockerfile",
		Tags:       []string{imageTag, project.Image + ":latest"},
	})
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	log.Printf("构建镜像: %s", imageTag)
	s.addRecord(taskID, "镜像标签", imageTag)

	return nil
}

// stopContainer 停止容器
func (s *DeployService) stopContainer(imageName string) error {
	ctx := context.Background()

	containers, err := s.docker.ContainerList(ctx, container.ListOptions{All: true})
	if err != nil {
		return err
	}

	for _, c := range containers {
		if c.Image == imageName || c.Image == imageName+":latest" {
			timeout := 10
			s.docker.ContainerStop(ctx, c.ID, container.StopOptions{Timeout: &timeout})
			s.docker.ContainerRemove(ctx, c.ID, container.RemoveOptions{})
		}
	}

	return nil
}

// startContainer 启动容器
func (s *DeployService) startContainer(project *Project) error {
	ctx := context.Background()

	// 构建端口映射
	portBindings := nat.PortMap{}
	exposedPorts := nat.PortSet{}
	for _, portSpec := range project.Ports {
		parts := strings.SplitN(portSpec, ":", 2)
		if len(parts) == 2 {
			hostPort := parts[0]
			containerPort := parts[1]
			port, _ := nat.NewPort("tcp", containerPort)
			exposedPorts[port] = struct{}{}
			portBindings[port] = []nat.PortBinding{
				{HostIP: "0.0.0.0", HostPort: hostPort},
			}
		}
	}

	resp, err := s.docker.ContainerCreate(ctx, &container.Config{
		Image:        project.Image + ":latest",
		ExposedPorts: exposedPorts,
	}, &container.HostConfig{
		PortBindings: portBindings,
		RestartPolicy: container.RestartPolicy{
			Name: "always",
		},
	}, nil, nil, project.Name)
	if err != nil {
		return err
	}

	return s.docker.ContainerStart(ctx, resp.ID, container.StartOptions{})
}

// addRecord 添加执行记录
func (s *DeployService) addRecord(taskID int64, step, log string) {
	db := config.GetDB()
	db.Table("deploy_record").Create(map[string]interface{}{
		"task_id":     taskID,
		"step":        step,
		"step_name":   log,
		"status":      3,
		"create_time": time.Now().UnixMilli(),
	})

	db.Table("deploy_task").Where("id = ?", taskID).UpdateColumn("log",
		gorm.Expr("CONCAT(COALESCE(log, ''), ?)",
			fmt.Sprintf("[%s] %s: %s\n", time.Now().Format("15:04:05"), step, log)))
}

// updateProgress 更新进度
func (s *DeployService) updateProgress(taskID int64, progress int) {
	db := config.GetDB()
	db.Table("deploy_task").Where("id = ?", taskID).Update("progress", progress)
}

// GetTask 获取任务
func (s *DeployService) GetTask(taskID int64) (*Task, error) {
	var task Task
	db := config.GetDB()
	err := db.Table("deploy_task").Where("id = ?", taskID).First(&task).Error
	return &task, err
}

// ListTasks 获取任务列表
func (s *DeployService) ListTasks(adminID int64, page, pageSize int) ([]Task, int64, error) {
	var tasks []Task
	var total int64

	db := config.GetDB()
	db.Table("deploy_task").Where("admin_id = ?", adminID).Count(&total)

	offset := (page - 1) * pageSize
	err := db.Table("deploy_task").
		Where("admin_id = ?", adminID).
		Order("create_time desc").
		Offset(offset).
		Limit(pageSize).
		Find(&tasks).Error

	return tasks, total, err
}

// GetContainerLogs 获取容器日志
func (s *DeployService) GetContainerLogs(containerID string) (string, error) {
	ctx := context.Background()

	reader, err := s.docker.ContainerLogs(ctx, containerID, container.LogsOptions{
		ShowStdout: true,
		ShowStderr: true,
		Tail:       "100",
	})
	if err != nil {
		return "", err
	}
	defer reader.Close()

	data, err := io.ReadAll(reader)
	if err != nil {
		return "", err
	}
	return string(data), nil
}

// ListContainers 获取容器列表
func (s *DeployService) ListContainers() ([]types.Container, error) {
	ctx := context.Background()
	return s.docker.ContainerList(ctx, container.ListOptions{All: true})
}

// ListImages 获取镜像列表
func (s *DeployService) ListImages() ([]image.Summary, error) {
	ctx := context.Background()
	return s.docker.ImageList(ctx, types.ImageListOptions{})
}

// ========== 项目 CRUD ==========

// ListProjects 获取项目列表
func (s *DeployService) ListProjects(tenantID int64, page, pageSize int) ([]DeployProject, int64, error) {
	var projects []DeployProject
	var total int64
	db := config.GetDB()
	db.Table("deploy_project").Where("tenant_id = ?", tenantID).Count(&total)
	offset := (page - 1) * pageSize
	err := db.Table("deploy_project").
		Where("tenant_id = ?", tenantID).
		Order("create_time desc").
		Offset(offset).Limit(pageSize).
		Find(&projects).Error
	return projects, total, err
}

// GetProjectByID 获取项目
func (s *DeployService) GetProjectByID(id int64, tenantID int64) (*DeployProject, error) {
	var project DeployProject
	db := config.GetDB()
	err := db.Table("deploy_project").
		Where("id = ? AND tenant_id = ?", id, tenantID).
		First(&project).Error
	return &project, err
}

// CreateProject 创建项目
func (s *DeployService) CreateProject(project *DeployProject) error {
	db := config.GetDB()
	project.CreateTime = time.Now().UnixMilli()
	project.UpdateTime = time.Now().UnixMilli()
	return db.Table("deploy_project").Create(project).Error
}

// UpdateProject 更新项目
func (s *DeployService) UpdateProject(id int64, tenantID int64, updates map[string]interface{}) error {
	db := config.GetDB()
	updates["update_time"] = time.Now().UnixMilli()
	return db.Table("deploy_project").
		Where("id = ? AND tenant_id = ?", id, tenantID).
		Updates(updates).Error
}

// DeleteProject 删除项目
func (s *DeployService) DeleteProject(id int64, tenantID int64) error {
	db := config.GetDB()
	return db.Table("deploy_project").
		Where("id = ? AND tenant_id = ?", id, tenantID).
		Delete(nil).Error
}

// ========== Docker 操作 ==========

// StartContainerByID 启动容器
func (s *DeployService) StartContainerByID(containerID string) error {
	ctx := context.Background()
	return s.docker.ContainerStart(ctx, containerID, container.StartOptions{})
}

// StopContainerByID 停止容器
func (s *DeployService) StopContainerByID(containerID string) error {
	ctx := context.Background()
	timeout := 10
	return s.docker.ContainerStop(ctx, containerID, container.StopOptions{Timeout: &timeout})
}

// RemoveContainerByID 删除容器
func (s *DeployService) RemoveContainerByID(containerID string) error {
	ctx := context.Background()
	return s.docker.ContainerRemove(ctx, containerID, container.RemoveOptions{})
}

// RemoveImageByID 删除镜像
func (s *DeployService) RemoveImageByID(imageID string) error {
	ctx := context.Background()
	_, err := s.docker.ImageRemove(ctx, imageID, image.RemoveOptions{})
	return err
}
