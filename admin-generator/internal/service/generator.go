package service

import (
	cfg "admin-generator/internal/config"
	"admin-generator/pkg/claude"
	"admin-generator/pkg/parser"
	"encoding/json"
	"fmt"
	"strconv"
	"strings"
	"text/template"
	"time"

	"gorm.io/gorm"
)

// FunctionConfig 功能配置
type FunctionConfig struct {
	ID             int64         `json:"id"`
	TableName      string        `json:"table_name"`
	FunctionName   string        `json:"function_name"`
	FunctionDesc   string        `json:"function_desc"`
	ModuleName     string        `json:"module_name"`
	BusinessName   string        `json:"business_name"`
	FormConfig     string        `json:"form_config"`
	TableConfig    string        `json:"table_config"`
	APIConfig      string        `json:"api_config"`
	GenType        int           `json:"gen_type"`
	IsTableCreated int           `json:"is_table_created"`
	IsJavaGenerated int          `json:"is_java_generated"`
	IsVueGenerated int           `json:"is_vue_generated"`
	Status         int           `json:"status"`
	TenantID       int64         `json:"tenant_id"`
	CreateTime     int64         `json:"create_time"`
	UpdateTime     int64         `json:"update_time"`
	Fields         []FieldConfig `json:"fields,omitempty"`
}

// FieldConfig 字段配置
type FieldConfig struct {
	ID           int64  `json:"id"`
	FunctionID   int64  `json:"function_id"`
	ColumnName   string `json:"column_name"`
	ColumnType   string `json:"column_type"`
	FieldName    string `json:"field_name"`
	FieldType    string `json:"field_type"`
	FieldLabel   string `json:"field_label"`
	HtmlType     string `json:"html_type"`
	DictType     string `json:"dict_type"`
	IsPK         int    `json:"is_pk"`
	IsRequired   int    `json:"is_required"`
	IsList       int    `json:"is_list"`
	IsForm       int    `json:"is_form"`
	IsQuery      int    `json:"is_query"`
	QueryType    string `json:"query_type"`
	ValidateRule string `json:"validate_rule"`
	Sort         int    `json:"sort"`
	TenantID     int64  `json:"tenant_id"`
	CreateTime   int64  `json:"create_time"`
	UpdateTime   int64  `json:"update_time"`
}

// ChatHistory 对话记录
type ChatHistory struct {
	ID             int64  `json:"id"`
	SessionID      string `json:"session_id"`
	AdminID        int64  `json:"admin_id"`
	Type           int    `json:"type"`  // 1命令式 2自然语言
	Command        string `json:"command"`
	Prompt         string `json:"prompt"`
	Response       string `json:"response"`
	StructuredData string `json:"structured_data"`
	TokensUsed     int    `json:"tokens_used"`
	ResponseTime   int    `json:"response_time"`
	Status         int    `json:"status"`
	TenantID       int64  `json:"tenant_id"`
	CreateTime     int64  `json:"create_time"`
}

// GeneratorService 生成服务
type GeneratorService struct {
	claudeClient *claude.Client
}

// NewGeneratorService 创建服务
func NewGeneratorService() *GeneratorService {
	return &GeneratorService{
		claudeClient: claude.NewClient(),
	}
}

// ProcessChat 处理对话
func (s *GeneratorService) ProcessChat(sessionID string, adminID int64, tenantID int64, prompt string) (*ChatHistory, error) {
	history := &ChatHistory{
		SessionID: sessionID,
		AdminID:   adminID,
		Prompt:    prompt,
		TenantID:  tenantID,
		Status:    1, // 处理中
		CreateTime: time.Now().UnixMilli(),
	}

	// 判断是命令还是自然语言
	if parser.IsCommand(prompt) {
		history.Type = 1
		return s.processCommand(history)
	}

	history.Type = 2
	return s.processNaturalLanguage(history)
}

// processCommand 处理命令
func (s *GeneratorService) processCommand(history *ChatHistory) (*ChatHistory, error) {
	cmd := parser.ParseCommand(history.Prompt)
	history.Command = string(cmd.Type)

	switch cmd.Type {
	case parser.CommandGenCRUD:
		return s.genCRUD(history, cmd)
	case parser.CommandGenMenu:
		return s.genMenu(history, cmd)
	case parser.CommandGenAPI:
		return s.genAPI(history, cmd)
	case parser.CommandHelp:
		history.Response = parser.GetHelpText()
		history.Status = 2
		return history, nil
	default:
		history.Response = "未知命令，输入 /help 查看帮助"
		history.Status = 3
		return history, nil
	}
}

