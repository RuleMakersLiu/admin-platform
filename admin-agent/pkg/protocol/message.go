package protocol

import (
	"encoding/json"
	"fmt"
	"time"

	"github.com/google/uuid"

	"admin-agent/internal/model"
)

// Message 标准消息协议
type Message struct {
	MsgID     string          `json:"msg_id"`           // 消息ID
	From      model.AgentType `json:"from"`             // 发送方
	To        model.AgentType `json:"to"`               // 接收方
	Type      model.MsgType   `json:"type"`             // 消息类型
	ProjectID string          `json:"project_id"`       // 项目ID
	SessionID string          `json:"session_id"`       // 会话ID
	Timestamp string          `json:"timestamp"`        // 时间戳 ISO8601
	Payload   json.RawMessage `json:"payload"`          // 消息载荷
}

// NewMessage 创建新消息
func NewMessage(from, to model.AgentType, msgType model.MsgType, payload interface{}) (*Message, error) {
	payloadBytes, err := json.Marshal(payload)
	if err != nil {
		return nil, fmt.Errorf("序列化payload失败: %w", err)
	}

	return &Message{
		MsgID:     generateMsgID(),
		From:      from,
		To:        to,
		Type:      msgType,
		Timestamp: time.Now().Format(time.RFC3339),
		Payload:   payloadBytes,
	}, nil
}

// generateMsgID 生成消息ID
func generateMsgID() string {
	return fmt.Sprintf("msg_%d_%s", time.Now().UnixMilli(), uuid.New().String()[:8])
}

// ========== 消息载荷定义 ==========

// ChatPayload 对话消息载荷
type ChatPayload struct {
	Content   string `json:"content"`    // 消息内容
	UserInput string `json:"user_input"` // 用户输入
	Intent    string `json:"intent"`     // 意图识别
}

// RequirementDocPayload 需求文档载荷
type RequirementDocPayload struct {
	DocTitle   string `json:"doc_title"`   // 文档标题
	DocContent string `json:"doc_content"` // 文档内容
	Priority   string `json:"priority"`    // 优先级
	Version    string `json:"version"`     // 版本号
}

// TaskListPayload 任务列表载荷
type TaskListPayload struct {
	Tasks []TaskItem `json:"tasks"` // 任务列表
	Total int        `json:"total"` // 总数
}

// TaskItem 任务项
type TaskItem struct {
	TaskID       string `json:"task_id"`       // 任务ID
	TaskName     string `json:"task_name"`     // 任务名称
	TaskType     string `json:"task_type"`     // 任务类型
	Assignee     string `json:"assignee"`      // 指派人
	Priority     string `json:"priority"`      // 优先级
	Dependencies string `json:"dependencies"`  // 依赖
	Description  string `json:"description"`   // 描述
}

// APIContractPayload API契约载荷
type APIContractPayload struct {
	ContractName string      `json:"contract_name"` // 契约名称
	Version      string      `json:"version"`       // 版本
	Endpoints    []APIEndpoint `json:"endpoints"`   // 接口列表
}

// APIEndpoint API端点
type APIEndpoint struct {
	Method      string            `json:"method"`       // HTTP方法
	Path        string            `json:"path"`         // 路径
	Description string            `json:"description"`  // 描述
	Request     interface{}       `json:"request"`      // 请求体
	Response    interface{}       `json:"response"`     // 响应体
	Headers     map[string]string `json:"headers"`      // 请求头
}

// BugReportPayload BUG报告载荷
type BugReportPayload struct {
	BugID         string `json:"bug_id"`          // BUG ID
	Title         string `json:"title"`           // 标题
	Severity      string `json:"severity"`        // 严重程度
	Description   string `json:"description"`     // 描述
	ReproduceSteps string `json:"reproduce_steps"` // 复现步骤
	ExpectedResult string `json:"expected_result"` // 期望结果
	ActualResult   string `json:"actual_result"`   // 实际结果
	Assignee       string `json:"assignee"`        // 指派人
}

// TestReportPayload 测试报告载荷
type TestReportPayload struct {
	ReportID    string       `json:"report_id"`    // 报告ID
	Summary     string       `json:"summary"`      // 摘要
	TotalCases  int          `json:"total_cases"`  // 总用例数
	Passed      int          `json:"passed"`       // 通过数
	Failed      int          `json:"failed"`       // 失败数
	Skipped     int          `json:"skipped"`      // 跳过数
	TestResults []TestResult `json:"test_results"` // 测试结果
}

// TestResult 测试结果
type TestResult struct {
	CaseName     string `json:"case_name"`     // 用例名称
	Status       string `json:"status"`        // 状态
	Duration     int64  `json:"duration"`      // 耗时(ms)
	ErrorMessage string `json:"error_message"` // 错误信息
}

// DailyReportPayload 日报载荷
type DailyReportPayload struct {
	ReportDate   string         `json:"report_date"`   // 报告日期
	Completed    []TaskSummary  `json:"completed"`     // 已完成
	InProgress   []TaskSummary  `json:"in_progress"`   // 进行中
	Blocked      []BlockerInfo  `json:"blocked"`       // 阻塞项
	NextDayPlan  []string       `json:"next_day_plan"` // 明日计划
	Metrics      ProjectMetrics `json:"metrics"`       // 项目指标
}

// TaskSummary 任务摘要
type TaskSummary struct {
	TaskID   string `json:"task_id"`   // 任务ID
	TaskName string `json:"task_name"` // 任务名称
	Progress int    `json:"progress"`  // 进度
}

// BlockerInfo 阻塞信息
type BlockerInfo struct {
	TaskID    string `json:"task_id"`    // 任务ID
	Reason    string `json:"reason"`     // 阻塞原因
	Impact    string `json:"impact"`     // 影响范围
	Suggestion string `json:"suggestion"` // 建议
}

// ProjectMetrics 项目指标
type ProjectMetrics struct {
	TotalTasks     int `json:"total_tasks"`     // 总任务数
	CompletedTasks int `json:"completed_tasks"` // 已完成数
	BugCount       int `json:"bug_count"`       // BUG数量
	FixedBugs      int `json:"fixed_bugs"`      // 已修复BUG
}

// ParsePayload 解析消息载荷
func (m *Message) ParsePayload(target interface{}) error {
	if err := json.Unmarshal(m.Payload, target); err != nil {
		return fmt.Errorf("解析payload失败: %w", err)
	}
	return nil
}

// ToJSON 转换为JSON字符串
func (m *Message) ToJSON() (string, error) {
	bytes, err := json.MarshalIndent(m, "", "  ")
	if err != nil {
		return "", fmt.Errorf("序列化消息失败: %w", err)
	}
	return string(bytes), nil
}

// FromJSON 从JSON解析消息
func FromJSON(data string) (*Message, error) {
	var msg Message
	if err := json.Unmarshal([]byte(data), &msg); err != nil {
		return nil, fmt.Errorf("反序列化消息失败: %w", err)
	}
	return &msg, nil
}
