package service

import (
	"sync"

	"admin-agent/internal/model"
	"admin-agent/pkg/protocol"
)

// WorkflowStage 工作流阶段
type WorkflowStage string

const (
	StageRequirement WorkflowStage = "requirement" // 需求阶段
	StagePlanning    WorkflowStage = "planning"    // 规划阶段
	StageDevelopment WorkflowStage = "development" // 开发阶段
	StageTesting     WorkflowStage = "testing"     // 测试阶段
	StageReport      WorkflowStage = "report"      // 汇报阶段
)

// WorkflowService 工作流服务
type WorkflowService struct {
	stages map[string]WorkflowStage
	mu     sync.RWMutex
}

// NewWorkflowService 创建工作流服务
func NewWorkflowService(orchestrator *Orchestrator) *WorkflowService {
	return &WorkflowService{
		stages: make(map[string]WorkflowStage),
	}
}

// 工作流转换规则
var workflowTransitions = map[model.AgentType]model.AgentType{
	model.AgentPM:  model.AgentPJM, // PM -> PJM
	model.AgentPJM: model.AgentBE,  // PJM -> BE (或FE)
	model.AgentBE:  model.AgentFE,  // BE -> FE
	model.AgentFE:  model.AgentQA,  // FE -> QA
	model.AgentQA:  model.AgentRPT, // QA -> RPT
	model.AgentRPT: model.AgentPM,  // RPT -> PM (新一轮)
}

// 阶段映射
var agentToStage = map[model.AgentType]WorkflowStage{
	model.AgentPM:  StageRequirement,
	model.AgentPJM: StagePlanning,
	model.AgentBE:  StageDevelopment,
	model.AgentFE:  StageDevelopment,
	model.AgentQA:  StageTesting,
	model.AgentRPT: StageReport,
}

// GetNextAgent 获取下一个要处理的分身
func (w *WorkflowService) GetNextAgent(input *protocol.Message, output *protocol.Message) model.AgentType {
	// 检查消息类型决定流转
	switch output.Type {
	case model.MsgTypeRequirementDoc:
		// PRD文档完成，流转到PJM
		return model.AgentPJM

	case model.MsgTypeTaskList:
		// 任务列表完成，流转到BE/FE
		return model.AgentBE

	case model.MsgTypeAPIContract:
		// API契约完成，流转到对应开发
		return model.AgentBE

	case model.MsgTypeBugReport:
		// BUG报告，流转给对应开发者
		// 这里需要从payload解析assignee
		return model.AgentBE

	case model.MsgTypeTestReport:
		// 测试报告完成，流转到RPT
		return model.AgentRPT

	case model.MsgTypeDailyReport:
		// 日报完成，不需要流转
		return ""
	}

	// 默认不流转
	return ""
}

// GetMessageType 获取分身对应的消息类型
func (w *WorkflowService) GetMessageType(agent model.AgentType) model.MsgType {
	switch agent {
	case model.AgentPM:
		return model.MsgTypeRequirementDoc
	case model.AgentPJM:
		return model.MsgTypeTaskList
	case model.AgentBE, model.AgentFE:
		return model.MsgTypeAPIContract
	case model.AgentQA:
		return model.MsgTypeBugReport
	case model.AgentRPT:
		return model.MsgTypeDailyReport
	default:
		return model.MsgTypeChat
	}
}

// UpdateStage 更新项目工作流阶段
func (w *WorkflowService) UpdateStage(projectID string, agent model.AgentType) {
	w.mu.Lock()
	defer w.mu.Unlock()

	if stage, ok := agentToStage[agent]; ok {
		w.stages[projectID] = stage
	}
}

// GetStage 获取项目当前阶段
func (w *WorkflowService) GetStage(projectID string) WorkflowStage {
	w.mu.RLock()
	defer w.mu.RUnlock()

	if stage, ok := w.stages[projectID]; ok {
		return stage
	}
	return StageRequirement
}

// GetStageInfo 获取阶段信息
func (w *WorkflowService) GetStageInfo(stage WorkflowStage) map[string]interface{} {
	info := map[string]interface{}{
		"stage": stage,
	}

	switch stage {
	case StageRequirement:
		info["description"] = "需求阶段"
		info["active_agent"] = "PM"
		info["next_stage"] = StagePlanning
	case StagePlanning:
		info["description"] = "规划阶段"
		info["active_agent"] = "PJM"
		info["next_stage"] = StageDevelopment
	case StageDevelopment:
		info["description"] = "开发阶段"
		info["active_agent"] = "BE/FE"
		info["next_stage"] = StageTesting
	case StageTesting:
		info["description"] = "测试阶段"
		info["active_agent"] = "QA"
		info["next_stage"] = StageReport
	case StageReport:
		info["description"] = "汇报阶段"
		info["active_agent"] = "RPT"
		info["next_stage"] = StageRequirement
	}

	return info
}

// CanTransition 检查是否可以转换到目标阶段
func (w *WorkflowService) CanTransition(projectID string, targetStage WorkflowStage) bool {
	currentStage := w.GetStage(projectID)

	// 定义允许的转换
	allowedTransitions := map[WorkflowStage][]WorkflowStage{
		StageRequirement: {StagePlanning},
		StagePlanning:    {StageDevelopment},
		StageDevelopment: {StageTesting},
		StageTesting:     {StageReport},
		StageReport:      {StageRequirement},
	}

	if allowed, ok := allowedTransitions[currentStage]; ok {
		for _, s := range allowed {
			if s == targetStage {
				return true
			}
		}
	}

	return false
}

// ForceTransition 强制转换阶段
func (w *WorkflowService) ForceTransition(projectID string, targetStage WorkflowStage) {
	w.mu.Lock()
	defer w.mu.Unlock()
	w.stages[projectID] = targetStage
}

// GetAllStages 获取所有阶段定义
func (w *WorkflowService) GetAllStages() []map[string]interface{} {
	stages := []WorkflowStage{
		StageRequirement,
		StagePlanning,
		StageDevelopment,
		StageTesting,
		StageReport,
	}

	var result []map[string]interface{}
	for _, s := range stages {
		result = append(result, w.GetStageInfo(s))
	}

	return result
}