// genCRUD 生成CRUD
func (s *GeneratorService) genCRUD(history *ChatHistory, cmd *parser.Command) (*ChatHistory, error) {
	tableName := cmd.Params["table"]
	functionName := cmd.Params["name"]

	if tableName == "" || functionName == "" {
		history.Response = "参数错误，请使用: /gen crud --table=表名 --name=功能名称"
		history.Status = 3
		return history, nil
	}

	// 保存功能配置
	config := &FunctionConfig{
		TableName:    tableName,
		FunctionName: functionName,
		ModuleName:   cmd.Params["module"],
		BusinessName: cmd.Params["business"],
		GenType:      1,
		Status:       1,
		TenantID:     history.TenantID,
		CreateTime:   time.Now().UnixMilli(),
		UpdateTime:   time.Now().UnixMilli(),
	}

	// 保存到数据库
	db := cfg.GetDB()
	result := db.Table("gen_function_config").Create(config)
	if result.Error != nil {
		history.Response = "保存配置失败: " + result.Error.Error()
		history.Status = 3
		return history, nil
	}

	// 生成代码
	code, err := s.generateCode(config)
	if err != nil {
		history.Response = "生成代码失败: " + err.Error()
		history.Status = 3
		return history, nil
	}

	history.Response = code
	history.Status = 2
	return history, nil
}

// genMenu 生成菜单
func (s *GeneratorService) genMenu(history *ChatHistory, cmd *parser.Command) (*ChatHistory, error) {
	name := cmd.Params["name"]
	parent := cmd.Params["parent"]

	if name == "" {
		history.Response = "参数错误，请使用: /gen menu --name=菜单名 --parent=父ID"
		history.Status = 3
		return history, nil
	}

	// 生成菜单SQL（转义用户输入防止注入）
	safeName := strings.ReplaceAll(name, "'", "''")
	safeName = strings.ReplaceAll(safeName, ";", "")
	safePath := strings.ReplaceAll(strings.ToLower(name), "'", "''")
	parentID := 0
	if parent != "" {
		parentID, _ = strconv.Atoi(parent)
	}
	sql := fmt.Sprintf(`INSERT INTO sys_menu (parent_id, name, path, component, permission, icon, type, visible, status, sort, tenant_id, create_time, update_time)
VALUES (%d, '%s', '/%s', '%s_index', '%s_list', 'folder', 2, 1, 1, 0, %d, %d, %d);`,
		parentID, safeName, safePath, safePath, safePath,
		history.TenantID, time.Now().UnixMilli(), time.Now().UnixMilli())

	history.Response = sql
	history.Status = 2
	return history, nil
}

// genAPI 生成API
func (s *GeneratorService) genAPI(history *ChatHistory, cmd *parser.Command) (*ChatHistory, error) {
	path := cmd.Params["path"]
	method := cmd.Params["method"]

	if path == "" {
		history.Response = "参数错误，请使用: /gen api --path=路径 --method=方法"
		history.Status = 3
		return history, nil
	}

	if method == "" {
		method = "GET"
	}

	// 生成API代码
	code := s.generateAPICode(path, method)
	history.Response = code
	history.Status = 2
	return history, nil
}

// processNaturalLanguage 处理自然语言
func (s *GeneratorService) processNaturalLanguage(history *ChatHistory) (*ChatHistory, error) {
	startTime := time.Now()

	// 调用Claude API解析
	config, err := s.claudeClient.ParseNaturalLanguage(history.Prompt)
	if err != nil {
		history.Response = "AI解析失败: " + err.Error()
		history.Status = 3
		return history, nil
	}

	history.StructuredData = config
	history.ResponseTime = int(time.Since(startTime).Milliseconds())

	// 解析配置
	var funcConfig FunctionConfig
	if err := json.Unmarshal([]byte(config), &funcConfig); err != nil {
		history.Response = "解析配置失败: " + err.Error()
		history.Status = 3
		return history, nil
	}

	// 生成代码
	code, err := s.generateCode(&funcConfig)
	if err != nil {
		history.Response = "生成代码失败: " + err.Error()
		history.Status = 3
		return history, nil
	}

	history.Response = code
	history.Status = 2
	return history, nil
}

// generateCode 生成代码
func (s *GeneratorService) generateCode(config *FunctionConfig) (string, error) {
	var result strings.Builder

	// 1. 生成SQL
	sql := s.generateSQL(config)
	result.WriteString("=== SQL建表语句 ===\n")
	result.WriteString(sql)
	result.WriteString("\n\n")

	// 2. 生成Java Entity
	entity := s.generateEntity(config)
	result.WriteString("=== Java Entity ===\n")
	result.WriteString(entity)
	result.WriteString("\n\n")

	// 3. 生成Java Service
	service := s.generateService(config)
	result.WriteString("=== Java Service ===\n")
	result.WriteString(service)
	result.WriteString("\n\n")

	// 4. 生成Vue List
	vueList := s.generateVueList(config)
	result.WriteString("=== Vue List ===\n")
	result.WriteString(vueList)

	return result.String(), nil
}

