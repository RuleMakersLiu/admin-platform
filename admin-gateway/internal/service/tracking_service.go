package service

import (
	"crypto/md5"
	"encoding/hex"
	"fmt"
	"log"
	"net"
	"net/url"
	"regexp"
	"strings"
	"time"

	"admin-gateway/internal/kafka"
	"admin-gateway/internal/model"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
)

// TrackingService 埋点服务
type TrackingService struct {
	producer *kafka.Producer
}

// NewTrackingService 创建埋点服务
func NewTrackingService() *TrackingService {
	return &TrackingService{
		producer: kafka.GetProducer(),
	}
}

// ProcessBatch 处理批量事件
func (s *TrackingService) ProcessBatch(c *gin.Context, req *model.BatchEventsRequest) (*model.BatchEventsResponse, error) {
	response := &model.BatchEventsResponse{
		Errors: make([]string, 0),
	}

	// 获取客户端信息
	clientIP := c.ClientIP()
	userAgent := c.GetHeader("User-Agent")

	// 获取认证信息（如果有）
	var adminID, username, tenantID string
	if id, exists := c.Get("adminId"); exists {
		adminID = fmt.Sprintf("%v", id)
	}
	if name, exists := c.Get("username"); exists {
		username = fmt.Sprintf("%v", name)
	}
	if tid, exists := c.Get("tenantId"); exists {
		tenantID = fmt.Sprintf("%v", tid)
	}

	for i, event := range req.Events {
		// 补充缺失的字段
		if event.EventID == "" {
			event.EventID = uuid.New().String()
		}
		if event.Timestamp == 0 {
			event.Timestamp = time.Now().UnixMilli()
		}
		if event.Source == "" {
			event.Source = "api"
		}

		// 补充认证信息
		if event.AdminID == "" && adminID != "" {
			event.AdminID = adminID
		}
		if event.Username == "" && username != "" {
			event.Username = username
		}
		if event.TenantID == "" && tenantID != "" {
			event.TenantID = tenantID
		}

		// 补充客户端信息
		if event.IP == "" {
			event.IP = clientIP
		}
		if event.UserAgent == "" {
			event.UserAgent = userAgent
		}

		// 解析User-Agent补充设备信息
		if event.OS == "" || event.Browser == "" {
			s.parseUserAgent(&event)
		}

		// 解析IP地理位置（简单实现）
		if event.City == "" {
			s.parseGeoIP(&event)
		}

		// 验证事件
		if err := s.validateEvent(&event); err != nil {
			response.Failed++
			response.Errors = append(response.Errors, fmt.Sprintf("event[%d]: %v", i, err))
			continue
		}

		// 发送到Kafka
		if err := s.producer.Send(event); err != nil {
			response.Failed++
			response.Errors = append(response.Errors, fmt.Sprintf("event[%d]: failed to send: %v", i, err))
			continue
		}

		response.Success++
	}

	return response, nil
}

// ProcessSingle 处理单个事件
func (s *TrackingService) ProcessSingle(c *gin.Context, event *model.Event) error {
	// 构造批量请求
	batchReq := &model.BatchEventsRequest{
		Events: []model.Event{*event},
	}

	// 处理
	resp, err := s.ProcessBatch(c, batchReq)
	if err != nil {
		return err
	}

	if resp.Failed > 0 && len(resp.Errors) > 0 {
		return fmt.Errorf("%s", resp.Errors[0])
	}

	return nil
}

// validateEvent 验证事件
func (s *TrackingService) validateEvent(event *model.Event) error {
	if event.EventType == "" {
		return fmt.Errorf("event_type is required")
	}
	if event.EventName == "" {
		return fmt.Errorf("event_name is required")
	}
	if event.Timestamp == 0 {
		return fmt.Errorf("timestamp is required")
	}

	// 验证时间戳范围（不能是未来，也不能太久以前）
	now := time.Now().UnixMilli()
	if event.Timestamp > now+60000 { // 允许1分钟的时间偏差
		return fmt.Errorf("timestamp cannot be in the future")
	}
	if event.Timestamp < now-86400000*365 { // 不能超过1年前
		return fmt.Errorf("timestamp is too old")
	}

	return nil
}

