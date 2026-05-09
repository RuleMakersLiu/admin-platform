package router

import (
	"net/http"

	"github.com/gin-gonic/gin"
	"gorm.io/gorm"

	"admin-agent/internal/config"
	"admin-agent/internal/handler"
	"admin-agent/internal/service"
	"admin-agent/pkg/prompt"
)

// SetupRouter 设置路由
func SetupRouter(agentService *service.AgentService, sandboxService *service.SandboxService, llmProviderService *service.LLMProviderService, db *gorm.DB) *gin.Engine {
	// 从全局配置创建语音服务
	var voiceService *service.VoiceService
	if config.GlobalConfig != nil {
		voiceCfg := convertVoiceConfig(&config.GlobalConfig.Voice)
		voiceService = service.NewVoiceService(voiceCfg)
	}

	return SetupRouterWithVoiceAndLLM(agentService, sandboxService, voiceService, llmProviderService, db)
}

// convertVoiceConfig 将 config.VoiceConfig 转换为 service.VoiceConfig
func convertVoiceConfig(cfg *config.VoiceConfig) *service.VoiceConfig {
	if cfg == nil {
		return nil
	}
	return &service.VoiceConfig{
		TTSEnabled:     cfg.TTSEnabled,
		TTSProvider:    cfg.TTSProvider,
		TTSCacheDir:    cfg.TTSCacheDir,
		TTSDefaultLang: cfg.TTSDefaultLang,
		STTEnabled:     cfg.STTEnabled,
		STTProvider:    cfg.STTProvider,
		WhisperAPIKey:  cfg.WhisperAPIKey,
		WhisperModel:   cfg.WhisperModel,
		WhisperAPIURL:  cfg.WhisperAPIURL,
		MaxTextLength:  cfg.MaxTextLength,
		MaxAudioSize:   cfg.MaxAudioSize,
		RequestTimeout: cfg.RequestTimeout,
	}
}

