---
id: frontend_development
name: frontend-development
description: "Generate frontend page code with multi-framework support. 根据需求生成前端页面代码，支持 Vue 2/3 + Ant Design、React + Ant Design 5、纯 HTML/CSS/JS。"
version: 1.1.0
category: development
agent_type: FE
metadata:
  hermes:
    tags: [frontend, vue, react, ant-design, code-generation, spa]
    related_skills: [requirement-analysis, ui-preview, code-review]
---

# 前端开发技能 (Frontend Development Skill)

## 概述

本技能由前端开发 Agent (FE) 执行，负责根据需求文档、页面设计、原型预览和 API 接口定义，生成完整的前端页面代码。

### 核心能力

- **多框架支持**: Vue 2 + antd-vue 1.x、Vue 3 + Ant Design Vue 4.x、React + Ant Design 5、纯 HTML/CSS/JS
- **页面类型全覆盖**: 列表页、详情页、表单页、仪表盘、设置页等标准后台管理页面
- **完整 CRUD**: 搜索、新增、编辑、删除、批量操作、导入导出
- **工程化输出**: 组件拆分、API 层封装、路由配置、类型定义

### 使用场景

- 流水线 `frontend_dev` 阶段自动调用
- 用户在 Chat 中指派 FE Agent 生成前端代码
- 接收 requirement-analysis 和 ui-preview 的产出作为输入

---

## 输入参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `requirement` | string | 是 | 需求描述或 PRD 文档 |
| `ui_spec` | string | 否 | UI 设计规范、页面设计文档 |
| `prototype_html` | string | 否 | 原型预览 HTML 代码 |
| `api_contract` | string | 否 | API 接口定义（OpenAPI / 手写格式） |
| `frontend_tech` | string | 否 | 前端技术栈，如 `vue3/antd-vue`、`react/antd5`、`html` |
| `session_id` | string | 否 | 会话 ID，用于上下文关联 |

---

## 输出格式

输出为 JSON 格式的 `code_files` 对象，每个键为文件路径，值为完整文件内容：

```json
{
  "code_files": [
    {
      "path": "src/views/user/UserList.vue",
      "content": "<template>...</template>"
    },
    {
      "path": "src/api/user.ts",
      "content": "import api from './request'..."
    },
    {
      "path": "src/router/modules/user.ts",
      "content": "export default [...]"
    }
  ]
}
```

### 文件组织规范

生成的代码文件应按以下结构组织：

| 技术栈 | 页面组件 | API 层 | 路由 | 类型定义 |
|--------|----------|--------|------|----------|
| Vue 2 | `src/views/{module}/index.vue` | `src/api/{module}.js` | `src/router/modules/{module}.js` | - |
| Vue 3 | `src/views/{module}/index.vue` | `src/api/{module}.ts` | `src/router/modules/{module}.ts` | `src/types/{module}.ts` |
| React | `src/pages/{module}/index.tsx` | `src/services/{module}.ts` | `src/routes/{module}.tsx` | `src/types/{module}.ts` |
| HTML | `index.html` | 内嵌 | - | - |

---

## 页面类型模板

### 1. 列表页 (表格列表页)

列表页是后台管理系统最常见的页面类型，包含搜索区域 + 数据表格 + 分页 + 操作按钮。

**结构组成**:

```
┌─────────────────────────────────────────────┐
│  搜索区域 (Search Form)                      │
│  [输入框] [下拉选择] [日期范围] [搜索] [重置]  │
├─────────────────────────────────────────────┤
│  操作栏 [新增] [批量删除] [导出]    [刷新]    │
├─────────────────────────────────────────────┤
│  数据表格 (Table)                             │
│  选择 | ID | 名称 | 状态 | 时间 | 操作       │
│  [x]   1   张三  启用   ...    编辑 删除     │
│  [ ]   2   李四  禁用   ...    编辑 删除     │
├─────────────────────────────────────────────┤
│  分页器: 共 100 条  < 1 2 3 ... 10 >         │
└─────────────────────────────────────────────┘
```

**核心要素**:
- 搜索表单: 支持输入框、下拉选择、日期范围、级联选择等筛选条件
- 操作按钮区: 新增、批量删除、导出、刷新，需做权限控制
- 数据表格: 列定义需包含数据字段映射、宽度、对齐方式、自定义渲染（Tag 状态、操作按钮）
- 分页: 前端分页或服务端分页，显示总数、页码跳转、每页条数切换
- 新增/编辑弹窗 (Modal) 或抽屉 (Drawer): 表单字段与搜索区域分离
- 删除确认: Popconfirm 或 Modal.confirm 二次确认

