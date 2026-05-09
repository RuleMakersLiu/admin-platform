package crypto

import (
	"encoding/base64"
	"testing"
)

// --- NewAESCrypto tests ---

func TestNewAESCrypto_ValidKeySizes(t *testing.T) {
	tests := []struct {
		name    string
		key     string
		keyLen  int
	}{
		{"AES-128 (16 bytes)", "1234567890abcdef", 16},
		{"AES-192 (24 bytes)", "1234567890abcdefghijklmn", 24},
		{"AES-256 (32 bytes)", "1234567890abcdefghijklmnopqrstuv", 32},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			crypto, err := NewAESCrypto(tt.key)
			if err != nil {
				t.Fatalf("expected no error for key of length %d, got: %v", tt.keyLen, err)
			}
			if crypto == nil {
				t.Fatal("expected non-nil AESCrypto instance")
			}
		})
	}
}

func TestNewAESCrypto_InvalidKeySizes(t *testing.T) {
	tests := []struct {
		name   string
		key    string
	}{
		{"empty key", ""},
		{"1 byte key", "a"},
		{"7 bytes key", "abcdefg"},
		{"15 bytes key", "1234567890abcde"},
		{"17 bytes key", "1234567890abcdefg"},
		{"20 bytes key", "1234567890abcdefghij"},
		{"48 bytes key", "1234567890abcdefghijklmnopqrstuvabcdefghijkl"},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			_, err := NewAESCrypto(tt.key)
			if err != ErrInvalidKey {
				t.Errorf("expected ErrInvalidKey for key length %d, got: %v", len(tt.key), err)
			}
		})
	}
}

// --- Encrypt / Decrypt roundtrip tests ---

func TestEncryptDecrypt_Roundtrip(t *testing.T) {
	key := "1234567890abcdef" // 16 bytes
	crypto, err := NewAESCrypto(key)
	if err != nil {
		t.Fatalf("failed to create AESCrypto: %v", err)
	}

	tests := []struct {
		name      string
		plaintext string
	}{
		{"simple ASCII", "hello world"},
		{"Chinese characters", "你好世界"},
		{"mixed Unicode", "Hello 你好 こんにちは 안녕하세요"},
		{"numbers", "1234567890"},
		{"special characters", "!@#$%^&*()_+-=[]{}|;':\",./<>?"},
		{"newlines and tabs", "line1\nline2\ttab\r\nwindows"},
		{"JSON payload", `{"key": "value", "nested": {"a": 1}}`},
		{"long string (500 chars)", string(make([]byte, 500))}, // will be zero bytes
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			encrypted, err := crypto.Encrypt(tt.plaintext)
			if err != nil {
				t.Fatalf("Encrypt failed: %v", err)
			}

			decrypted, err := crypto.Decrypt(encrypted)
			if err != nil {
				t.Fatalf("Decrypt failed: %v", err)
			}

			if decrypted != tt.plaintext {
				t.Errorf("roundtrip mismatch.\nexpected: %q\nactual:   %q", tt.plaintext, decrypted)
			}
		})
	}
}

func TestEncryptDecrypt_EmptyStrings(t *testing.T) {
	key := "1234567890abcdef"
	crypto, err := NewAESCrypto(key)
	if err != nil {
		t.Fatalf("failed to create AESCrypto: %v", err)
	}

	// Encrypt empty string should return empty string
	encrypted, err := crypto.Encrypt("")
	if err != nil {
		t.Fatalf("Encrypt('') failed: %v", err)
	}
	if encrypted != "" {
		t.Errorf("Encrypt('') expected empty string, got: %q", encrypted)
	}

	// Decrypt empty string should return empty string
	decrypted, err := crypto.Decrypt("")
	if err != nil {
		t.Fatalf("Decrypt('') failed: %v", err)
	}
	if decrypted != "" {
		t.Errorf("Decrypt('') expected empty string, got: %q", decrypted)
	}
}

