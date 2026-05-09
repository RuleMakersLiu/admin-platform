package handler

import (
	"net/http"
	"strings"

	"github.com/gin-gonic/gin"

	"admin-agent/internal/service"
)

// VoiceHandler 语音处理器
type VoiceHandler struct {
	voiceService *service.VoiceService
}

// NewVoiceHandler 创建语音处理器
func NewVoiceHandler(voiceService *service.VoiceService) *VoiceHandler {
	return &VoiceHandler{
		voiceService: voiceService,
	}
}

// TextToSpeech POST /api/v1/voice/tts - 文本转语音
// @Summary 文本转语音
// @Description 将文本转换为语音，支持中英日韩四种语言
// @Tags 语音服务
// @Accept json
// @Produce json
// @Param request body service.TTSRequest true "TTS请求"
// @Success 200 {object} service.TTSResponse
// @Failure 400 {object} gin.H
// @Failure 500 {object} gin.H
// @Router /api/v1/voice/tts [post]
func (h *VoiceHandler) TextToSpeech(c *gin.Context) {
	var req service.TTSRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{
			"success": false,
			"message": "参数错误: " + err.Error(),
		})
		return
	}

	// 设置默认输出格式
	if req.Output == "" {
		req.Output = "base64"
	}

	// 调用服务
	response, err := h.voiceService.TextToSpeech(c.Request.Context(), &req)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{
			"success": false,
			"message": err.Error(),
		})
		return
	}

	c.JSON(http.StatusOK, response)
}

// SpeechToText POST /api/v1/voice/stt - 语音转文本
// @Summary 语音转文本
// @Description 将语音文件转换为文本，使用Whisper API
// @Tags 语音服务
// @Accept multipart/form-data
// @Produce json
// @Param file formData file true "音频文件"
// @Param language formData string false "语言代码 (zh, en, ja, ko)"
// @Success 200 {object} service.STTResponse
// @Failure 400 {object} gin.H
// @Failure 500 {object} gin.H
// @Router /api/v1/voice/stt [post]
func (h *VoiceHandler) SpeechToText(c *gin.Context) {
	// 获取上传的文件
	file, err := c.FormFile("file")
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{
			"success": false,
			"message": "请上传音频文件: " + err.Error(),
		})
		return
	}

	// 获取语言参数
	language := c.DefaultPostForm("language", "")

	// 验证文件类型
	if !isValidAudioFile(file.Filename) {
		c.JSON(http.StatusBadRequest, gin.H{
			"success": false,
			"message": "不支持的音频格式，支持: mp3, wav, m4a, webm, mp4, mpeg, mpga, oga, ogg",
		})
		return
	}

	// 调用服务
	response, err := h.voiceService.SpeechToText(c.Request.Context(), file, language)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{
			"success": false,
			"message": err.Error(),
		})
		return
	}

	c.JSON(http.StatusOK, response)
}

// GetVoices GET /api/v1/voice/voices - 获取支持的声音列表
// @Summary 获取支持的声音
// @Description 获取TTS支持的声音列表
// @Tags 语音服务
// @Produce json
// @Param language query string false "语言代码 (zh-CN, en-US, ja-JP, ko-KR)"
// @Success 200 {object} gin.H
// @Router /api/v1/voice/voices [get]
func (h *VoiceHandler) GetVoices(c *gin.Context) {
	language := c.Query("language")
	voices := h.voiceService.GetSupportedVoices(language)

	c.JSON(http.StatusOK, gin.H{
		"success": true,
		"total":   len(voices),
		"voices":  voices,
	})
}

// GetLanguages GET /api/v1/voice/languages - 获取支持的语言列表
// @Summary 获取支持的语言
// @Description 获取语音服务支持的语言列表
// @Tags 语音服务
// @Produce json
// @Success 200 {object} gin.H
// @Router /api/v1/voice/languages [get]
func (h *VoiceHandler) GetLanguages(c *gin.Context) {
	languages := h.voiceService.GetSupportedLanguages()

	c.JSON(http.StatusOK, gin.H{
		"success":  true,
		"total":    len(languages),
		"languages": languages,
	})
}

// GetConfig GET /api/v1/voice/config - 获取语音服务配置
// @Summary 获取语音服务配置
// @Description 获取当前语音服务的配置信息
// @Tags 语音服务
// @Produce json
// @Success 200 {object} gin.H
// @Router /api/v1/voice/config [get]
func (h *VoiceHandler) GetConfig(c *gin.Context) {
	c.JSON(http.StatusOK, gin.H{
		"success": true,
		"config": gin.H{
			"tts_enabled":    true,
			"tts_provider":   "edge-tts",
			"stt_enabled":    true,
			"stt_provider":   "whisper-api",
			"max_text_length": 5000,
			"max_audio_size":  "25MB",
		},
	})
}

// GetAudioFile GET /api/v1/voice/audio/:filename - 获取音频文件
// @Summary 获取音频文件
// @Description 下载生成的音频文件
// @Tags 语音服务
// @Produce audio/mpeg
// @Param filename path string true "文件名"
// @Success 200 {file} binary
// @Failure 404 {object} gin.H
// @Router /api/v1/voice/audio/{filename} [get]
func (h *VoiceHandler) GetAudioFile(c *gin.Context) {
	filename := c.Param("filename")

	// 安全检查：防止路径遍历攻击
	if strings.Contains(filename, "..") || strings.Contains(filename, "/") {
		c.JSON(http.StatusBadRequest, gin.H{
			"success": false,
			"message": "无效的文件名",
		})
		return
	}

	// 从缓存目录提供文件
	// 这里需要根据实际缓存目录配置
	cacheDir := "/tmp/voice_cache"
	filePath := cacheDir + "/" + filename

	c.FileAttachment(filePath, filename)
}

// isValidAudioFile 验证音频文件类型
func isValidAudioFile(filename string) bool {
	ext := strings.ToLower(filename[strings.LastIndex(filename, ".")+1:])
	supportedFormats := map[string]bool{
		"mp3":  true,
		"mp4":  true,
		"mpeg": true,
		"mpga": true,
		"m4a":  true,
		"wav":  true,
		"webm": true,
		"oga":  true,
		"ogg":  true,
	}
	return supportedFormats[ext]
}