**交互流程**:
1. 页面加载自动请求列表数据（mounted / useEffect）
2. 搜索按钮触发表单校验 -> 带参数重新请求（重置页码为 1）
3. 重置按钮清空搜索条件 -> 重新请求
4. 新增按钮打开弹窗 -> 填写表单 -> 提交 -> 刷新列表
5. 编辑按钮回填数据到弹窗 -> 修改 -> 提交 -> 刷新列表
6. 删除按钮二次确认 -> 调用删除 API -> 刷新列表
7. 分页切换 -> 带分页参数重新请求
8. 表格行选择 -> 批量操作按钮可用

### 2. 详情页

详情页展示单条记录的完整信息，通常从列表页跳转进入。

**结构组成**:

```
┌─────────────────────────────────────────────┐
│  页面头部 [返回] 用户详情     [编辑] [删除]   │
├─────────────────────────────────────────────┤
│  基本信息卡片                                 │
│  ┌─────────────────────────────────────────┐ │
│  │  用户名:  admin                          │ │
│  │  邮箱:    admin@example.com              │ │
│  │  角色:    [管理员]                        │ │
│  │  状态:    ● 启用                          │ │
│  │  创建时间: 2024-01-01 12:00:00           │ │
│  └─────────────────────────────────────────┘ │
├─────────────────────────────────────────────┤
│  关联信息 (Tabs)                              │
│  [操作日志] [关联订单] [权限配置]              │
│  ┌─────────────────────────────────────────┐ │
│  │  Tab 内容区域                             │ │
│  └─────────────────────────────────────────┘ │
└─────────────────────────────────────────────┘
```

**核心要素**:
- 页面头部: 返回按钮、标题、操作按钮
- Descriptions 组件: 键值对展示，支持多列布局
- 卡片分组: 将字段按业务含义分组展示
- Tabs 标签页: 展示关联信息（日志、子表、关联数据）
- 状态标签: 用 Tag 组件高亮展示状态信息
- 时间格式化: BIGINT 毫秒时间戳转为可读日期格式

### 3. 表单页

表单页用于数据新增和编辑，可以独立页面或弹窗形式呈现。

**核心要素**:
- 表单布局: 支持水平 (horizontal)、垂直 (vertical)、行内 (inline) 三种模式
- 表单校验: 必填、格式、长度、自定义规则，实时校验 + 提交校验
- 字段类型: Input、Textarea、Select、Radio、Checkbox、DatePicker、Upload、Cascader
- 联动控制: 某些字段值变化时动态显示/隐藏其他字段
- 提交与取消: 提交前二次确认，取消时提示未保存的修改
- 防重复提交: 提交按钮 loading 状态

### 4. 仪表盘 (Dashboard)

仪表盘展示系统概览和关键指标。

**结构组成**:

```
┌──────────┬──────────┬──────────┬──────────┐
│ 总用户数  │ 今日新增  │ 活跃用户  │ 待处理   │
│  12,580  │   +128   │   3,420  │    15    │
└──────────┴──────────┴──────────┴──────────┘
┌─────────────────────┬─────────────────────┐
│  趋势图 (折线图)     │  分类统计 (饼图)     │
│                     │                     │
└─────────────────────┴─────────────────────┘
┌─────────────────────────────────────────────┐
│  最近活动 / 待办事项 / 快捷操作              │
└─────────────────────────────────────────────┘
```

**核心要素**:
- 统计卡片 (Statistic): 数字 + 趋势箭头 + 图标背景
- 图表组件: 折线图、柱状图、饼图（ECharts / @ant-design/charts）
- 表格: 最近操作记录、待办列表
- 快捷入口: 常用操作按钮或链接

### 5. 设置页

设置页使用 Tabs + Form 组合，通常包含多个配置分组。

**核心要素**:
- Tabs 标签页: 基本设置、安全设置、通知设置等分组
- 表单分区: 每个 Tab 内可再用 Card 或 Divider 分区
- Switch 开关: 布尔配置项使用开关组件
- 保存/重置: 每个 Tab 独立保存，或统一底部操作栏

---

## 框架约定

### Vue 2 + antd-vue 1.x

**适用场景**: 旧项目维护、PHP 混合开发、简单管理后台

