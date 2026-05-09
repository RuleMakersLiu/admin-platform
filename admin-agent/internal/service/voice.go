package service

import (
	"bytes"
	"context"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"mime/multipart"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"sync"
	"time"
)

// VoiceConfig 语音服务配置
type VoiceConfig struct {
	// TTS 配置
	TTSEnabled    bool   `mapstructure:"tts_enabled"`
	TTSProvider   string `mapstructure:"tts_provider"`    // edge-tts, openai
	TTSCacheDir   string `mapstructure:"tts_cache_dir"`   // 音频缓存目录
	TTSDefaultLang string `mapstructure:"tts_default_lang"` // 默认语言

	// STT 配置
	STTEnabled    bool   `mapstructure:"stt_enabled"`
	STTProvider   string `mapstructure:"stt_provider"`    // whisper-api, whisper-local
	WhisperAPIKey string `mapstructure:"whisper_api_key"`
	WhisperModel  string `mapstructure:"whisper_model"`   // whisper-1, tiny, base, small, medium, large
	WhisperAPIURL string `mapstructure:"whisper_api_url"` // OpenAI API 地址

	// 通用配置
	MaxTextLength  int `mapstructure:"max_text_length"`  // 最大文本长度
	MaxAudioSize   int `mapstructure:"max_audio_size"`   // 最大音频大小(bytes)
	RequestTimeout int `mapstructure:"request_timeout"`  // 请求超时(秒)
}

// DefaultVoiceConfig 默认语音配置
func DefaultVoiceConfig() *VoiceConfig {
	return &VoiceConfig{
		TTSEnabled:     true,
		TTSProvider:    "edge-tts",
		TTSCacheDir:    "/tmp/voice_cache",
		TTSDefaultLang: "zh-CN",

		STTEnabled:     true,
		STTProvider:    "whisper-api",
		WhisperModel:   "whisper-1",
		WhisperAPIURL:  "https://api.openai.com/v1/audio/transcriptions",

		MaxTextLength:  5000,
		MaxAudioSize:   25 * 1024 * 1024, // 25MB
		RequestTimeout: 60,
	}
}

// VoiceService 语音服务
type VoiceService struct {
	config     *VoiceConfig
	httpClient *http.Client
	cache      sync.Map // 简单的内存缓存
}

// NewVoiceService 创建语音服务
func NewVoiceService(cfg *VoiceConfig) *VoiceService {
	if cfg == nil {
		cfg = DefaultVoiceConfig()
	}

	// 确保缓存目录存在
	if cfg.TTSCacheDir != "" {
		if err := os.MkdirAll(cfg.TTSCacheDir, 0755); err != nil {
			log.Printf("[VoiceService] 创建缓存目录失败: %v", err)
		}
	}

	return &VoiceService{
		config: cfg,
		httpClient: &http.Client{
			Timeout: time.Duration(cfg.RequestTimeout) * time.Second,
		},
	}
}

// ========== TTS 相关结构和方法 ==========

// TTSRequest TTS请求
type TTSRequest struct {
	Text     string `json:"text" binding:"required"`
	Language string `json:"language"` // zh-CN, en-US, ja-JP, ko-KR
	Voice    string `json:"voice"`    // 指定声音(可选)
	Speed    string `json:"speed"`    // 语速: slow, normal, fast
	Output   string `json:"output"`   // 输出格式: base64, url
}

// TTSResponse TTS响应
type TTSResponse struct {
	Success   bool   `json:"success"`
	Message   string `json:"message,omitempty"`
	AudioData string `json:"audio_data,omitempty"` // base64编码的音频数据
	AudioURL  string `json:"audio_url,omitempty"`  // 音频下载URL
	Format    string `json:"format"`               // 音频格式 mp3/wav
	Duration  int    `json:"duration,omitempty"`   // 预估时长(毫秒)
	Language  string `json:"language"`
	Voice     string `json:"voice"`
}

