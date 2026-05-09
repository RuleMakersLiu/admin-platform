package service

import (
	"bytes"
	"context"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"io"
	"strings"
	"time"

	"github.com/docker/docker/api/types"
	"github.com/docker/docker/api/types/container"
	"github.com/docker/docker/api/types/mount"
	"github.com/docker/docker/client"
	"github.com/docker/docker/pkg/stdcopy"
)

// SandboxService 代码执行沙箱服务
// 使用Docker容器隔离执行代码，确保安全性
type SandboxService struct {
	dockerClient *client.Client
	config       *SandboxConfig
}

// SandboxConfig 沙箱配置
type SandboxConfig struct {
	MemoryLimit    int64  // 内存限制(MB)
	CPUQuota       int64  // CPU配额(微秒, 100000=1核)
	Timeout        int    // 超时时间(秒)
	NetworkDisabled bool  // 是否禁用网络
	TempDir        string // 临时目录挂载路径
}

// ExecuteRequest 代码执行请求
type ExecuteRequest struct {
	Language string `json:"language" binding:"required"` // python/javascript/go
	Code     string `json:"code" binding:"required"`     // 要执行的代码
	Input    string `json:"input"`                       // 可选的标准输入
}

// ExecuteResult 执行结果
type ExecuteResult struct {
	Stdout   string `json:"stdout"`    // 标准输出
	Stderr   string `json:"stderr"`    // 标准错误
	ExitCode int    `json:"exit_code"` // 退出码
	Time     int64  `json:"time_ms"`   // 执行时间(毫秒)
	Memory   int64  `json:"memory_kb"` // 内存使用(KB)
}

// DefaultSandboxConfig 默认沙箱配置
func DefaultSandboxConfig() *SandboxConfig {
	return &SandboxConfig{
		MemoryLimit:     128,  // 128MB
		CPUQuota:       50000, // 0.5核
		Timeout:        10,    // 10秒
		NetworkDisabled: true,
		TempDir:        "/tmp/sandbox",
	}
}

// NewSandboxService 创建沙箱服务
func NewSandboxService(cfg *SandboxConfig) (*SandboxService, error) {
	if cfg == nil {
		cfg = DefaultSandboxConfig()
	}

	// 创建Docker客户端
	cli, err := client.NewClientWithOpts(client.FromEnv, client.WithAPIVersionNegotiation())
	if err != nil {
		return nil, fmt.Errorf("创建Docker客户端失败: %w", err)
	}

	// 验证Docker连接
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	_, err = cli.Ping(ctx)
	if err != nil {
		return nil, fmt.Errorf("Docker连接失败: %w", err)
	}

	return &SandboxService{
		dockerClient: cli,
		config:       cfg,
	}, nil
}

// Execute 执行代码
func (s *SandboxService) Execute(ctx context.Context, req *ExecuteRequest) (*ExecuteResult, error) {
	// 验证语言支持
	image, cmd, err := s.getExecutionConfig(req.Language, req.Code)
	if err != nil {
		return nil, err
	}

	// 拉取镜像(如果不存在)
	if err := s.ensureImage(ctx, image); err != nil {
		return nil, fmt.Errorf("准备镜像失败: %w", err)
	}

	// 创建容器
	containerID, err := s.createContainer(ctx, image, cmd, req.Input)
	if err != nil {
		return nil, fmt.Errorf("创建容器失败: %w", err)
	}
	defer s.cleanupContainer(ctx, containerID)

	// 启动容器并等待执行
	startTime := time.Now()
	result, err := s.runContainer(ctx, containerID, req.Input)
	if err != nil {
		return nil, fmt.Errorf("执行容器失败: %w", err)
	}
	result.Time = time.Since(startTime).Milliseconds()

	// 获取内存使用统计
	stats, _ := s.getContainerStats(ctx, containerID)
	if stats != nil {
		result.Memory = stats.MemoryKB
	}

	return result, nil
}