**模板结构**:
```vue
<template>
  <div class="page-container">
    <!-- 搜索区域 -->
    <a-card class="search-card" :bordered="false">
      <a-form :form="searchForm" layout="inline">
        <a-form-item label="名称">
          <a-input v-decorator="['name']" placeholder="请输入名称" allowClear />
        </a-form-item>
        <a-form-item>
          <a-button type="primary" icon="search" @click="handleSearch">查询</a-button>
          <a-button @click="handleReset" style="margin-left: 8px">重置</a-button>
        </a-form-item>
      </a-form>
    </a-card>

    <!-- 表格区域 -->
    <a-card :bordered="false" style="margin-top: 16px">
      <div class="table-toolbar">
        <a-button type="primary" icon="plus" @click="handleAdd" v-if="hasPermission('add')">
          新增
        </a-button>
      </div>
      <a-table
        :columns="columns"
        :dataSource="dataSource"
        :loading="loading"
        :pagination="pagination"
        @change="handleTableChange"
        rowKey="id"
      >
        <template slot="status" slot-scope="text">
          <a-tag :color="text === 1 ? 'green' : 'red'">
            {{ text === 1 ? '启用' : '禁用' }}
          </a-tag>
        </template>
        <template slot="action" slot-scope="text, record">
          <a @click="handleEdit(record)">编辑</a>
          <a-divider type="vertical" />
          <a-popconfirm title="确定删除？" @confirm="handleDelete(record.id)">
            <a style="color: #ff4d4f">删除</a>
          </a-popconfirm>
        </template>
      </a-table>
    </a-card>

    <!-- 弹窗 -->
    <a-modal
      :title="modalTitle"
      :visible="visible"
      :confirmLoading="confirmLoading"
      @ok="handleSubmit"
      @cancel="handleCancel"
    >
      <a-form :form="form" layout="vertical">
        <a-form-item label="名称">
          <a-input v-decorator="['name', { rules: [{ required: true, message: '请输入名称' }] }]" />
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script>
import { fetchList, createItem, updateItem, deleteItem } from '@/api/module'

export default {
  name: 'ModuleList',
  data() {
    return {
      searchForm: this.$form.createForm(this),
      form: this.$form.createForm(this),
      dataSource: [],
      loading: false,
      visible: false,
      confirmLoading: false,
      editId: null,
      pagination: { current: 1, pageSize: 10, total: 0, showTotal: (total) => `共 ${total} 条` },
      columns: [
        { title: 'ID', dataIndex: 'id', width: 80 },
        { title: '名称', dataIndex: 'name' },
        { title: '状态', dataIndex: 'status', scopedSlots: { customRender: 'status' } },
        { title: '创建时间', dataIndex: 'create_time', customRender: (val) => this.formatTime(val) },
        { title: '操作', scopedSlots: { customRender: 'action' }, width: 180 },
      ],
    }
  },
  computed: {
    modalTitle() { return this.editId ? '编辑' : '新增' },
  },
  mounted() {
    this.loadData()
  },
  methods: {
    async loadData() {
      this.loading = true
      try {
        const params = this.searchForm.getFieldsValue()
        const { list, total } = await fetchList({
          ...params,
          page: this.pagination.current,
          page_size: this.pagination.pageSize,
        })
        this.dataSource = list || []
        this.pagination.total = total || 0
      } catch (e) {
        this.$message.error(e.message || '加载失败')
      } finally {
        this.loading = false
      }
    },
    handleSearch() { this.pagination.current = 1; this.loadData() },
    handleReset() { this.searchForm.resetFields(); this.handleSearch() },
    handleTableChange(pagination) { this.pagination.current = pagination.current; this.loadData() },
    handleAdd() { this.editId = null; this.visible = true; this.$nextTick(() => this.form.resetFields()) },
    handleEdit(record) {
      this.editId = record.id
      this.visible = true
      this.$nextTick(() => this.form.setFieldsValue(record))
    },
    handleSubmit() {
      this.form.validateFields(async (err, values) => {
        if (err) return
        this.confirmLoading = true
        try {
          if (this.editId) {
            await updateItem(this.editId, values)
            this.$message.success('更新成功')
          } else {
            await createItem(values)
            this.$message.success('创建成功')
          }
          this.visible = false
          this.loadData()
        } catch (e) {
          this.$message.error(e.message || '操作失败')
        } finally {
          this.confirmLoading = false
        }
      })
    },
    handleCancel() { this.visible = false },
    async handleDelete(id) {
      try {
        await deleteItem(id)
        this.$message.success('删除成功')
        this.loadData()
      } catch (e) {
        this.$message.error(e.message || '删除失败')
      }
    },
    formatTime(timestamp) {
      if (!timestamp) return '-'
      return new Date(timestamp).toLocaleString()
    },
    hasPermission(action) { return true },
  },
}
</script>

<style scoped>
.page-container { padding: 24px; }
.search-card { margin-bottom: 16px; }
.table-toolbar { margin-bottom: 16px; }
</style>
```

**关键约定**:
- 使用 Options API (`data`, `methods`, `computed`, `watch`, `mounted`)
- 使用 `this.$form.createForm(this)` 创建表单实例
- 使用 `v-decorator` 绑定表单字段
- 使用 `scopedSlots` 自定义表格列渲染
- 使用 scoped style 隔离样式
- 时间戳格式化使用 `new Date(timestamp).toLocaleString()`
- API 调用使用 `@/api/module` 统一封装

