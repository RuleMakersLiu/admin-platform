package handler

import (
	"log"
	"net/http"

	"admin-gateway/internal/model"
	"admin-gateway/internal/service"

	"github.com/gin-gonic/gin"
)

var trackingService = service.NewTrackingService()

// TrackEvents 批量接收埋点事件
// @Summary 批量接收埋点事件
// @Description 接收前端批量上报的埋点事件，发送到Kafka
// @Tags tracking
// @Accept json
// @Produce json
// @Param events body model.BatchEventsRequest true "批量事件"
// @Success 200 {object} model.BatchEventsResponse
// @Failure 400 {object} gin.H
// @Failure 500 {object} gin.H
// @Router /api/tracking/events [post]
func TrackEvents(c *gin.Context) {
	var req model.BatchEventsRequest

	// 绑定请求
	if err := c.ShouldBindJSON(&req); err != nil {
		log.Printf("[Tracking] Invalid request: %v", err)
		c.JSON(http.StatusBadRequest, gin.H{
			"code":    400,
			"message": "Invalid request format",
			"error":   err.Error(),
		})
		return
	}

	// 验证事件数量
	if len(req.Events) == 0 {
		c.JSON(http.StatusBadRequest, gin.H{
			"code":    400,
			"message": "No events provided",
		})
		return
	}

	if len(req.Events) > 100 {
		c.JSON(http.StatusBadRequest, gin.H{
			"code":    400,
			"message": "Too many events in one batch (max 100)",
		})
		return
	}

	// 处理批量事件
	response, err := trackingService.ProcessBatch(c, &req)
	if err != nil {
		log.Printf("[Tracking] Failed to process batch: %v", err)
		c.JSON(http.StatusInternalServerError, gin.H{
			"code":    500,
			"message": "Failed to process events",
			"error":   err.Error(),
		})
		return
	}

	// 返回结果
	c.JSON(http.StatusOK, gin.H{
		"code":    200,
		"message": "Success",
		"data":    response,
	})
}

// TrackSingleEvent 接收单个埋点事件
// @Summary 接收单个埋点事件
// @Description 接收前端上报的单个埋点事件，发送到Kafka
// @Tags tracking
// @Accept json
// @Produce json
// @Param event body model.Event true "事件"
// @Success 200 {object} gin.H
// @Failure 400 {object} gin.H
// @Failure 500 {object} gin.H
// @Router /api/tracking/event [post]
func TrackSingleEvent(c *gin.Context) {
	var event model.Event

	// 绑定请求
	if err := c.ShouldBindJSON(&event); err != nil {
		log.Printf("[Tracking] Invalid event: %v", err)
		c.JSON(http.StatusBadRequest, gin.H{
			"code":    400,
			"message": "Invalid event format",
			"error":   err.Error(),
		})
		return
	}

	// 处理单个事件
	if err := trackingService.ProcessSingle(c, &event); err != nil {
		log.Printf("[Tracking] Failed to process event: %v", err)
		c.JSON(http.StatusInternalServerError, gin.H{
			"code":    500,
			"message": "Failed to process event",
			"error":   err.Error(),
		})
		return
	}

	// 返回结果
	c.JSON(http.StatusOK, gin.H{
		"code":    200,
		"message": "Success",
		"data": gin.H{
			"event_id": event.EventID,
		},
	})
}

// TrackingHealth 健康检查
// @Summary 埋点服务健康检查
// @Description 检查埋点服务和Kafka连接状态
// @Tags tracking
// @Produce json
// @Success 200 {object} model.TrackingHealthResponse
// @Router /api/tracking/health [get]
func TrackingHealth(c *gin.Context) {
	status := trackingService.GetHealthStatus()

	c.JSON(http.StatusOK, gin.H{
		"code":    200,
		"message": "Success",
		"data":    status,
	})
}

// GetDeviceID 获取设备ID
// @Summary 获取设备ID
// @Description 基于请求生成设备指纹ID
// @Tags tracking
// @Produce json
// @Success 200 {object} gin.H
// @Router /api/tracking/device-id [get]
func GetDeviceID(c *gin.Context) {
	deviceID := trackingService.GenerateDeviceID(c)

	c.JSON(http.StatusOK, gin.H{
		"code":    200,
		"message": "Success",
		"data": gin.H{
			"device_id": deviceID,
		},
	})
}
