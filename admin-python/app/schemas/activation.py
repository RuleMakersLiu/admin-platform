"""激活体验相关的Schemas"""
from typing import Optional, List
from pydantic import BaseModel, Field
from datetime import datetime


class ActivationStartRequest(BaseModel):
    """开始激活流程请求"""
    user_id: int = Field(..., alias="userId", description="用户ID")
    tenant_id: int = Field(..., alias="tenantId", description="租户ID")
    user_name: Optional[str] = Field(None, alias="userName", description="用户名称")
    
    class Config:
        populate_by_name = True


class ActivationStartResponse(BaseModel):
    """开始激活流程响应"""
    activation_id: str = Field(..., alias="activationId", description="激活会话ID")
    status: str = Field(default="ready", description="状态")
    welcome_message: str = Field(..., alias="welcomeMessage", description="欢迎消息")
    suggested_prompts: List[str] = Field(..., alias="suggestedPrompts", description="建议的提示词")
    
    class Config:
        populate_by_name = True


class TemplateItem(BaseModel):
    """演示模板项"""
    id: str = Field(..., description="模板ID")
    title: str = Field(..., description="模板标题")
    description: str = Field(..., description="模板描述")
    prompt: str = Field(..., description="模板提示词")
    category: str = Field(..., description="模板分类")
    icon: Optional[str] = Field(None, description="图标")
    
    class Config:
        populate_by_name = True


class TemplatesResponse(BaseModel):
    """模板列表响应"""
    templates: List[TemplateItem]
    categories: List[str]


class ActivationChatRequest(BaseModel):
    """激活对话请求"""
    activation_id: str = Field(..., alias="activationId", description="激活会话ID")
    message: str = Field(..., min_length=1, max_length=2000, description="用户消息")
    use_stream: bool = Field(default=True, alias="useStream", description="是否使用流式响应")
    
    class Config:
        populate_by_name = True


class ActivationCompleteRequest(BaseModel):
    """完成激活请求"""
    activation_id: str = Field(..., alias="activationId", description="激活会话ID")
    rating: Optional[int] = Field(None, ge=1, le=5, description="评分1-5")
    feedback: Optional[str] = Field(None, max_length=500, description="反馈")
    
    class Config:
        populate_by_name = True


class ActivationCompleteResponse(BaseModel):
    """完成激活响应"""
    status: str = Field(default="completed", description="状态")
    message: str = Field(default="激活完成", description="消息")
    next_steps: List[str] = Field(default=[], alias="nextSteps", description="后续步骤")
    
    class Config:
        populate_by_name = True


class ActivationStatus(BaseModel):
    """激活状态"""
    activation_id: str = Field(..., alias="activationId")
    status: str  # pending, ready, chatting, completed
    message_count: int = Field(default=0, alias="messageCount")
    started_at: int = Field(..., alias="startedAt")
    last_activity: int = Field(..., alias="lastActivity")
    
    class Config:
        populate_by_name = True