### Vue 3 + Ant Design Vue 4.x

**适用场景**: 新项目推荐方案、需要 TypeScript 支持、Composition API

**模板结构**:
```vue
<template>
  <div class="page-container">
    <a-card :bordered="false">
      <a-form :model="searchForm" layout="inline">
        <a-form-item label="名称" name="name">
          <a-input v-model:value="searchForm.name" placeholder="请输入" allow-clear />
        </a-form-item>
        <a-form-item>
          <a-space>
            <a-button type="primary" @click="handleSearch">
              <template #icon><SearchOutlined /></template>
              查询
            </a-button>
            <a-button @click="handleReset">重置</a-button>
          </a-space>
        </a-form-item>
      </a-form>
    </a-card>

    <a-card :bordered="false" style="margin-top: 16px">
      <a-table
        :columns="columns"
        :data-source="dataSource"
        :loading="loading"
        :pagination="pagination"
        @change="handleTableChange"
        row-key="id"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.dataIndex === 'status'">
            <a-tag :color="record.status === 1 ? 'green' : 'red'">
              {{ record.status === 1 ? '启用' : '禁用' }}
            </a-tag>
          </template>
          <template v-if="column.key === 'action'">
            <a @click="handleEdit(record)">编辑</a>
            <a-divider type="vertical" />
            <a-popconfirm title="确定删除？" @confirm="handleDelete(record.id)">
              <a style="color: #ff4d4f">删除</a>
            </a-popconfirm>
          </template>
        </template>
      </a-table>
    </a-card>

    <a-modal
      :title="modalTitle"
      :open="visible"
      :confirm-loading="confirmLoading"
      @ok="handleSubmit"
      @cancel="visible = false"
      destroy-on-close
    >
      <a-form ref="formRef" :model="formState" :rules="rules" layout="vertical">
        <a-form-item label="名称" name="name">
          <a-input v-model:value="formState.name" />
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import { SearchOutlined } from '@ant-design/icons-vue'
import type { FormInstance } from 'ant-design-vue'
import { fetchList, createItem, updateItem, deleteItem } from '@/api/module'
import type { ModuleItem, ModuleQuery } from '@/types/module'

// 搜索表单
const searchForm = reactive<ModuleQuery>({ name: '' })
const loading = ref(false)
const dataSource = ref<ModuleItem[]>([])
const pagination = reactive({ current: 1, pageSize: 10, total: 0 })

// 弹窗
const visible = ref(false)
const confirmLoading = ref(false)
const editId = ref<number | null>(null)
const formRef = ref<FormInstance>()
const formState = reactive<Partial<ModuleItem>>({ name: '' })
const rules = { name: [{ required: true, message: '请输入名称' }] }

const modalTitle = computed(() => editId.value ? '编辑' : '新增')

const columns = [
  { title: 'ID', dataIndex: 'id', width: 80 },
  { title: '名称', dataIndex: 'name' },
  { title: '状态', dataIndex: 'status' },
  { title: '创建时间', dataIndex: 'create_time' },
  { title: '操作', key: 'action', width: 180 },
]

async function loadData() {
  loading.value = true
  try {
    const { list, total } = await fetchList({ ...searchForm, page: pagination.current, page_size: pagination.pageSize })
    dataSource.value = list || []
    pagination.total = total || 0
  } catch (e: any) {
    message.error(e.message || '加载失败')
  } finally {
    loading.value = false
  }
}

function handleSearch() { pagination.current = 1; loadData() }
function handleReset() { Object.assign(searchForm, { name: '' }); handleSearch() }
function handleTableChange(pag: any) { pagination.current = pag.current; loadData() }

function handleAdd() {
  editId.value = null
  Object.assign(formState, { name: '' })
  visible.value = true
}

function handleEdit(record: ModuleItem) {
  editId.value = record.id
  Object.assign(formState, record)
  visible.value = true
}

async function handleSubmit() {
  try {
    await formRef.value?.validate()
  } catch { return }
  confirmLoading.value = true
  try {
    if (editId.value) {
      await updateItem(editId.value, formState)
      message.success('更新成功')
    } else {
      await createItem(formState)
      message.success('创建成功')
    }
    visible.value = false
    loadData()
  } catch (e: any) {
    message.error(e.message || '操作失败')
  } finally {
    confirmLoading.value = false
  }
}

async function handleDelete(id: number) {
  try {
    await deleteItem(id)
    message.success('删除成功')
    loadData()
  } catch (e: any) {
    message.error(e.message || '删除失败')
  }
}

onMounted(() => { loadData() })
</script>

<style scoped>
.page-container { padding: 24px; }
</style>
```