// generateSQL 生成SQL
func (s *GeneratorService) generateSQL(config *FunctionConfig) string {
	var sql strings.Builder
	sql.WriteString(fmt.Sprintf("CREATE TABLE `%s` (\n", config.TableName))
	sql.WriteString("  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT '主键ID',\n")

	for _, field := range config.Fields {
		sql.WriteString(fmt.Sprintf("  `%s` %s COMMENT '%s',\n",
			field.ColumnName, field.ColumnType, field.FieldLabel))
	}

	sql.WriteString("  `tenant_id` bigint(20) NOT NULL DEFAULT 0 COMMENT '租户ID',\n")
	sql.WriteString("  `create_time` bigint(20) NOT NULL COMMENT '创建时间',\n")
	sql.WriteString("  `update_time` bigint(20) NOT NULL COMMENT '更新时间',\n")
	sql.WriteString(fmt.Sprintf("  PRIMARY KEY (`id`)\n"))
	sql.WriteString(fmt.Sprintf(") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='%s';", config.FunctionName))

	return sql.String()
}

// generateEntity 生成Java Entity
func (s *GeneratorService) generateEntity(config *FunctionConfig) string {
	tmpl := `package com.admin.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;
import java.io.Serializable;

/**
 * {{.FunctionName}}实体
 */
@Data
@TableName("{{.TableName}}")
public class {{.ClassName}} implements Serializable {

    private static final long serialVersionUID = 1L;

    @TableId(type = IdType.AUTO)
    private Long id;
{{range .Fields}}
    /** {{.FieldLabel}} */
    private {{.FieldType}} {{.FieldName}};
{{end}}
    private Long tenantId;
    private Long createTime;
    private Long updateTime;
}
`

	className := strings.ToUpper(config.TableName[:1]) + strings.ToLower(config.TableName[1:])
	className = strings.ReplaceAll(className, "_", "")

	data := map[string]interface{}{
		"FunctionName": config.FunctionName,
		"TableName":    config.TableName,
		"ClassName":    className,
		"Fields":       config.Fields,
	}

	t, _ := template.New("entity").Parse(tmpl)
	var result strings.Builder
	t.Execute(&result, data)
	return result.String()
}

// generateService 生成Java Service
func (s *GeneratorService) generateService(config *FunctionConfig) string {
	className := strings.ToUpper(config.TableName[:1]) + strings.ToLower(config.TableName[1:])
	className = strings.ReplaceAll(className, "_", "")

	return fmt.Sprintf(`package com.admin.service;

import com.admin.entity.%s;
import com.admin.mapper.%sMapper;
import com.baomidou.mybatisplus.extension.service.impl.ServiceImpl;
import org.springframework.stereotype.Service;

/**
 * %s服务
 */
@Service
public class %sService extends ServiceImpl<%sMapper, %s> {

}`, className, className, config.FunctionName, className, className, className)
}

// generateVueList 生成Vue列表页
func (s *GeneratorService) generateVueList(config *FunctionConfig) string {
	return fmt.Sprintf(`<template>
  <div class="app-container">
    <a-table :columns="columns" :data-source="data" :loading="loading" />
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { get%sList } from '@/api/%s'

const loading = ref(false)
const data = ref([])

const columns = [
  { title: 'ID', dataIndex: 'id' },
  // 添加更多列
]

const fetchData = async () => {
  loading.value = true
  try {
    const res = await get%sList()
    data.value = res.data
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  fetchData()
})
</script>
`, config.FunctionName, config.TableName, config.FunctionName)
}

// generateAPICode 生成API代码
func (s *GeneratorService) generateAPICode(path, method string) string {
	return fmt.Sprintf(`/**
 * API接口
 * 路径: %s
 * 方法: %s
 */
@%s("%s")
public Result<?> handle%s() {
    // TODO: 实现业务逻辑
    return Result.success();
}`, method, path, method, path, method)
}

// SaveChatHistory 保存对话记录
func (s *GeneratorService) SaveChatHistory(history *ChatHistory) error {
	db := cfg.GetDB()
	return db.Table("gen_chat_history").Create(history).Error
}

// GetChatHistory 获取对话历史
func (s *GeneratorService) GetChatHistory(sessionID string) ([]ChatHistory, error) {
	var histories []ChatHistory
	db := cfg.GetDB()
	err := db.Table("gen_chat_history").
		Where("session_id = ?", sessionID).
		Order("create_time asc").
		Find(&histories).Error
	return histories, err
}