// EdgeTTSVoice Edge-TTS 支持的声音
var EdgeTTSVoices = map[string][]VoiceInfo{
	"zh-CN": {
		{Name: "xiaoxiao", Code: "zh-CN-XiaoxiaoNeural", Gender: "Female", Description: "晓晓 - 温柔女声"},
		{Name: "yunxi", Code: "zh-CN-YunxiNeural", Gender: "Male", Description: "云希 - 阳光男声"},
		{Name: "yunjian", Code: "zh-CN-YunjianNeural", Gender: "Male", Description: "云健 - 专业男声"},
		{Name: "xiaoyi", Code: "zh-CN-XiaoyiNeural", Gender: "Female", Description: "晓伊 - 活泼女声"},
		{Name: "yunxia", Code: "zh-CN-YunxiaNeural", Gender: "Male", Description: "云夏 - 儿童声"},
	},
	"en-US": {
		{Name: "jenny", Code: "en-US-JennyNeural", Gender: "Female", Description: "Jenny - Natural Female"},
		{Name: "guy", Code: "en-US-GuyNeural", Gender: "Male", Description: "Guy - Natural Male"},
		{Name: "aria", Code: "en-US-AriaNeural", Gender: "Female", Description: "Aria - Professional Female"},
		{Name: "davis", Code: "en-US-DavisNeural", Gender: "Male", Description: "Davis - Professional Male"},
	},
	"ja-JP": {
		{Name: "nanami", Code: "ja-JP-NanamiNeural", Gender: "Female", Description: "Nanami - Natural Female"},
		{Name: "keita", Code: "ja-JP-KeitaNeural", Gender: "Male", Description: "Keita - Natural Male"},
	},
	"ko-KR": {
		{Name: "sunhi", Code: "ko-KR-SunHiNeural", Gender: "Female", Description: "SunHi - Natural Female"},
		{Name: "injun", Code: "ko-KR-InJoonNeural", Gender: "Male", Description: "InJoon - Natural Male"},
	},
}

// VoiceInfo 声音信息
type VoiceInfo struct {
	Name        string `json:"name"`
	Code        string `json:"code"`
	Gender      string `json:"gender"`
	Description string `json:"description"`
}

// TextToSpeech 文本转语音
func (s *VoiceService) TextToSpeech(ctx context.Context, req *TTSRequest) (*TTSResponse, error) {
	// 参数校验
	if req.Text == "" {
		return nil, fmt.Errorf("文本不能为空")
	}

	if len(req.Text) > s.config.MaxTextLength {
		return nil, fmt.Errorf("文本长度超过限制(%d字符)", s.config.MaxTextLength)
	}

	// 设置默认语言
	if req.Language == "" {
		req.Language = s.config.TTSDefaultLang
	}

	// 验证语言支持
	if !s.isLanguageSupported(req.Language) {
		return nil, fmt.Errorf("不支持的语言: %s", req.Language)
	}

	// 选择默认声音
	if req.Voice == "" {
		req.Voice = s.getDefaultVoice(req.Language)
	}

	// 根据提供商处理
	var response *TTSResponse
	var err error

	switch s.config.TTSProvider {
	case "edge-tts":
		response, err = s.edgeTTS(ctx, req)
	case "openai":
		response, err = s.openaiTTS(ctx, req)
	default:
		response, err = s.edgeTTS(ctx, req)
	}

	if err != nil {
		return &TTSResponse{
			Success: false,
			Message: err.Error(),
		}, err
	}

	return response, nil
}