**关键约定**:
- 使用 `<script setup lang="ts">` 语法糖
- 使用 Composition API (`ref`, `reactive`, `computed`, `onMounted`)
- 使用 `v-model:value` 双向绑定（Vue 3 语法）
- 使用 `#bodyCell` 插槽统一处理表格自定义渲染
- Modal 的 `visible` 改为 `open`（Ant Design Vue 4.x）
- 使用 `destroy-on-close` 确保弹窗关闭时重置状态
- 类型定义使用 TypeScript interface

### React + Ant Design 5

**适用场景**: React 技术栈项目、需要丰富生态、大型前端应用

**模板结构**:
```tsx
import React, { useState, useEffect, useCallback } from 'react'
import {
  Card, Table, Button, Form, Input, Modal, Tag, Space,
  Popconfirm, message, Pagination,
} from 'antd'
import { PlusOutlined, SearchOutlined, ReloadOutlined } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import { fetchList, createItem, updateItem, deleteItem } from '@/services/module'
import type { ModuleItem, ModuleQuery } from '@/types/module'

const ModuleList: React.FC = () => {
  const [searchForm] = Form.useForm()
  const [form] = Form.useForm()

  const [dataSource, setDataSource] = useState<ModuleItem[]>([])
  const [loading, setLoading] = useState(false)
  const [pagination, setPagination] = useState({ current: 1, pageSize: 10, total: 0 })
  const [modalVisible, setModalVisible] = useState(false)
  const [confirmLoading, setConfirmLoading] = useState(false)
  const [editId, setEditId] = useState<number | null>(null)

  const loadData = useCallback(async (params?: Partial<ModuleQuery>) => {
    setLoading(true)
    try {
      const searchValues = searchForm.getFieldsValue()
      const res = await fetchList({
        ...searchValues,
        ...params,
        page: params?.page || pagination.current,
        page_size: params?.page_size || pagination.pageSize,
      })
      setDataSource(res.list || [])
      setPagination(prev => ({ ...prev, total: res.total || 0 }))
    } catch (e: any) {
      message.error(e.message || '加载失败')
    } finally {
      setLoading(false)
    }
  }, [searchForm, pagination.current, pagination.pageSize])

  useEffect(() => { loadData() }, [])

  const handleSearch = () => { setPagination(prev => ({ ...prev, current: 1 })); loadData({ page: 1 }) }
  const handleReset = () => { searchForm.resetFields(); handleSearch() }

  const handleAdd = () => {
    setEditId(null)
    form.resetFields()
    setModalVisible(true)
  }

  const handleEdit = (record: ModuleItem) => {
    setEditId(record.id)
    form.setFieldsValue(record)
    setModalVisible(true)
  }

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields()
      setConfirmLoading(true)
      if (editId) {
        await updateItem(editId, values)
        message.success('更新成功')
      } else {
        await createItem(values)
        message.success('创建成功')
      }
      setModalVisible(false)
      loadData()
    } catch (e: any) {
      if (e.message) message.error(e.message)
    } finally {
      setConfirmLoading(false)
    }
  }

  const handleDelete = async (id: number) => {
    try {
      await deleteItem(id)
      message.success('删除成功')
      loadData()
    } catch (e: any) {
      message.error(e.message || '删除失败')
    }
  }

  const columns: ColumnsType<ModuleItem> = [
    { title: 'ID', dataIndex: 'id', width: 80 },
    { title: '名称', dataIndex: 'name' },
    {
      title: '状态', dataIndex: 'status',
      render: (val: number) => (
        <Tag color={val === 1 ? 'green' : 'red'}>{val === 1 ? '启用' : '禁用'}</Tag>
      ),
    },
    {
      title: '创建时间', dataIndex: 'create_time',
      render: (val: number) => val ? new Date(val).toLocaleString() : '-',
    },
    {
      title: '操作', key: 'action', width: 180,
      render: (_, record) => (
        <Space>
          <a onClick={() => handleEdit(record)}>编辑</a>
          <Popconfirm title="确定删除？" onConfirm={() => handleDelete(record.id)}>
            <a style={{ color: '#ff4d4f' }}>删除</a>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div style={{ padding: 24 }}>
      <Card>
        <Form form={searchForm} layout="inline">
          <Form.Item name="name" label="名称">
            <Input placeholder="请输入" allowClear />
          </Form.Item>
          <Form.Item>
            <Space>
              <Button type="primary" icon={<SearchOutlined />} onClick={handleSearch}>查询</Button>
              <Button onClick={handleReset}>重置</Button>
            </Space>
          </Form.Item>
        </Form>
      </Card>

      <Card style={{ marginTop: 16 }}>
        <div style={{ marginBottom: 16 }}>
          <Button type="primary" icon={<PlusOutlined />} onClick={handleAdd}>新增</Button>
        </div>
        <Table
          columns={columns}
          dataSource={dataSource}
          loading={loading}
          rowKey="id"
          pagination={{
            ...pagination,
            showTotal: (total) => `共 ${total} 条`,
            onChange: (page) => { setPagination(prev => ({ ...prev, current: page })); loadData({ page }) },
          }}
        />
      </Card>

      <Modal
        title={editId ? '编辑' : '新增'}
        open={modalVisible}
        confirmLoading={confirmLoading}
        onOk={handleSubmit}
        onCancel={() => setModalVisible(false)}
        destroyOnClose
      >
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="名称" rules={[{ required: true, message: '请输入名称' }]}>
            <Input />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}

export default ModuleList
```

