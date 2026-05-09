package crypto

import (
	"bytes"
	"crypto/aes"
	"crypto/cipher"
	"crypto/rand"
	"encoding/base64"
	"errors"
	"io"
)

var (
	ErrInvalidKey      = errors.New("invalid key size, must be 16, 24 or 32 bytes")
	ErrInvalidCiphertext = errors.New("invalid ciphertext")
)

// AESCrypto AES加密器
type AESCrypto struct {
	key []byte
}

// NewAESCrypto 创建AES加密器
func NewAESCrypto(key string) (*AESCrypto, error) {
	keyBytes := []byte(key)
	keyLen := len(keyBytes)
	if keyLen != 16 && keyLen != 24 && keyLen != 32 {
		return nil, ErrInvalidKey
	}
	return &AESCrypto{key: keyBytes}, nil
}

// Encrypt 加密
func (a *AESCrypto) Encrypt(plaintext string) (string, error) {
	if plaintext == "" {
		return "", nil
	}

	block, err := aes.NewCipher(a.key)
	if err != nil {
		return "", err
	}

	// PKCS7填充
	plainBytes := []byte(plaintext)
	plainBytes = pkcs7Padding(plainBytes, block.BlockSize())

	// 创建加密块
	ciphertext := make([]byte, len(plainBytes)+aes.BlockSize)
	iv := ciphertext[:aes.BlockSize]
	if _, err := io.ReadFull(rand.Reader, iv); err != nil {
		return "", err
	}

	// CBC模式加密
	mode := cipher.NewCBCEncrypter(block, iv)
	mode.CryptBlocks(ciphertext[aes.BlockSize:], plainBytes)

	// Base64编码
	return base64.StdEncoding.EncodeToString(ciphertext), nil
}

// Decrypt 解密
func (a *AESCrypto) Decrypt(ciphertext string) (string, error) {
	if ciphertext == "" {
		return "", nil
	}

	// Base64解码
	cipherBytes, err := base64.StdEncoding.DecodeString(ciphertext)
	if err != nil {
		return "", err
	}

	if len(cipherBytes) < aes.BlockSize {
		return "", ErrInvalidCiphertext
	}

	block, err := aes.NewCipher(a.key)
	if err != nil {
		return "", err
	}

	// 提取IV
	iv := cipherBytes[:aes.BlockSize]
	cipherBytes = cipherBytes[aes.BlockSize:]

	if len(cipherBytes)%aes.BlockSize != 0 {
		return "", ErrInvalidCiphertext
	}

	// CBC模式解密
	mode := cipher.NewCBCDecrypter(block, iv)
	mode.CryptBlocks(cipherBytes, cipherBytes)

	// PKCS7去填充
	plainBytes, err := pkcs7UnPadding(cipherBytes)
	if err != nil {
		return "", err
	}

	return string(plainBytes), nil
}

// pkcs7Padding PKCS7填充
func pkcs7Padding(data []byte, blockSize int) []byte {
	padding := blockSize - len(data)%blockSize
	padText := bytes.Repeat([]byte{byte(padding)}, padding)
	return append(data, padText...)
}

// pkcs7UnPadding PKCS7去填充
func pkcs7UnPadding(data []byte) ([]byte, error) {
	length := len(data)
	if length == 0 {
		return nil, errors.New("empty data")
	}
	unPadding := int(data[length-1])
	if unPadding > length {
		return nil, errors.New("invalid padding")
	}
	return data[:length-unPadding], nil
}
