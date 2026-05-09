package service

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os/exec"
	"sync"
	"time"

	"github.com/google/uuid"
	"gorm.io/gorm"

	"admin-agent/internal/model"
)

// SkillService 技能服务
type SkillService struct {
    db          *gorm.DB
    registry    map[uuid.UUID]*model.Skill
    executors   map[string]SkillExecutor
    mu          sync.RWMutex
}

// SkillExecutor 技能执行器接口
type SkillExecutor interface {
    Name() string
    Description() string
    Execute(ctx context.Context, input json.RawMessage) (json.RawMessage, error)
    ValidateInput(input json.RawMessage) error
}

// NewSkillService 创建技能服务
func NewSkillService(db *gorm.DB) *SkillService {
    return &SkillService{
        db:        db,
        registry:  make(map[uuid.UUID]*model.Skill),
        executors: make(map[string]SkillExecutor),
    }
}

// Register 注册技能
func (s *SkillService) Register(skill *model.Skill) error {
    s.mu.Lock()
    defer s.mu.Unlock()

    if _, exists := s.registry[skill.ID]; exists {
        return fmt.Errorf("skill already registered: %s", skill.ID)
    }

    // 保存到数据库
    if err := s.db.Create(skill).Error; err != nil {
        return fmt.Errorf("failed to save skill: %w", err)
    }

    s.registry[skill.ID] = skill
    return nil
}

// RegisterExecutor 注册执行器
func (s *SkillService) RegisterExecutor(executor SkillExecutor) error {
    s.mu.Lock()
    defer s.mu.Unlock()

    name := executor.Name()
    if _, exists := s.executors[name]; exists {
        return fmt.Errorf("executor already registered: %s", name)
    }
    s.executors[name] = executor
    return nil
}

// Get 获取技能
func (s *SkillService) Get(id uuid.UUID) (*model.Skill, error) {
    s.mu.RLock()
    defer s.mu.RUnlock()

    if skill, exists := s.registry[id]; exists {
        return skill, nil
    }

    var skill model.Skill
    if err := s.db.First(&skill, "id = ?", id).Error; err != nil {
        return nil, fmt.Errorf("skill not found: %s", id)
    }
    return &skill, nil
}

// List 列出技能
func (s *SkillService) List(category string, enabled *bool) ([]model.Skill, error) {
    var skills []model.Skill
    query := s.db.Model(&model.Skill{})

    if category != "" {
        query = query.Where("category = ?", category)
    }
    if enabled != nil {
        query = query.Where("enabled = ?", *enabled)
    }

    if err := query.Find(&skills).Error; err != nil {
        return nil, fmt.Errorf("failed to list skills: %w", err)
    }
    return skills, nil
}

// Execute 执行技能
func (s *SkillService) Execute(ctx context.Context, skillID uuid.UUID, input json.RawMessage) (json.RawMessage, error) {
    skill, err := s.Get(skillID)
    if err != nil {
        return nil, fmt.Errorf("skill not found: %s", skillID)
    }

    if !skill.Enabled {
        return nil, fmt.Errorf("skill is disabled: %s", skill.Name)
    }

    start := time.Now()

    // 创建执行记录
    execution := &model.SkillExecution{
        SkillID:    skillID,
        Input:       func() model.JSON { var m model.JSON; json.Unmarshal(input, &m); return m }(),
        Status:      "running",
    }
    if err := s.db.Create(execution).Error; err != nil {
        return nil, fmt.Errorf("failed to create execution record: %w", err)
    }

    // 执行技能
    var result json.RawMessage
    var execErr error

    if skill.HandlerType == "builtin" && skill.BuiltinFunc != "" {
        // 内置执行器
        if executor, exists := s.executors[skill.BuiltinFunc]; exists {
            if err := executor.ValidateInput(input); err != nil {
                execErr = err
            } else {
                result, execErr = executor.Execute(ctx, input)
            }
        } else {
            execErr = fmt.Errorf("builtin executor not found: %s", skill.BuiltinFunc)
        }
    } else if skill.HandlerType == "http" && skill.HandlerURL != "" {
        // HTTP 调用
        result, execErr = s.executeHTTP(ctx, skill, input)
    } else if skill.HandlerType == "script" && skill.ScriptPath != "" {
        // 脚本执行
        result, execErr = s.executeScript(ctx, skill, input)
    } else {
        execErr = fmt.Errorf("invalid skill handler configuration")
    }

    // 更新执行记录
    duration := int(time.Since(start).Milliseconds())
    status := "success"
    if execErr != nil {
        status = "failed"
    }

    s.db.Model(execution).Updates(map[string]interface{}{
        "output":  result,
        "status":  status,
        "error":   execErr,
        "duration": duration,
    })

    return result, execErr
}

// executeHTTP HTTP 执行
func (s *SkillService) executeHTTP(ctx context.Context, skill *model.Skill, input json.RawMessage) (json.RawMessage, error) {
	timeout := 30 * time.Second
	ctx, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()

	req, err := http.NewRequestWithContext(ctx, "POST", skill.HandlerURL, bytes.NewReader(input))
	if err != nil {
		return nil, fmt.Errorf("创建请求失败: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("HTTP 调用失败: %w", err)
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("读取响应失败: %w", err)
	}

	if resp.StatusCode >= 400 {
		return nil, fmt.Errorf("HTTP 错误 %d: %s", resp.StatusCode, string(body))
	}

	return json.RawMessage(body), nil
}

// executeScript 脚本执行
func (s *SkillService) executeScript(ctx context.Context, skill *model.Skill, input json.RawMessage) (json.RawMessage, error) {
	timeout := 60 * time.Second
	ctx, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()

	cmd := exec.CommandContext(ctx, "sh", "-c", skill.ScriptPath)
	stdin, err := cmd.StdinPipe()
	if err != nil {
		return nil, fmt.Errorf("创建管道失败: %w", err)
	}

	go func() {
		defer stdin.Close()
		stdin.Write(input)
	}()

	output, err := cmd.Output()
	if err != nil {
		return nil, fmt.Errorf("脚本执行失败: %w", err)
	}

	return json.RawMessage(output), nil
}

// Update 更新技能
func (s *SkillService) Update(skill *model.Skill) error {
    s.mu.Lock()
    defer s.mu.Unlock()

    if err := s.db.Save(skill).Error; err != nil {
        return fmt.Errorf("failed to update skill: %w", err)
    }
    s.registry[skill.ID] = skill
    return nil
}

// Delete 删除技能
func (s *SkillService) Delete(id uuid.UUID) error {
    s.mu.Lock()
    defer s.mu.Unlock()

    if err := s.db.Delete(&model.Skill{}, "id = ?", id).Error; err != nil {
        return fmt.Errorf("failed to delete skill: %w", err)
    }
    delete(s.registry, id)
    return nil
}