**关键约定**:
- 使用函数式组件 + Hooks (`useState`, `useEffect`, `useCallback`)
- TypeScript 类型注解贯穿全文件
- 使用 `Form.useForm()` 管理表单实例
- 表格列使用 `ColumnsType<T>` 类型定义
- 自定义渲染使用 `render` 函数
- Modal 的 `visible` 改为 `open`（Ant Design 5）
- 使用 `destroyOnClose` 确保弹窗状态干净

### 纯 HTML (CDN 方式)

**适用场景**: 原型预览、简单页面、无构建工具的 PHP 混合项目

**CDN 资源**:

| 资源 | CDN 地址 |
|------|----------|
| antd CSS | `https://cdn.jsdelivr.net/npm/ant-design-vue@1.7.8/dist/antd.min.css` |
| antd Icons | `https://cdn.jsdelivr.net/npm/@ant-design/icons@5.2.6/dist/index.umd.min.js` |

**约定**:
- 单 HTML 文件，内嵌 CSS 和 JS
- 使用 antd CSS 类名模拟组件外观（`.ant-btn`, `.ant-table`, `.ant-input`, `.ant-modal`, `.ant-tag` 等）
- 不引入任何框架（Vue/React），纯原生 JS 实现交互
- 弹窗通过 `document.getElementById().style.display` 控制显示隐藏
- Mock 数据内嵌，表格使用 JS 动态渲染
- 所有文字使用中文

---

## 通用模式

### CRUD 操作模式

所有列表页必须实现完整的 CRUD 生命周期：

1. **Create (新增)**:
   - 点击"新增"按钮 -> 打开 Modal/Drawer -> 空表单
   - 填写表单 -> 校验通过 -> 调用 POST API
   - 成功: `message.success('创建成功')` -> 关闭弹窗 -> 刷新列表
   - 失败: `message.error(错误信息)` -> 保持弹窗

2. **Read (列表查询)**:
   - 页面加载自动请求列表数据
   - 搜索表单提交 -> 携带参数重新请求（页码重置为 1）
   - 分页切换 -> 携带分页参数请求
   - 支持加载状态（Spin/Loading）和空状态（Empty）

3. **Update (编辑)**:
   - 点击"编辑" -> 打开 Modal/Drawer -> 回填数据到表单
   - 修改表单 -> 校验通过 -> 调用 PUT API
   - 成功: `message.success('更新成功')` -> 关闭弹窗 -> 刷新列表

4. **Delete (删除)**:
   - 点击"删除" -> `Popconfirm` 或 `Modal.confirm` 二次确认
   - 确认 -> 调用 DELETE API
   - 成功: `message.success('删除成功')` -> 刷新列表
   - 批量删除: 表格勾选 + 批量操作按钮

### 搜索与筛选

- 搜索表单使用 `layout="inline"` 水平排列
- 常见筛选字段: Input（名称/关键词）、Select（状态/类型）、DatePicker/RangePicker（时间范围）、Cascader（地区/分类）
- 搜索按钮始终在最后，配合"重置"按钮
- 搜索时自动将页码重置为 1
- 重置按钮清空所有搜索条件并重新请求

### 权限控制

- 页面级权限: 路由守卫控制页面访问
- 按钮/操作级权限: 使用 `v-if` (Vue) 或条件渲染 (React) 控制按钮显示
- 权限判断函数示例:
  ```javascript
  // Vue 2/3
  v-if="hasPermission('user:add')"

  // React
  {hasPermission('user:add') && <Button>新增</Button>}
  ```
- 表格操作列的编辑/删除按钮也需做权限控制

### 错误处理与反馈

- **API 成功反馈**: `message.success('操作成功')`
- **API 失败反馈**: `message.error(errorMessage)`
- **表单校验失败**: 字段下方红色提示文字
- **网络异常**: `message.error('网络错误，请检查网络连接')`
- **401 未授权**: 自动跳转登录页
- **Loading 状态**: 按钮 `loading` 属性 + 表格 `loading` 属性 + 页面级 `Spin`

### 加载状态管理