// SetupRouterWithVoiceAndLLM 设置路由(带语音服务和LLM提供商服务)
func SetupRouterWithVoiceAndLLM(agentService *service.AgentService, sandboxService *service.SandboxService, voiceService *service.VoiceService, llmProviderService *service.LLMProviderService, db *gorm.DB) *gin.Engine {
	router := gin.Default()

	// 健康检查
	router.GET("/health", func(c *gin.Context) {
		c.JSON(200, gin.H{
			"status":  "ok",
			"service": "admin-agent",
			"version": "1.0.0",
		})
	})

	// Prompt配置测试端点
	promptMgr := prompt.NewManager()
	router.GET("/api/v1/prompts/:agent_type", func(c *gin.Context) {
		agentType := c.Param("agent_type")
		cfg, err := promptMgr.GetPrompt(prompt.AgentType(agentType))
		if err != nil {
			c.JSON(http.StatusNotFound, gin.H{"error": err.Error()})
			return
		}
		c.JSON(http.StatusOK, gin.H{
			"agent_type": cfg.AgentType,
			"system_prompt": cfg.SystemPrompt,
			"model_config": cfg.ModelConfig,
		})
	})

	// 获取所有Prompt配置
	router.GET("/api/v1/prompts", func(c *gin.Context) {
		all := promptMgr.GetAllPrompts()
		result := make([]gin.H, 0)
		for _, cfg := range all {
			result = append(result, gin.H{
				"agent_type": cfg.AgentType,
				"system_prompt_length": len(cfg.SystemPrompt),
				"model_config": cfg.ModelConfig,
			})
		}
		c.JSON(http.StatusOK, gin.H{
			"total": len(result),
			"agents": result,
		})
	})

	// LLM提供商健康检查 (在 /api/llm 路径下)
	if llmProviderService != nil {
		llmHandler := handler.NewLLMHandler(llmProviderService)
		llm := router.Group("/api/llm")
		{
			llm.GET("/health", llmHandler.GetHealth)         // 获取健康状态
			llm.GET("/providers", llmHandler.GetProviders)   // 获取提供商列表
			llm.POST("/reload", llmHandler.ReloadProviders)  // 重新加载配置
			llm.POST("/test", llmHandler.TestProvider)       // 测试提供商
		}
	}

	// API v1
	v1 := router.Group("/api/v1")
	{
		// 对话相关
		chatHandler := handler.NewChatHandler(nil, agentService)
		chats := v1.Group("/chat")
		{
			chats.POST("", chatHandler.Chat)
			chats.POST("/stream", chatHandler.StreamChat) // 流式对话接口
			chats.GET("/sessions", chatHandler.ListSessions)
			chats.POST("/sessions", chatHandler.CreateSession)
			chats.GET("/sessions/:session_id", chatHandler.GetSessionHistory)
			chats.DELETE("/sessions/:session_id", chatHandler.DeleteSession)
		}

		// 项目相关
		projectHandler := handler.NewProjectHandler(agentService)
		projects := v1.Group("/projects")
		{
			projects.POST("", projectHandler.CreateProject)
			projects.GET("", projectHandler.ListProjects)
			projects.GET("/:id", projectHandler.GetProject)
		}

		// 任务相关
		taskHandler := handler.NewTaskHandler(agentService)
		tasks := v1.Group("/tasks")
		{
			tasks.GET("", taskHandler.ListTasks)
			tasks.PUT("/:id/status", taskHandler.UpdateTaskStatus)
		}

		// BUG相关
		bugHandler := handler.NewBugHandler(agentService)
		bugs := v1.Group("/bugs")
		{
			bugs.GET("", bugHandler.ListBugs)
			bugs.PUT("/:id/status", bugHandler.UpdateBugStatus)
		}

		// 知识库管理
		knowledgeService := service.NewKnowledgeService(db)
		knowledgeHandler := handler.NewKnowledgeHandler(knowledgeService)
		knowledge := v1.Group("/knowledge")
		{
			knowledge.GET("", knowledgeHandler.GetKnowledgeList)        // 获取知识列表
			knowledge.POST("", knowledgeHandler.CreateKnowledge)        // 创建知识
			knowledge.GET("/search", knowledgeHandler.SearchKnowledge)  // 搜索知识
			knowledge.GET("/:id", knowledgeHandler.GetKnowledge)        // 获取单个知识
			knowledge.PUT("/:id", knowledgeHandler.UpdateKnowledge)     // 更新知识
			knowledge.DELETE("/:id", knowledgeHandler.DeleteKnowledge)  // 删除知识
		}

		// 沙箱代码执行
		if sandboxService != nil {
			sandboxHandler := handler.NewSandboxHandler(sandboxService)
			sandbox := v1.Group("/sandbox")
			{
				sandbox.POST("/execute", sandboxHandler.Execute)     // 执行代码
				sandbox.GET("/health", sandboxHandler.HealthCheck)   // 健康检查
				sandbox.GET("/config", sandboxHandler.GetConfig)     // 获取配置
				sandbox.GET("/languages", sandboxHandler.SupportedLanguages) // 支持的语言
			}
		}

		// 语音服务
		if voiceService != nil {
			voiceHandler := handler.NewVoiceHandler(voiceService)
			voice := v1.Group("/voice")
			{
				voice.POST("/tts", voiceHandler.TextToSpeech)        // 文本转语音
				voice.POST("/stt", voiceHandler.SpeechToText)        // 语音转文本
				voice.GET("/voices", voiceHandler.GetVoices)         // 获取支持的声音
				voice.GET("/languages", voiceHandler.GetLanguages)   // 获取支持的语言
				voice.GET("/config", voiceHandler.GetConfig)         // 获取配置
				voice.GET("/audio/:filename", voiceHandler.GetAudioFile) // 获取音频文件
			}
		}

		// 技能市场服务
		// 注意: skillMarketService 需要从外部传入或在初始化时创建
		// 这里使用数据库和现有技能服务创建市场服务
		if agentService != nil {
			// 从 AgentService 获取数据库连接创建 SkillMarketService
			// 由于 AgentService 结构未暴露 db，这里创建独立的 handler
			skillMarketHandler := handler.NewSkillMarketHandler(db)
			skills := v1.Group("/skills/market")
			{
				skills.GET("", skillMarketHandler.ListMarketSkills)           // 获取市场技能列表
				skills.GET("/categories", skillMarketHandler.GetCategories)   // 获取技能分类
				skills.POST("/categories", skillMarketHandler.CreateCategory) // 创建技能分类(管理员)
				skills.POST("/publish", skillMarketHandler.PublishSkill)      // 发布技能到市场
				skills.GET("/:id", skillMarketHandler.GetMarketSkill)         // 获取技能详情
				skills.PUT("/:id", skillMarketHandler.UpdateSkill)            // 更新技能
				skills.DELETE("/:id", skillMarketHandler.DeleteSkill)         // 删除/下架技能
				skills.POST("/download/:id", skillMarketHandler.DownloadSkill)// 下载技能
				skills.POST("/rate/:id", skillMarketHandler.RateSkill)        // 评分技能
				skills.GET("/:id/ratings", skillMarketHandler.GetRatings)     // 获取评分列表
				skills.POST("/:id/review", skillMarketHandler.ReviewSkill)    // 审核技能(管理员)
			}
		}
	}

	return router
}

// SetupRouterWithVoice 设置路由(带语音服务) - 向后兼容
func SetupRouterWithVoice(agentService *service.AgentService, sandboxService *service.SandboxService, voiceService *service.VoiceService, db *gorm.DB) *gin.Engine {
	return SetupRouterWithVoiceAndLLM(agentService, sandboxService, voiceService, nil, db)
}
