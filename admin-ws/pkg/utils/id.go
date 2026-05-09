package utils

import (
	"crypto/rand"
	"encoding/hex"
	"fmt"
	"time"
)

// GenerateID 生成唯一 ID
func GenerateID() string {
	b := make([]byte, 8)
	rand.Read(b)
	return fmt.Sprintf("%x%d", b, time.Now().UnixNano())
}

// GenerateSessionID 生成会话 ID
func GenerateSessionID() string {
	b := make([]byte, 16)
	rand.Read(b)
	return hex.EncodeToString(b)
}