// ListConfig 获取配置列表
func (s *GeneratorService) ListConfig(tenantID int64, page, pageSize int) ([]FunctionConfig, int64, error) {
	db := cfg.GetDB()
	var total int64
	var configs []FunctionConfig

	db.Table("gen_function_config").Where("tenant_id = ?", tenantID).Count(&total)

	offset := (page - 1) * pageSize
	err := db.Table("gen_function_config").
		Where("tenant_id = ?", tenantID).
		Order("create_time desc").
		Offset(offset).Limit(pageSize).
		Find(&configs).Error
	if err != nil {
		return nil, 0, err
	}

	for i := range configs {
		var fields []FieldConfig
		db.Table("gen_field_config").
			Where("function_id = ?", configs[i].ID).
			Order("sort").
			Find(&fields)
		configs[i].Fields = fields
	}

	return configs, total, nil
}

// GetConfigByID 根据ID获取配置
func (s *GeneratorService) GetConfigByID(id int64, tenantID int64) (*FunctionConfig, error) {
	db := cfg.GetDB()
	var config FunctionConfig
	err := db.Table("gen_function_config").
		Where("id = ? AND tenant_id = ?", id, tenantID).
		First(&config).Error
	if err != nil {
		return nil, err
	}

	var fields []FieldConfig
	db.Table("gen_field_config").
		Where("function_id = ?", config.ID).
		Order("sort").
		Find(&fields)
	config.Fields = fields

	return &config, nil
}

// CreateConfig 创建配置
func (s *GeneratorService) CreateConfig(config *FunctionConfig, fields []FieldConfig) error {
	db := cfg.GetDB()
	return db.Transaction(func(tx *gorm.DB) error {
		if err := tx.Table("gen_function_config").Create(config).Error; err != nil {
			return err
		}
		for i := range fields {
			fields[i].FunctionID = config.ID
			fields[i].TenantID = config.TenantID
			fields[i].CreateTime = time.Now().UnixMilli()
			fields[i].UpdateTime = time.Now().UnixMilli()
		}
		if len(fields) > 0 {
			return tx.Table("gen_field_config").Create(&fields).Error
		}
		return nil
	})
}

// UpdateConfig 更新配置
func (s *GeneratorService) UpdateConfig(id int64, tenantID int64, config *FunctionConfig, fields []FieldConfig) error {
	db := cfg.GetDB()
	return db.Transaction(func(tx *gorm.DB) error {
		updates := map[string]interface{}{
			"table_name":    config.TableName,
			"function_name": config.FunctionName,
			"function_desc": config.FunctionDesc,
			"module_name":   config.ModuleName,
			"business_name": config.BusinessName,
			"form_config":   config.FormConfig,
			"table_config":  config.TableConfig,
			"api_config":    config.APIConfig,
			"gen_type":      config.GenType,
			"status":        config.Status,
			"update_time":   time.Now().UnixMilli(),
		}
		if err := tx.Table("gen_function_config").
			Where("id = ? AND tenant_id = ?", id, tenantID).
			Updates(updates).Error; err != nil {
			return err
		}
		tx.Table("gen_field_config").Where("function_id = ?", id).Delete(nil)
		for i := range fields {
			fields[i].FunctionID = id
			fields[i].TenantID = tenantID
			fields[i].CreateTime = time.Now().UnixMilli()
			fields[i].UpdateTime = time.Now().UnixMilli()
		}
		if len(fields) > 0 {
			return tx.Table("gen_field_config").Create(&fields).Error
		}
		return nil
	})
}

// DeleteConfig 删除配置
func (s *GeneratorService) DeleteConfig(id int64, tenantID int64) error {
	db := cfg.GetDB()
	return db.Transaction(func(tx *gorm.DB) error {
		tx.Table("gen_field_config").Where("function_id = ?", id).Delete(nil)
		return tx.Table("gen_function_config").
			Where("id = ? AND tenant_id = ?", id, tenantID).
			Delete(nil).Error
	})
}

// GenerateCodeFiles 根据配置生成代码文件
func (s *GeneratorService) GenerateCodeFiles(config *FunctionConfig) map[string]string {
	files := make(map[string]string)

	className := strings.ToUpper(config.TableName[:1]) + strings.ToLower(config.TableName[1:])
	className = strings.ReplaceAll(className, "_", "")

	files["sql/"+config.TableName+".sql"] = s.generateSQL(config)
	files["entity/"+className+".java"] = s.generateEntity(config)
	files["service/"+className+"Service.java"] = s.generateService(config)
	files["vue/"+config.TableName+"/index.vue"] = s.generateVueList(config)

	return files
}