- **表格加载**: `loading` 属性控制，请求期间显示 Spin
- **按钮加载**: 提交按钮 `loading` / `confirmLoading` 防止重复提交
- **页面加载**: 首次加载使用 `Spin` 包裹整个内容区域
- **骨架屏**: 可选，使用 `Skeleton` 组件提升感知性能

---

## API 集成

### 请求层封装

每个模块独立一个 API 文件，统一封装增删改查接口：

```typescript
// src/api/module.ts 或 src/services/module.ts
import api from './request'

export function fetchList(params: QueryParams) {
  return api.get('/module/list', { params })
}

export function getItem(id: number) {
  return api.get(`/module/${id}`)
}

export function createItem(data: CreateParams) {
  return api.post('/module', data)
}

export function updateItem(id: number, data: UpdateParams) {
  return api.put(`/module/${id}`, data)
}

export function deleteItem(id: number) {
  return api.delete(`/module/${id}`)
}
```

### 请求配置

```typescript
// src/api/request.ts 或 src/services/request.ts
import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 120000,
  headers: { 'Content-Type': 'application/json' },
})

// 请求拦截器: 注入 JWT Token
api.interceptors.request.use((config) => {
  const token = getToken() // 从 store/cookie 获取
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// 响应拦截器: 统一错误处理
api.interceptors.response.use(
  (response) => {
    const { data } = response
    if (data.code === 200 || data.code === 0) return data.data
    return Promise.reject(new Error(data.message || '请求失败'))
  },
  (error) => {
    if (error.response?.status === 401) {
      clearToken()
      window.location.href = '/login'
    }
    const msg = error.response?.data?.message || '请求失败'
    return Promise.reject(new Error(msg))
  }
)
```

### 统一响应格式约定

后端 API 应返回统一格式：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "list": [],
    "total": 100
  }
}
```

分页请求参数约定：

| 参数 | 说明 | 示例 |
|------|------|------|
| `page` | 页码，从 1 开始 | `1` |
| `page_size` | 每页条数 | `10` |
| `keyword` | 搜索关键词 | `"张三"` |

### 时间戳处理

- 所有时间字段使用 BIGINT 毫秒时间戳
- 前端展示时统一格式化: `new Date(timestamp).toLocaleString()` 或 dayjs
- 表格列渲染中使用 `customRender` / `render` 进行格式化

---

## 样式约定

### 主题与配色

- 主色调: `#1890ff`（Ant Design 默认蓝）
- 成功色: `#52c41a`
- 警告色: `#faad14`
- 错误色: `#ff4d4f`
- 使用 Ant Design 的 Token 系统自定义主题

### 暗色主题支持

使用 Ant Design 的 ConfigProvider 配置暗色主题：

```javascript
// Vue
<a-config-provider :theme="{ algorithm: theme.darkAlgorithm }">

// React
<ConfigProvider theme={{ algorithm: theme.darkAlgorithm }}>
```

CSS 变量方案：

```css
:root {
  --bg-primary: #ffffff;
  --text-primary: rgba(0, 0, 0, 0.85);
}
[data-theme="dark"] {
  --bg-primary: #141414;
  --text-primary: rgba(255, 255, 255, 0.85);
}
```

### 响应式布局

使用 Ant Design Grid 系统：

```html
<a-row :gutter="16">
  <a-col :xs="24" :sm="12" :md="8" :lg="6">...</a-col>
  <a-col :xs="24" :sm="12" :md="16" :lg="18">...</a-col>
</a-row>
```

### 间距与排版

- 页面容器: `padding: 24px`
- 卡片间距: `margin-top: 16px` 或 `gap: 16px`
- 表格工具栏与表格间距: `margin-bottom: 16px`
- 按钮组间距: 使用 `<a-space>` 或 `<Space>` 组件

---

## 示例

### 示例 1: Vue 3 用户管理列表页

需求: 生成一个用户管理页面，包含用户列表、搜索、新增/编辑弹窗、删除确认、角色筛选。

**生成的代码文件**:

**文件: `src/views/user/index.vue`**
- 搜索区域: 用户名 Input + 角色 Select + 状态 Select + 日期范围 RangePicker
- 表格列: ID、用户名、邮箱、角色 (Tag)、状态 (Tag)、创建时间、操作
- 弹窗表单: 用户名、邮箱、手机号、角色 Select、状态 Switch
- 完整 CRUD 逻辑

**文件: `src/api/user.ts`**
- `fetchUserList(params)` - GET /user/list
- `getUserDetail(id)` - GET /user/:id
- `createUser(data)` - POST /user
- `updateUser(id, data)` - PUT /user/:id
- `deleteUser(id)` - DELETE /user/:id
- `getRoles()` - GET /role/list (用于角色下拉)