func TestEncrypt_DifferentCiphertextsEachTime(t *testing.T) {
	key := "1234567890abcdef"
	crypto, err := NewAESCrypto(key)
	if err != nil {
		t.Fatalf("failed to create AESCrypto: %v", err)
	}

	plaintext := "same plaintext, different IV"
	enc1, err := crypto.Encrypt(plaintext)
	if err != nil {
		t.Fatalf("first Encrypt failed: %v", err)
	}
	enc2, err := crypto.Encrypt(plaintext)
	if err != nil {
		t.Fatalf("second Encrypt failed: %v", err)
	}

	if enc1 == enc2 {
		t.Error("expected different ciphertexts for the same plaintext due to random IV, but they were equal")
	}
}

// --- Decrypt error path tests ---

func TestDecrypt_InvalidBase64(t *testing.T) {
	key := "1234567890abcdef"
	crypto, err := NewAESCrypto(key)
	if err != nil {
		t.Fatalf("failed to create AESCrypto: %v", err)
	}

	_, err = crypto.Decrypt("not-valid-base64!!!")
	if err == nil {
		t.Error("expected error for invalid base64 input, got nil")
	}
}

func TestDecrypt_CiphertextTooShort(t *testing.T) {
	key := "1234567890abcdef"
	crypto, err := NewAESCrypto(key)
	if err != nil {
		t.Fatalf("failed to create AESCrypto: %v", err)
	}

	// Encode a very short byte slice that is less than aes.BlockSize (16)
	shortCipher := base64.StdEncoding.EncodeToString([]byte("short"))
	_, err = crypto.Decrypt(shortCipher)
	if err != ErrInvalidCiphertext {
		t.Errorf("expected ErrInvalidCiphertext, got: %v", err)
	}
}

func TestDecrypt_TruncatedCiphertext(t *testing.T) {
	key := "1234567890abcdef"
	crypto, err := NewAESCrypto(key)
	if err != nil {
		t.Fatalf("failed to create AESCrypto: %v", err)
	}

	// Encrypt something first
	encrypted, err := crypto.Encrypt("test data for truncation")
	if err != nil {
		t.Fatalf("Encrypt failed: %v", err)
	}

	// Decode, truncate to IV + partial block (not a multiple of aes.BlockSize)
	cipherBytes, _ := base64.StdEncoding.DecodeString(encrypted)
	// IV is 16 bytes; add 10 extra bytes (not a multiple of 16)
	truncated := base64.StdEncoding.EncodeToString(cipherBytes[:26])

	_, err = crypto.Decrypt(truncated)
	if err != ErrInvalidCiphertext {
		t.Errorf("expected ErrInvalidCiphertext for truncated ciphertext, got: %v", err)
	}
}

// --- Cross-key isolation test ---

func TestEncryptDecrypt_WrongKey(t *testing.T) {
	key1 := "1234567890abcdef"
	key2 := "abcdefghijklmnop"

	crypto1, _ := NewAESCrypto(key1)
	crypto2, _ := NewAESCrypto(key2)

	encrypted, err := crypto1.Encrypt("secret message")
	if err != nil {
		t.Fatalf("Encrypt failed: %v", err)
	}

	// Decrypting with a different key should fail (PKCS7 unpadding will be invalid)
	_, err = crypto2.Decrypt(encrypted)
	if err == nil {
		t.Error("expected error when decrypting with wrong key, got nil")
	}
}

// --- AES-256 key test ---

func TestEncryptDecrypt_AES256(t *testing.T) {
	key := "1234567890abcdefghijklmnopqrstuv" // 32 bytes
	crypto, err := NewAESCrypto(key)
	if err != nil {
		t.Fatalf("failed to create AES-256 crypto: %v", err)
	}

	plaintext := "AES-256 test with a longer key"
	encrypted, err := crypto.Encrypt(plaintext)
	if err != nil {
		t.Fatalf("Encrypt failed: %v", err)
	}

	decrypted, err := crypto.Decrypt(encrypted)
	if err != nil {
		t.Fatalf("Decrypt failed: %v", err)
	}

	if decrypted != plaintext {
		t.Errorf("AES-256 roundtrip mismatch.\nexpected: %q\nactual:   %q", plaintext, decrypted)
	}
}
