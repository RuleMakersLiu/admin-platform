package response

import (
	"net/http"
	"time"

	"github.com/gin-gonic/gin"
)

// Response 统一响应结构
type Response struct {
	Code      int         `json:"code"`
	Message   string      `json:"message"`
	Data      interface{} `json:"data,omitempty"`
	Timestamp int64       `json:"timestamp"`
}

// Success 成功响应
func Success(c *gin.Context, data interface{}) {
	c.JSON(http.StatusOK, Response{
		Code:      0,
		Message:   "操作成功",
		Data:      data,
		Timestamp: time.Now().UnixMilli(),
	})
}

// SuccessWithMsg 成功响应（自定义消息）
func SuccessWithMsg(c *gin.Context, message string, data interface{}) {
	c.JSON(http.StatusOK, Response{
		Code:      0,
		Message:   message,
		Data:      data,
		Timestamp: time.Now().UnixMilli(),
	})
}

// Error 错误响应
func Error(c *gin.Context, code int, message string) {
	c.JSON(http.StatusOK, Response{
		Code:      code,
		Message:   message,
		Timestamp: time.Now().UnixMilli(),
	})
}

// BadRequest 400错误
func BadRequest(c *gin.Context, message string) {
	Error(c, 40000, message)
}

// Unauthorized 401错误
func Unauthorized(c *gin.Context, message string) {
	c.JSON(http.StatusUnauthorized, Response{
		Code:      40100,
		Message:   message,
		Timestamp: time.Now().UnixMilli(),
	})
}

// Forbidden 403错误
func Forbidden(c *gin.Context, message string) {
	c.JSON(http.StatusForbidden, Response{
		Code:      40300,
		Message:   message,
		Timestamp: time.Now().UnixMilli(),
	})
}

// NotFound 404错误
func NotFound(c *gin.Context, message string) {
	Error(c, 40001, message)
}

// InternalServerError 500错误
func InternalServerError(c *gin.Context, message string) {
	Error(c, 50000, message)
}

// PageData 分页数据结构
type PageData struct {
	List  interface{} `json:"list"`
	Total int64       `json:"total"`
}

// SuccessWithPage 分页成功响应
func SuccessWithPage(c *gin.Context, list interface{}, total int64) {
	Success(c, PageData{
		List:  list,
		Total: total,
	})
}