// getExecutionConfig 根据语言获取执行配置
func (s *SandboxService) getExecutionConfig(language, code string) (image string, cmd []string, err error) {
	language = strings.ToLower(language)

	switch language {
	case "python", "py":
		return "python:3.11-slim", []string{"python", "-c", code}, nil
	case "javascript", "js", "node":
		return "node:20-slim", []string{"node", "-e", code}, nil
	case "go", "golang":
		// Go: 使用base64编码传递代码，防止shell注入
		encoded := base64.StdEncoding.EncodeToString([]byte(code))
		return "golang:1.21-alpine", []string{"sh", "-c",
			fmt.Sprintf("echo %s | base64 -d > /tmp/main.go && go run /tmp/main.go", encoded)}, nil
	default:
		return "", nil, fmt.Errorf("不支持的语言: %s (支持: python, javascript, go)", language)
	}
}

// ensureImage 确保镜像存在
func (s *SandboxService) ensureImage(ctx context.Context, image string) error {
	// 检查镜像是否存在
	_, _, err := s.dockerClient.ImageInspectWithRaw(ctx, image)
	if err == nil {
		return nil // 镜像已存在
	}

	// 拉取镜像
	reader, err := s.dockerClient.ImagePull(ctx, image, types.ImagePullOptions{})
	if err != nil {
		return fmt.Errorf("拉取镜像失败: %w", err)
	}
	defer reader.Close()

	// 等待拉取完成
	_, err = io.Copy(io.Discard, reader)
	return err
}

// createContainer 创建容器
func (s *SandboxService) createContainer(ctx context.Context, image string, cmd []string, input string) (string, error) {
	// 安全配置
	securityOpt := []string{
		"no-new-privileges", // 禁止提权
	}

	// 容器配置
	config := &container.Config{
		Image:      image,
		Cmd:        cmd,
		StdinOnce:  true,
		OpenStdin:  input != "",
		Tty:        false,
		User:       "nobody", // 非root用户运行
		WorkingDir: "/tmp",
		Env: []string{
			"HOME=/tmp",
			"TMPDIR=/tmp",
		},
	}

	// 主机配置
	hostConfig := &container.HostConfig{
		Resources: container.Resources{
			Memory:     s.config.MemoryLimit * 1024 * 1024, // MB转字节
			MemorySwap: s.config.MemoryLimit * 1024 * 1024, // 禁止swap
			CPUQuota:   s.config.CPUQuota,                  // CPU配额
			CPUPeriod:  100000,                             // CPU周期(100ms)
		},
		NetworkMode:   "none", // 禁用网络
		SecurityOpt:   securityOpt,
		ReadonlyRootfs: true, // 只读文件系统
		Mounts: []mount.Mount{
			{
				Type:     mount.TypeTmpfs,
				Target:   "/tmp",
				TmpfsOptions: &mount.TmpfsOptions{
					SizeBytes: s.config.MemoryLimit * 1024 * 1024, // /tmp目录大小限制
				},
			},
		},
		AutoRemove: false, // 手动清理以便获取日志
	}

	// 创建容器
	resp, err := s.dockerClient.ContainerCreate(ctx, config, hostConfig, nil, nil, "")
	if err != nil {
		return "", err
	}

	return resp.ID, nil
}

