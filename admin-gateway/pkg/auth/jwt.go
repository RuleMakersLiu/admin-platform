package auth

import (
	"errors"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"github.com/spf13/viper"
)

var (
	ErrTokenExpired     = errors.New("token已过期")
	ErrTokenInvalid     = errors.New("token无效")
	ErrTokenMalformed   = errors.New("token格式错误")
	ErrTokenNotValidYet = errors.New("token尚未生效")
)

// Claims JWT声明
type Claims struct {
	AdminID  int64  `json:"adminId"`
	Username string `json:"username"`
	TenantID int64  `json:"tenantId"`
	jwt.RegisteredClaims
}

// GenerateToken 生成Token
func GenerateToken(adminID int64, username string, tenantID int64) (string, error) {
	claims := Claims{
		AdminID:  adminID,
		Username: username,
		TenantID: tenantID,
		RegisteredClaims: jwt.RegisteredClaims{
			ExpiresAt: jwt.NewNumericDate(time.Now().Add(time.Duration(viper.GetInt("jwt.expiration")) * time.Second)),
			IssuedAt:  jwt.NewNumericDate(time.Now()),
			NotBefore: jwt.NewNumericDate(time.Now()),
			Issuer:    "admin-gateway",
		},
	}

	token := jwt.NewWithClaims(jwt.SigningMethodHS256, claims)
	return token.SignedString([]byte(viper.GetString("jwt.secret")))
}

// ParseToken 解析Token
func ParseToken(tokenString string) (*Claims, error) {
	token, err := jwt.ParseWithClaims(tokenString, &Claims{}, func(token *jwt.Token) (interface{}, error) {
		return []byte(viper.GetString("jwt.secret")), nil
	})

	if err != nil {
		if errors.Is(err, jwt.ErrTokenExpired) {
			return nil, ErrTokenExpired
		}
		if errors.Is(err, jwt.ErrTokenMalformed) {
			return nil, ErrTokenMalformed
		}
		if errors.Is(err, jwt.ErrTokenNotValidYet) {
			return nil, ErrTokenNotValidYet
		}
		return nil, ErrTokenInvalid
	}

	if claims, ok := token.Claims.(*Claims); ok && token.Valid {
		return claims, nil
	}

	return nil, ErrTokenInvalid
}

// RefreshToken 刷新Token
func RefreshToken(tokenString string) (string, error) {
	claims, err := ParseToken(tokenString)
	if err != nil {
		return "", err
	}

	return GenerateToken(claims.AdminID, claims.Username, claims.TenantID)
}