// edgeTTS 使用 Edge-TTS 进行语音合成
func (s *VoiceService) edgeTTS(ctx context.Context, req *TTSRequest) (*TTSResponse, error) {
	// 获取声音代码
	voiceCode := s.getVoiceCode(req.Language, req.Voice)
	if voiceCode == "" {
		voiceCode = req.Voice // 直接使用用户指定的声音代码
	}

	// 生成临时文件路径
	timestamp := time.Now().UnixNano()
	outputFile := filepath.Join(s.config.TTSCacheDir, fmt.Sprintf("tts_%d.mp3", timestamp))

	// 构建命令
	args := []string{
		"--text", req.Text,
		"--voice", voiceCode,
		"--write-media", outputFile,
	}

	// 设置语速
	if req.Speed != "" {
		rate := s.getSpeechRate(req.Speed)
		args = append(args, "--rate", rate)
	}

	// 执行 edge-tts 命令
	cmd := exec.CommandContext(ctx, "edge-tts", args...)
	var stderr bytes.Buffer
	cmd.Stderr = &stderr

	log.Printf("[VoiceService] 执行 edge-tts: voice=%s, text_length=%d", voiceCode, len(req.Text))

	if err := cmd.Run(); err != nil {
		log.Printf("[VoiceService] edge-tts 执行失败: %v, stderr: %s", err, stderr.String())
		return nil, fmt.Errorf("语音合成失败: %v", err)
	}

	// 读取生成的音频文件
	audioData, err := os.ReadFile(outputFile)
	if err != nil {
		return nil, fmt.Errorf("读取音频文件失败: %v", err)
	}

	// 根据输出格式返回
	response := &TTSResponse{
		Success:  true,
		Format:   "mp3",
		Language: req.Language,
		Voice:    voiceCode,
		Duration: s.estimateDuration(len(req.Text), req.Language),
	}

	switch req.Output {
	case "url":
		// 保留文件，返回相对URL
		response.AudioURL = fmt.Sprintf("/api/v1/voice/audio/%s", filepath.Base(outputFile))
	default:
		// 返回base64编码，删除临时文件
		response.AudioData = base64.StdEncoding.EncodeToString(audioData)
		os.Remove(outputFile)
	}

	return response, nil
}

// openaiTTS 使用 OpenAI TTS API 进行语音合成
func (s *VoiceService) openaiTTS(ctx context.Context, req *TTSRequest) (*TTSResponse, error) {
	// 这里可以实现 OpenAI TTS API 调用
	// 目前暂返回错误，提示使用 edge-tts
	return nil, fmt.Errorf("OpenAI TTS 暂未实现，请使用 edge-tts")
}

// ========== STT 相关结构和方法 ==========

// STTRequest STT请求(用于内部处理)
type STTRequest struct {
	Language string `json:"language"` // zh, en, ja, ko
	Model    string `json:"model"`    // whisper-1
}

// STTResponse STT响应
type STTResponse struct {
	Success   bool   `json:"success"`
	Message   string `json:"message,omitempty"`
	Text      string `json:"text"`               // 识别的文本
	Language  string `json:"language,omitempty"` // 检测到的语言
	Duration  float64 `json:"duration,omitempty"` // 音频时长(秒)
	Confidence float64 `json:"confidence,omitempty"` // 置信度
}

// SpeechToText 语音转文本
func (s *VoiceService) SpeechToText(ctx context.Context, file *multipart.FileHeader, language string) (*STTResponse, error) {
	// 检查文件大小
	if file.Size > int64(s.config.MaxAudioSize) {
		return nil, fmt.Errorf("音频文件大小超过限制(%dMB)", s.config.MaxAudioSize/1024/1024)
	}

	// 打开上传的文件
	src, err := file.Open()
	if err != nil {
		return nil, fmt.Errorf("打开音频文件失败: %v", err)
	}
	defer src.Close()

	// 读取文件内容
	audioData, err := io.ReadAll(src)
	if err != nil {
		return nil, fmt.Errorf("读取音频文件失败: %v", err)
	}

	// 根据提供商处理
	var response *STTResponse

	switch s.config.STTProvider {
	case "whisper-api":
		response, err = s.whisperAPI(ctx, audioData, file.Filename, language)
	case "whisper-local":
		response, err = s.whisperLocal(ctx, audioData, file.Filename, language)
	default:
		response, err = s.whisperAPI(ctx, audioData, file.Filename, language)
	}

	if err != nil {
		return &STTResponse{
			Success: false,
			Message: err.Error(),
		}, err
	}

	return response, nil
}

