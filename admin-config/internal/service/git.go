package service

import (
	"errors"
	"time"

	"admin-config/internal/config"
	"admin-config/internal/model"
	"admin-config/pkg/crypto"

	"gorm.io/gorm"
)

// GitService Git配置服务
type GitService struct {
	db     *gorm.DB
	crypto *crypto.AESCrypto
}

// NewGitService 创建Git服务
func NewGitService(db *gorm.DB) (*GitService, error) {
	aesCrypto, err := crypto.NewAESCrypto(config.GlobalConfig.Crypto.AESKey)
	if err != nil {
		return nil, err
	}
	return &GitService{
		db:     db,
		crypto: aesCrypto,
	}, nil
}

// Create 创建Git配置
func (s *GitService) Create(adminID, tenantID int64, req *model.GitConfigCreate) (*model.GitConfig, error) {
	// 加密Access Token
	encryptedToken, err := s.crypto.Encrypt(req.AccessToken)
	if err != nil {
		return nil, err
	}

	now := time.Now().UnixMilli()
	git := &model.GitConfig{
		Name:          req.Name,
		Platform:      req.Platform,
		BaseURL:       req.BaseURL,
		AccessToken:   encryptedToken,
		WebhookSecret: req.WebhookSecret,
		SSHKey:        req.SSHKey,
		ExtraConfig:   req.ExtraConfig,
		IsDefault:     req.IsDefault,
		Status:        1,
		TenantID:      tenantID,
		AdminID:       adminID,
		CreateTime:    now,
		UpdateTime:    now,
	}

	// 如果设置为默认，先取消其他默认配置
	if git.IsDefault == 1 {
		s.db.Model(&model.GitConfig{}).
			Where("tenant_id = ? AND is_default = 1", tenantID).
			Update("is_default", 0)
	}

	if err := s.db.Create(git).Error; err != nil {
		return nil, err
	}

	return git, nil
}

// Update 更新Git配置
func (s *GitService) Update(id int64, tenantID int64, req *model.GitConfigUpdate) (*model.GitConfig, error) {
	var git model.GitConfig
	if err := s.db.Where("id = ? AND tenant_id = ?", id, tenantID).First(&git).Error; err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, errors.New("配置不存在")
		}
		return nil, err
	}

	updates := make(map[string]interface{})

	if req.Name != "" {
		updates["name"] = req.Name
	}
	if req.BaseURL != "" {
		updates["base_url"] = req.BaseURL
	}
	if req.AccessToken != "" {
		encryptedToken, err := s.crypto.Encrypt(req.AccessToken)
		if err != nil {
			return nil, err
		}
		updates["access_token"] = encryptedToken
	}
	if req.WebhookSecret != "" {
		updates["webhook_secret"] = req.WebhookSecret
	}
	if req.SSHKey != "" {
		updates["ssh_key"] = req.SSHKey
	}
	if req.ExtraConfig != nil {
		updates["extra_config"] = req.ExtraConfig
	}
	if req.IsDefault != nil {
		// 如果设置为默认，先取消其他默认配置
		if *req.IsDefault == 1 {
			s.db.Model(&model.GitConfig{}).
				Where("tenant_id = ? AND is_default = 1 AND id != ?", tenantID, id).
				Update("is_default", 0)
		}
		updates["is_default"] = *req.IsDefault
	}
	if req.Status != nil {
		updates["status"] = *req.Status
	}

	updates["update_time"] = time.Now().UnixMilli()

	if err := s.db.Model(&git).Updates(updates).Error; err != nil {
		return nil, err
	}

	// 重新查询
	if err := s.db.Where("id = ?", id).First(&git).Error; err != nil {
		return nil, err
	}

	return &git, nil
}

// Delete 删除Git配置
func (s *GitService) Delete(id int64, tenantID int64) error {
	result := s.db.Where("id = ? AND tenant_id = ?", id, tenantID).Delete(&model.GitConfig{})
	if result.Error != nil {
		return result.Error
	}
	if result.RowsAffected == 0 {
		return errors.New("配置不存在")
	}
	return nil
}

// GetByID 根据ID获取Git配置
func (s *GitService) GetByID(id int64, tenantID int64) (*model.GitConfig, error) {
	var git model.GitConfig
	if err := s.db.Where("id = ? AND tenant_id = ?", id, tenantID).First(&git).Error; err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, errors.New("配置不存在")
		}
		return nil, err
	}
	return &git, nil
}

// List 获取Git配置列表
func (s *GitService) List(tenantID int64, platform string, status *int) ([]*model.GitConfig, int64, error) {
	var list []*model.GitConfig
	var total int64

	query := s.db.Model(&model.GitConfig{}).Where("tenant_id = ?", tenantID)

	if platform != "" {
		query = query.Where("platform = ?", platform)
	}
	if status != nil {
		query = query.Where("status = ?", *status)
	}

	if err := query.Count(&total).Error; err != nil {
		return nil, 0, err
	}

	if err := query.Order("is_default desc, create_time desc").Find(&list).Error; err != nil {
		return nil, 0, err
	}

	return list, total, nil
}

// GetDefault 获取默认Git配置
func (s *GitService) GetDefault(tenantID int64) (*model.GitConfig, error) {
	var git model.GitConfig
	if err := s.db.Where("tenant_id = ? AND is_default = 1 AND status = 1", tenantID).First(&git).Error; err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, errors.New("未配置默认Git")
		}
		return nil, err
	}
	return &git, nil
}

// DecryptAccessToken 解密Access Token（供内部调用使用）
func (s *GitService) DecryptAccessToken(encryptedToken string) (string, error) {
	return s.crypto.Decrypt(encryptedToken)
}

// DecryptSSHKey 解密SSH Key（供内部调用使用）
func (s *GitService) DecryptSSHKey(encryptedKey string) (string, error) {
	return s.crypto.Decrypt(encryptedKey)
}
