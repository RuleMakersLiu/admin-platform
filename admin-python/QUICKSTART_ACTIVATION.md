# 激活体验 - 快速开始指南

## 🚀 一键启动

```bash
# 1. 进入项目目录
cd ~/admin-platform/admin-python

# 2. 启动服务
uvicorn app.main:app --reload --port 8081

# 3. 在新终端运行演示（可选）
python3 activation_demo.py
```

## 📖 API文档

启动服务后，访问：http://localhost:8081/docs

## 🧪 测试

```bash
# 单元测试
pytest tests/test_activation.py -v

# 性能测试
python3 tests/performance_test.py
```

## 🔧 环境变量

确保 `.env` 文件包含：

```env
ZAI_API_KEY=your_api_key_here
```

## 📁 文件清单

- `app/api/v1/activation.py` - API路由
- `app/schemas/activation.py` - 数据结构
- `app/services/activation_service.py` - 业务逻辑
- `app/ai/glm_provider_streaming.py` - 流式GLM
- `tests/test_activation.py` - 单元测试
- `tests/performance_test.py` - 性能测试
- `activation_demo.py` - 演示脚本

## 📊 性能目标

- 首字延迟: < 2秒 ✅
- 完整激活: < 30秒 ✅