// whisperAPI 调用 OpenAI Whisper API
func (s *VoiceService) whisperAPI(ctx context.Context, audioData []byte, filename, language string) (*STTResponse, error) {
	// 检查 API Key
	apiKey := s.config.WhisperAPIKey
	if apiKey == "" {
		apiKey = os.Getenv("OPENAI_API_KEY")
	}
	if apiKey == "" {
		return nil, fmt.Errorf("未配置 Whisper API Key")
	}

	// 构建 multipart form
	body := &bytes.Buffer{}
	writer := multipart.NewWriter(body)

	// 添加文件字段
	part, err := writer.CreateFormFile("file", filename)
	if err != nil {
		return nil, fmt.Errorf("创建表单字段失败: %v", err)
	}
	if _, err := part.Write(audioData); err != nil {
		return nil, fmt.Errorf("写入文件数据失败: %v", err)
	}

	// 添加模型字段
	_ = writer.WriteField("model", s.config.WhisperModel)

	// 添加语言字段(可选)
	if language != "" {
		_ = writer.WriteField("language", s.normalizeLanguageCode(language))
	}

	// 关闭 writer
	if err := writer.Close(); err != nil {
		return nil, fmt.Errorf("关闭 multipart writer 失败: %v", err)
	}

	// 创建请求
	req, err := http.NewRequestWithContext(ctx, "POST", s.config.WhisperAPIURL, body)
	if err != nil {
		return nil, fmt.Errorf("创建请求失败: %v", err)
	}

	req.Header.Set("Content-Type", writer.FormDataContentType())
	req.Header.Set("Authorization", "Bearer "+apiKey)

	log.Printf("[VoiceService] 调用 Whisper API: model=%s, filename=%s, size=%d",
		s.config.WhisperModel, filename, len(audioData))

	// 发送请求
	resp, err := s.httpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("API 请求失败: %v", err)
	}
	defer resp.Body.Close()

	// 读取响应
	respBody, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("读取响应失败: %v", err)
	}

	// 检查状态码
	if resp.StatusCode != http.StatusOK {
		log.Printf("[VoiceService] Whisper API 错误: status=%d, body=%s", resp.StatusCode, string(respBody))
		return nil, fmt.Errorf("API 返回错误: %s", string(respBody))
	}

	// 解析响应
	var result struct {
		Text     string  `json:"text"`
		Language string  `json:"language"`
		Duration float64 `json:"duration"`
	}

	if err := json.Unmarshal(respBody, &result); err != nil {
		return nil, fmt.Errorf("解析响应失败: %v", err)
	}

	return &STTResponse{
		Success:    true,
		Text:       strings.TrimSpace(result.Text),
		Language:   result.Language,
		Duration:   result.Duration,
		Confidence: 0.95, // Whisper API 不返回置信度，使用默认值
	}, nil
}

// whisperLocal 使用本地 Whisper 模型
func (s *VoiceService) whisperLocal(ctx context.Context, audioData []byte, filename, language string) (*STTResponse, error) {
	// 保存临时音频文件
	timestamp := time.Now().UnixNano()
	tempFile := filepath.Join(s.config.TTSCacheDir, fmt.Sprintf("stt_%d_%s", timestamp, filename))

	if err := os.WriteFile(tempFile, audioData, 0644); err != nil {
		return nil, fmt.Errorf("保存临时文件失败: %v", err)
	}
	defer os.Remove(tempFile)

	// 构建 whisper 命令
	args := []string{tempFile, "--output_format", "json"}

	if language != "" {
		args = append(args, "--language", s.normalizeLanguageCode(language))
	}

	if s.config.WhisperModel != "" {
		args = append(args, "--model", s.config.WhisperModel)
	}

	// 执行 whisper 命令
	cmd := exec.CommandContext(ctx, "whisper", args...)
	var stdout, stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr

	log.Printf("[VoiceService] 执行本地 whisper: model=%s, file=%s", s.config.WhisperModel, tempFile)

	if err := cmd.Run(); err != nil {
		log.Printf("[VoiceService] whisper 执行失败: %v, stderr: %s", err, stderr.String())
		return nil, fmt.Errorf("语音识别失败: %v", err)
	}

	// 读取输出文件
	outputFile := strings.TrimSuffix(tempFile, filepath.Ext(tempFile)) + ".json"
	outputData, err := os.ReadFile(outputFile)
	if err != nil {
		return nil, fmt.Errorf("读取识别结果失败: %v", err)
	}
	defer os.Remove(outputFile)

	// 解析结果
	var result struct {
		Text string `json:"text"`
	}

	if err := json.Unmarshal(outputData, &result); err != nil {
		return nil, fmt.Errorf("解析识别结果失败: %v", err)
	}

	return &STTResponse{
		Success: true,
		Text:    strings.TrimSpace(result.Text),
	}, nil
}