**文件: `src/types/user.ts`**
```typescript
export interface UserItem {
  id: number
  username: string
  email: string
  phone: string
  role_id: number
  role_name: string
  status: number
  create_time: number
  update_time: number
}

export interface UserQuery {
  username?: string
  role_id?: number
  status?: number
  date_range?: [number, number]
  page?: number
  page_size?: number
}
```

**文件: `src/router/modules/user.ts`**
```typescript
export default [
  {
    path: '/system/user',
    name: 'UserList',
    component: () => import('@/views/user/index.vue'),
    meta: { title: '用户管理', permission: 'system:user:list' },
  },
]
```

### 示例 2: React 订单管理页面（仪表盘 + 列表）

需求: 生成一个订单管理页面，顶部统计卡片展示今日订单数/总金额/待处理，下方订单列表支持搜索和状态筛选。

**生成的代码文件**:

**文件: `src/pages/order/index.tsx`**
- 统计卡片行: 3 个 Statistic 卡片 (今日订单、总金额、待处理)
- 搜索区域: 订单号 Input + 状态 Select + 下单时间 RangePicker
- 表格列: 订单号、客户名称、商品数量、订单金额、状态 (Tag 颜色映射)、下单时间、操作
- 操作列: 查看详情（跳转路由）、取消订单（二次确认）

**文件: `src/services/order.ts`**
```typescript
import api from './request'

export const orderApi = {
  getStatistics: () => api.get('/order/statistics'),
  getList: (params: OrderQuery) => api.get('/order/list', { params }),
  getDetail: (id: string) => api.get(`/order/${id}`),
  cancelOrder: (id: string) => api.put(`/order/${id}/cancel`),
}
```

**文件: `src/types/order.ts`**
```typescript
export interface OrderItem {
  id: string
  order_no: string
  customer_name: string
  product_count: number
  total_amount: number
  status: 'pending' | 'paid' | 'shipped' | 'completed' | 'cancelled'
  create_time: number
}

export interface OrderStatistics {
  today_count: number
  today_amount: number
  pending_count: number
}

export interface OrderQuery {
  order_no?: string
  status?: string
  date_range?: [number, number]
  page?: number
  page_size?: number
}
```

**状态颜色映射**:
```typescript
const STATUS_MAP: Record<string, { color: string; text: string }> = {
  pending: { color: 'orange', text: '待付款' },
  paid: { color: 'blue', text: '已付款' },
  shipped: { color: 'cyan', text: '已发货' },
  completed: { color: 'green', text: '已完成' },
  cancelled: { color: 'red', text: '已取消' },
}
```

---

## 反模式 (Anti-patterns)

### 禁止事项

1. **禁止直接在组件内写 API URL**: 所有接口调用必须通过独立的 API 层封装
   ```javascript
   // 错误
   axios.get('/api/user/list')

   // 正确
   import { fetchUserList } from '@/api/user'
   fetchUserList(params)
   ```

2. **禁止硬编码 Mock 数据**: 除非是纯 HTML 原型预览模式，否则必须调用真实 API

3. **禁止忽略错误处理**: 每个 API 调用必须有 try/catch 或 .catch 处理
   ```javascript
   // 错误
   const data = await fetchList(params)

   // 正确
   try {
     const data = await fetchList(params)
   } catch (e: any) {
     message.error(e.message || '加载失败')
   }
   ```

4. **禁止不加二次确认的删除操作**: 所有删除必须经过 Popconfirm 或 Modal.confirm

5. **禁止使用 `any` 类型作为函数参数或返回值**: 在 TypeScript 项目中必须定义具体类型

6. **禁止在模板/JSX 中写复杂逻辑**: 超过 3 行的逻辑应提取为方法/computed/hook

7. **禁止 `v-html` / `dangerouslySetInnerHTML` 渲染用户输入**: 防止 XSS 攻击

8. **禁止内联样式覆盖组件主题**: 使用 CSS 变量或 Ant Design Token 系统修改样式

### 性能注意事项

1. **大列表虚拟滚动**: 数据量超过 100 条时，表格需开启虚拟滚动或分页
2. **防抖搜索**: 输入框搜索建议添加 300ms 防抖
3. **图片懒加载**: 列表中如有图片，使用懒加载
4. **按需加载组件**: 使用动态 import (`() => import()`) 做路由级别代码拆分

### 代码规范

1. 组件命名使用 PascalCase: `UserList`, `OrderDetail`
2. 文件命名使用 kebab-case 或 PascalCase，与项目约定保持一致
3. 事件处理函数以 `handle` 前缀命名: `handleSearch`, `handleDelete`
4. API 函数以动词开头: `fetchList`, `createItem`, `updateItem`, `deleteItem`
5. 类型定义使用 PascalCase + 后缀: `UserItem`, `UserQuery`, `CreateUserParams`
6. 常量使用 UPPER_SNAKE_CASE: `STATUS_MAP`, `DEFAULT_PAGE_SIZE`
