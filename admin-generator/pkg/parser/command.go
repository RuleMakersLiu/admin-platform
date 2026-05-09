package parser

import (
	"regexp"
	"strings"
)

// CommandType 命令类型
type CommandType string

const (
	CommandGenCRUD  CommandType = "/gen/crud"
	CommandGenMenu  CommandType = "/gen/menu"
	CommandGenAPI   CommandType = "/gen/api"
	CommandBuild    CommandType = "/build"
	CommandDeploy   CommandType = "/deploy"
	CommandHelp     CommandType = "/help"
	CommandUnknown  CommandType = "unknown"
)

// Command 解析后的命令
type Command struct {
	Type    CommandType
	Params  map[string]string
	RawText string
}

// ParseCommand 解析命令
// 支持格式:
//   /gen crud --table=user_info --name=用户信息
//   /gen menu --name=用户管理 --parent=1
//   /gen api --path=/api/user --method=GET
//   /build --project=admin-backend
//   /deploy --env=prod
func ParseCommand(text string) *Command {
	text = strings.TrimSpace(text)

	// 检查是否是命令
	if !strings.HasPrefix(text, "/") {
		return &Command{
			Type:    CommandUnknown,
			RawText: text,
		}
	}

	// 解析命令类型
	cmd := &Command{
		Params:  make(map[string]string),
		RawText: text,
	}

	parts := strings.Fields(text)
	if len(parts) == 0 {
		cmd.Type = CommandUnknown
		return cmd
	}

	// 确定命令类型
	cmdStr := strings.ToLower(parts[0])
	switch {
	case strings.HasPrefix(cmdStr, "/gen/crud"):
		cmd.Type = CommandGenCRUD
	case strings.HasPrefix(cmdStr, "/gen/menu"):
		cmd.Type = CommandGenMenu
	case strings.HasPrefix(cmdStr, "/gen/api"):
		cmd.Type = CommandGenAPI
	case cmdStr == "/build":
		cmd.Type = CommandBuild
	case cmdStr == "/deploy":
		cmd.Type = CommandDeploy
	case cmdStr == "/help":
		cmd.Type = CommandHelp
	default:
		cmd.Type = CommandUnknown
	}

	// 解析参数 --key=value
	paramRegex := regexp.MustCompile(`--(\w+)=([^\s]+)`)
	matches := paramRegex.FindAllStringSubmatch(text, -1)
	for _, match := range matches {
		if len(match) >= 3 {
			cmd.Params[match[1]] = match[2]
		}
	}

	return cmd
}

// IsCommand 检查是否是命令
func IsCommand(text string) bool {
	return strings.HasPrefix(strings.TrimSpace(text), "/")
}

// GetHelpText 获取帮助文本
func GetHelpText() string {
	return `支持的命令:

【代码生成】
/gen crud --table=表名 --name=功能名称    生成CRUD功能
/gen menu --name=菜单名 --parent=父ID     生成菜单
/gen api --path=路径 --method=方法        生成API接口

【构建部署】
/build --project=项目名                  构建项目
/deploy --env=环境                       部署项目

【自然语言】
直接输入需求描述，例如：
"创建一个商品管理功能，包含名称、价格、库存字段"

/help 显示此帮助信息
`
}