// runContainer 运行容器并获取结果
func (s *SandboxService) runContainer(ctx context.Context, containerID, input string) (*ExecuteResult, error) {
	// 设置超时上下文
	execCtx, cancel := context.WithTimeout(ctx, time.Duration(s.config.Timeout)*time.Second)
	defer cancel()

	// 启动容器
	err := s.dockerClient.ContainerStart(execCtx, containerID, types.ContainerStartOptions{})
	if err != nil {
		return nil, err
	}

	// 如果有输入，写入stdin
	if input != "" {
		hijacked, err := s.dockerClient.ContainerAttach(execCtx, containerID, types.ContainerAttachOptions{
			Stream: true,
			Stdin:  true,
		})
		if err == nil {
			go func() {
				defer hijacked.Close()
				hijacked.Conn.Write([]byte(input))
				hijacked.CloseWrite()
			}()
		}
	}

	// 等待容器执行完成
	statusCh, errCh := s.dockerClient.ContainerWait(execCtx, containerID, container.WaitConditionNotRunning)
	var exitCode int64
	select {
	case err := <-errCh:
		if err != nil {
			return nil, err
		}
	case status := <-statusCh:
		exitCode = status.StatusCode
	case <-execCtx.Done():
		// 超时，强制停止容器
		timeout := 2
		s.dockerClient.ContainerStop(context.Background(), containerID, container.StopOptions{Timeout: &timeout})
		return &ExecuteResult{
			Stderr:   fmt.Sprintf("执行超时 (超过%d秒)", s.config.Timeout),
			ExitCode: 137, // SIGKILL
		}, nil
	}

	// 获取容器日志
	stdout, stderr, err := s.getContainerLogs(execCtx, containerID)
	if err != nil {
		return nil, err
	}

	return &ExecuteResult{
		Stdout:   stdout,
		Stderr:   stderr,
		ExitCode: int(exitCode),
	}, nil
}

// getContainerLogs 获取容器日志
func (s *SandboxService) getContainerLogs(ctx context.Context, containerID string) (stdout, stderr string, err error) {
	options := types.ContainerLogsOptions{
		ShowStdout: true,
		ShowStderr: true,
	}

	reader, err := s.dockerClient.ContainerLogs(ctx, containerID, options)
	if err != nil {
		return "", "", err
	}
	defer reader.Close()

	// Docker日志使用特殊格式，需要用stdcopy分离stdout和stderr
	var outBuf, errBuf bytes.Buffer
	_, err = stdcopy.StdCopy(&outBuf, &errBuf, reader)
	if err != nil {
		return "", "", err
	}

	return outBuf.String(), errBuf.String(), nil
}

// ContainerStats 容器统计信息
type ContainerStats struct {
	MemoryKB int64
	CPUNano  int64
}

// getContainerStats 获取容器资源使用统计
func (s *SandboxService) getContainerStats(ctx context.Context, containerID string) (*ContainerStats, error) {
	stats, err := s.dockerClient.ContainerStats(ctx, containerID, false)
	if err != nil {
		return nil, err
	}
	defer stats.Body.Close()

	var stat types.StatsJSON
	if err := json.NewDecoder(stats.Body).Decode(&stat); err != nil {
		return nil, err
	}

	return &ContainerStats{
		MemoryKB: int64(stat.MemoryStats.Usage / 1024),
		CPUNano:  int64(stat.CPUStats.CPUUsage.TotalUsage),
	}, nil
}

// cleanupContainer 清理容器
func (s *SandboxService) cleanupContainer(ctx context.Context, containerID string) {
	// 设置清理超时
	cleanCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	// 移除容器
	_ = s.dockerClient.ContainerRemove(cleanCtx, containerID, types.ContainerRemoveOptions{
		Force:         true,
		RemoveVolumes: true,
	})
}

// Close 关闭沙箱服务
func (s *SandboxService) Close() error {
	if s.dockerClient != nil {
		return s.dockerClient.Close()
	}
	return nil
}

// HealthCheck 健康检查
func (s *SandboxService) HealthCheck(ctx context.Context) error {
	ctx, cancel := context.WithTimeout(ctx, 5*time.Second)
	defer cancel()

	_, err := s.dockerClient.Ping(ctx)
	if err != nil {
		return fmt.Errorf("Docker连接异常: %w", err)
	}
	return nil
}

// SupportedLanguages 返回支持的语言列表
func (s *SandboxService) SupportedLanguages() []string {
	return []string{
		"python (py)",
		"javascript (js/node)",
		"go (golang)",
	}
}

// GetConfig 获取当前沙箱配置
func (s *SandboxService) GetConfig() *SandboxConfig {
	return s.config
}
