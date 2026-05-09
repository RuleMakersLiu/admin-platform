package handler

import (
	"fmt"
	"io"
	"log"
	"net/http"
	"net/http/httputil"
	"net/url"
	"strings"

	"github.com/gin-gonic/gin"
	"github.com/gorilla/websocket"
	"github.com/spf13/viper"
)

var wsUpgrader = websocket.Upgrader{
	CheckOrigin: func(r *http.Request) bool {
		return true
	},
}

// ProxyToPython 代理到Python后端
func ProxyToPython(c *gin.Context) {
	target := viper.GetString("services.python.host") + ":" + viper.GetString("services.python.port")
	prefix := viper.GetString("services.python.prefix")
	proxyRequestWithStrip(c, target, prefix, "/api")
}

// ProxyToGenerator 代理到代码生成服务
func ProxyToGenerator(c *gin.Context) {
	target := viper.GetString("services.generator.host") + ":" + viper.GetString("services.generator.port")
	prefix := viper.GetString("services.generator.prefix")
	proxyRequestWithStrip(c, target, prefix, "/api/generator")
}

// ProxyToDeploy 代理到部署服务
func ProxyToDeploy(c *gin.Context) {
	target := viper.GetString("services.deploy.host") + ":" + viper.GetString("services.deploy.port")
	prefix := viper.GetString("services.deploy.prefix")
	proxyRequestWithStrip(c, target, prefix, "/api/deploy")
}

// ProxyToAgent 代理到智能分身服务
func ProxyToAgent(c *gin.Context) {
	target := viper.GetString("services.agent.host") + ":" + viper.GetString("services.agent.port")
	prefix := viper.GetString("services.agent.prefix")
	proxyRequestWithStrip(c, target, prefix, "/api/agent")
}

// ProxyToConfig 代理到配置服务
func ProxyToConfig(c *gin.Context) {
	target := viper.GetString("services.config.host") + ":" + viper.GetString("services.config.port")
	prefix := viper.GetString("services.config.prefix")
	proxyRequestWithStrip(c, target, prefix, "/api/config")
}

// proxyRequest 代理请求
func proxyRequest(c *gin.Context, target string, prefix string) {
	proxyRequestWithStrip(c, target, prefix, "/api")
}

// proxyRequestWithStrip 代理请求（自定义前缀剥离）
func proxyRequestWithStrip(c *gin.Context, target string, prefix string, stripPrefix string) {
	remote, err := url.Parse("http://" + target)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{
			"code":    500,
			"message": "服务配置错误",
		})
		return
	}

	log.Printf("[DEBUG] 代理请求: target=%s, prefix=%s, path=%s", target, prefix, c.Request.URL.Path)

	proxy := httputil.NewSingleHostReverseProxy(remote)
	proxy.Director = func(req *http.Request) {
		req.URL.Scheme = remote.Scheme
		req.URL.Host = remote.Host

		// 处理路径前缀
		path := c.Request.URL.Path
		if prefix != "" {
			// 去除stripPrefix前缀，然后拼接prefix
			stripped := strings.TrimPrefix(path, stripPrefix)
			path = prefix + stripped
		}
		req.URL.Path = path

		log.Printf("[DEBUG] 转发到: %s%s", req.URL.Host, req.URL.Path)

		// 传递用户信息到后端
		if adminID, exists := c.Get("adminId"); exists {
			req.Header.Set("X-Admin-Id", toString(adminID))
		}
		if username, exists := c.Get("username"); exists {
			req.Header.Set("X-Username", toString(username))
		}
		if tenantID, exists := c.Get("tenantId"); exists {
			req.Header.Set("X-Tenant-Id", toString(tenantID))
		}

		// 传递原始Authorization头
		req.Header.Set("Authorization", c.GetHeader("Authorization"))
	}

	proxy.ErrorHandler = func(w http.ResponseWriter, r *http.Request, err error) {
		log.Printf("代理错误: %v", err)
		w.WriteHeader(http.StatusBadGateway)
		io.WriteString(w, `{"code":502,"message":"服务暂不可用"}`)
	}

	proxy.ServeHTTP(c.Writer, c.Request)
}

// toString 接口转字符串
func toString(v interface{}) string {
	if v == nil {
		return ""
	}
	switch val := v.(type) {
	case string:
		return val
	case int64:
		return fmt.Sprintf("%d", val)
	case int:
		return fmt.Sprintf("%d", val)
	default:
		return ""
	}
}

// ProxyWebSocket WebSocket代理
func ProxyWebSocket(c *gin.Context) {
	target := viper.GetString("services.ws.host") + ":" + viper.GetString("services.ws.port")

	// 升级客户端连接
	clientConn, err := wsUpgrader.Upgrade(c.Writer, c.Request, nil)
	if err != nil {
		log.Printf("WebSocket升级失败: %v", err)
		return
	}
	defer clientConn.Close()

	// 连接后端WebSocket服务
	backendURL := url.URL{Scheme: "ws", Host: target, Path: c.Request.URL.Path}
	backendConn, _, err := websocket.DefaultDialer.Dial(backendURL.String(), nil)
	if err != nil {
		log.Printf("连接后端WebSocket失败: %v", err)
		return
	}
	defer backendConn.Close()

	// 双向转发
	done := make(chan struct{})

	// 客户端 -> 后端
	go func() {
		defer close(done)
		for {
			messageType, message, err := clientConn.ReadMessage()
			if err != nil {
				return
			}
			backendConn.WriteMessage(messageType, message)
		}
	}()

	// 后端 -> 客户端
	for {
		select {
		case <-done:
			return
		default:
			messageType, message, err := backendConn.ReadMessage()
			if err != nil {
				return
			}
			clientConn.WriteMessage(messageType, message)
		}
	}
}

// ProxyToWS 代理到WebSocket服务的HTTP端点
func ProxyToWS(c *gin.Context) {
	target := viper.GetString("services.ws.host") + ":" + viper.GetString("services.ws.port")
	proxyRequestWithStrip(c, target, "", "/api/ws")
}