// ========== 辅助方法 ==========

// isLanguageSupported 检查语言是否支持
func (s *VoiceService) isLanguageSupported(lang string) bool {
	supported := []string{"zh-CN", "en-US", "ja-JP", "ko-KR", "zh", "en", "ja", "ko"}
	for _, l := range supported {
		if strings.HasPrefix(lang, l) {
			return true
		}
	}
	return false
}

// getDefaultVoice 获取默认声音
func (s *VoiceService) getDefaultVoice(language string) string {
	voices, ok := EdgeTTSVoices[language]
	if !ok || len(voices) == 0 {
		return "xiaoxiao" // 默认中文女声
	}
	return voices[0].Name
}

// getVoiceCode 获取声音代码
func (s *VoiceService) getVoiceCode(language, voiceName string) string {
	voices, ok := EdgeTTSVoices[language]
	if !ok {
		return ""
	}
	for _, v := range voices {
		if v.Name == voiceName {
			return v.Code
		}
	}
	return ""
}

// getSpeechRate 获取语速参数
func (s *VoiceService) getSpeechRate(speed string) string {
	switch speed {
	case "slow":
		return "-20%"
	case "fast":
		return "+20%"
	default:
		return "+0%"
	}
}

// estimateDuration 估算语音时长
func (s *VoiceService) estimateDuration(textLength int, language string) int {
	// 粗略估算：中文约3字/秒，英文约15词/秒
	charsPerSecond := 3
	if strings.HasPrefix(language, "en") {
		charsPerSecond = 15
	}
	return (textLength / charsPerSecond) * 1000
}

// normalizeLanguageCode 标准化语言代码
func (s *VoiceService) normalizeLanguageCode(lang string) string {
	// 将 zh-CN 转换为 zh，en-US 转换为 en
	parts := strings.Split(lang, "-")
	if len(parts) > 0 {
		return parts[0]
	}
	return lang
}

// GetSupportedVoices 获取支持的声音列表
func (s *VoiceService) GetSupportedVoices(language string) []VoiceInfo {
	if language == "" {
		// 返回所有语言的声音
		var allVoices []VoiceInfo
		for _, voices := range EdgeTTSVoices {
			allVoices = append(allVoices, voices...)
		}
		return allVoices
	}
	return EdgeTTSVoices[language]
}

// GetSupportedLanguages 获取支持的语言列表
func (s *VoiceService) GetSupportedLanguages() []LanguageInfo {
	return []LanguageInfo{
		{Code: "zh-CN", Name: "中文", NativeName: "简体中文"},
		{Code: "en-US", Name: "English", NativeName: "English (US)"},
		{Code: "ja-JP", Name: "Japanese", NativeName: "日本語"},
		{Code: "ko-KR", Name: "Korean", NativeName: "한국어"},
	}
}

// LanguageInfo 语言信息
type LanguageInfo struct {
	Code        string `json:"code"`
	Name        string `json:"name"`
	NativeName  string `json:"native_name"`
}

// CleanupCache 清理过期缓存文件
func (s *VoiceService) CleanupCache(maxAge time.Duration) error {
	if s.config.TTSCacheDir == "" {
		return nil
	}

	entries, err := os.ReadDir(s.config.TTSCacheDir)
	if err != nil {
		return fmt.Errorf("读取缓存目录失败: %v", err)
	}

	now := time.Now()
	for _, entry := range entries {
		if entry.IsDir() {
			continue
		}

		info, err := entry.Info()
		if err != nil {
			continue
		}

		if now.Sub(info.ModTime()) > maxAge {
			filePath := filepath.Join(s.config.TTSCacheDir, entry.Name())
			os.Remove(filePath)
			log.Printf("[VoiceService] 清理过期缓存: %s", entry.Name())
		}
	}

	return nil
}