// parseUserAgent 解析User-Agent
func (s *TrackingService) parseUserAgent(event *model.Event) {
	ua := event.UserAgent
	if ua == "" {
		return
	}

	// 简单的User-Agent解析（生产环境建议使用专业库）
	ua = strings.ToLower(ua)

	// 解析OS
	if strings.Contains(ua, "windows") {
		event.OS = "Windows"
		if strings.Contains(ua, "windows nt 10") {
			event.OSVersion = "10"
		} else if strings.Contains(ua, "windows nt 6.3") {
			event.OSVersion = "8.1"
		} else if strings.Contains(ua, "windows nt 6.2") {
			event.OSVersion = "8"
		} else if strings.Contains(ua, "windows nt 6.1") {
			event.OSVersion = "7"
		}
	} else if strings.Contains(ua, "mac os") {
		event.OS = "MacOS"
		// 提取版本号
		re := regexp.MustCompile(`mac os x (\d+[._]\d+)`)
		matches := re.FindStringSubmatch(ua)
		if len(matches) > 1 {
			event.OSVersion = strings.Replace(matches[1], "_", ".", -1)
		}
	} else if strings.Contains(ua, "linux") {
		event.OS = "Linux"
	} else if strings.Contains(ua, "android") {
		event.OS = "Android"
		event.DeviceType = "mobile"
		re := regexp.MustCompile(`android (\d+\.?\d*)`)
		matches := re.FindStringSubmatch(ua)
		if len(matches) > 1 {
			event.OSVersion = matches[1]
		}
	} else if strings.Contains(ua, "iphone") || strings.Contains(ua, "ipad") {
		if strings.Contains(ua, "ipad") {
			event.OS = "iPadOS"
			event.DeviceType = "tablet"
		} else {
			event.OS = "iOS"
			event.DeviceType = "mobile"
		}
		re := regexp.MustCompile(`os (\d+[._]\d+)`)
		matches := re.FindStringSubmatch(ua)
		if len(matches) > 1 {
			event.OSVersion = strings.Replace(matches[1], "_", ".", -1)
		}
	}

	// 解析Browser
	if strings.Contains(ua, "edg/") {
		event.Browser = "Edge"
		re := regexp.MustCompile(`edg/(\d+\.?\d*)`)
		matches := re.FindStringSubmatch(ua)
		if len(matches) > 1 {
			event.BrowserVersion = matches[1]
		}
	} else if strings.Contains(ua, "chrome") {
		event.Browser = "Chrome"
		re := regexp.MustCompile(`chrome/(\d+\.?\d*)`)
		matches := re.FindStringSubmatch(ua)
		if len(matches) > 1 {
			event.BrowserVersion = matches[1]
		}
	} else if strings.Contains(ua, "firefox") {
		event.Browser = "Firefox"
		re := regexp.MustCompile(`firefox/(\d+\.?\d*)`)
		matches := re.FindStringSubmatch(ua)
		if len(matches) > 1 {
			event.BrowserVersion = matches[1]
		}
	} else if strings.Contains(ua, "safari") && !strings.Contains(ua, "chrome") {
		event.Browser = "Safari"
		re := regexp.MustCompile(`version/(\d+\.?\d*)`)
		matches := re.FindStringSubmatch(ua)
		if len(matches) > 1 {
			event.BrowserVersion = matches[1]
		}
	}

	// 设置设备类型
	if event.DeviceType == "" {
		if strings.Contains(ua, "mobile") || strings.Contains(ua, "iphone") {
			event.DeviceType = "mobile"
		} else if strings.Contains(ua, "tablet") || strings.Contains(ua, "ipad") {
			event.DeviceType = "tablet"
		} else {
			event.DeviceType = "desktop"
		}
	}
}

// parseGeoIP 解析IP地理位置（简单实现）
func (s *TrackingService) parseGeoIP(event *model.Event) {
	// 生产环境应使用专业的GeoIP库，如 https://github.com/oschwald/geoip2-golang
	// 这里只是简单实现，识别内网IP
	ip := event.IP
	if ip == "" {
		return
	}

	// 检查是否为内网IP
	if s.isPrivateIP(ip) {
		event.Country = "CN"
		event.Province = "Local"
		event.City = "Local"
	}
}

// isPrivateIP 检查是否为私有IP
func (s *TrackingService) isPrivateIP(ipStr string) bool {
	ip := net.ParseIP(ipStr)
	if ip == nil {
		return false
	}

	// 检查是否为私有IP段
	privateBlocks := []string{
		"10.0.0.0/8",
		"172.16.0.0/12",
		"192.168.0.0/16",
		"127.0.0.0/8",
		"169.254.0.0/16",
	}

	for _, block := range privateBlocks {
		_, cidr, _ := net.ParseCIDR(block)
		if cidr.Contains(ip) {
			return true
		}
	}

	return false
}

// GenerateDeviceID 生成设备ID（基于User-Agent和IP的指纹）
func (s *TrackingService) GenerateDeviceID(c *gin.Context) string {
	ua := c.GetHeader("User-Agent")
	ip := c.ClientIP()
	acceptLang := c.GetHeader("Accept-Language")
	acceptEnc := c.GetHeader("Accept-Encoding")

	// 组合生成指纹
	data := fmt.Sprintf("%s|%s|%s|%s", ua, ip, acceptLang, acceptEnc)
	hash := md5.Sum([]byte(data))
	return hex.EncodeToString(hash[:])
}

// SanitizePageURL 清理和规范化页面URL
func (s *TrackingService) SanitizePageURL(pageURL string) string {
	if pageURL == "" {
		return ""
	}

	// 解析URL
	parsed, err := url.Parse(pageURL)
	if err != nil {
		return pageURL
	}

	// 移除敏感查询参数（如token）
	sensitiveParams := []string{"token", "access_token", "auth", "key", "secret", "password"}
	query := parsed.Query()
	for _, param := range sensitiveParams {
		if query.Has(param) {
			query.Set(param, "REDACTED")
		}
	}
	parsed.RawQuery = query.Encode()

	return parsed.String()
}

// GetHealthStatus 获取健康状态
func (s *TrackingService) GetHealthStatus() *model.TrackingHealthResponse {
	connected := s.producer.IsConnected()
	queueSize, processedCount, failedCount, lastProcessTime := s.producer.GetStats()

	return &model.TrackingHealthResponse{
		Status:          map[bool]string{true: "healthy", false: "unhealthy"}[connected],
		KafkaConnected:  connected,
		QueueSize:       queueSize,
		ProcessedCount:  processedCount,
		FailedCount:     failedCount,
		LastProcessTime: lastProcessTime,
		Version:         "1.0.0",
	}
}

// LogEvent 记录事件（用于调试）
func (s *TrackingService) LogEvent(event *model.Event) {
	log.Printf("[Tracking] Event: type=%s, name=%s, user=%s, ip=%s",
		event.EventType, event.EventName, event.Username, event.IP)
}
