# 拼团活动管理功能 PM 交付包

## 交付目标
为后台运营人员提供拼团活动管理能力，支持创建拼团活动、配置商品 SKU、设置成团规则、查看活动效果和处理异常团单。该交付包用于验证产品流水线能产出真实产品经理可评审的需求分析、页面设计、API 契约、测试计划和交付检查清单。

## 需求分析执行记录
1. 输入盘点：用户需要一个团购类功能；前端参考项目为后台管理前端；后端参考项目为营销/商品/订单服务；缺失信息包括真实接口前缀、库存锁定策略和退款策略。
2. 业务目标拆解：通过拼团优惠提升商品转化；目标用户为运营、客服、财务和系统管理员；不做 C 端拼团页、不做支付通道、不做复杂分销。
3. 功能点拆分：P0 覆盖活动列表、创建/编辑、详情、启停、手动成团、失败退款；P1 覆盖复制活动、导出、活动数据看板；P2 覆盖活动模板。
4. 流程建模：运营创建活动，系统校验商品和库存，活动上线后用户参团，达到人数自动成团，超时未成团自动失败并触发退款。
5. 数据建模：核心对象包括 group_buy_activity、group_buy_sku、group_buy_team、group_buy_order、group_buy_refund_log。
6. 权限建模：按菜单、页面、按钮、API 和数据范围拆分，运营可管理本租户活动，客服可查看团单和退款，财务可导出结算数据。
7. 边界排查：覆盖空数据、加载中、无权限、接口失败、重复提交、并发库存、数据越权、非法价格、分页越界、活动状态非法流转。
8. 验收标准落地：每个 P0 功能给出可测试场景、操作、预期结果和验证数据。
9. 待确认收口：真实商品选择接口、库存锁定时机、退款回调字段、手动成团审批流需由产品和后端确认。

## PRD

### 项目概述
业务目标：在后台提供拼团活动配置和运营管理能力，帮助运营快速配置团购活动并追踪成团效果。

目标用户：
- 运营：创建、编辑、上下线、复制、查看活动效果。
- 客服：查询团单、处理异常团单和退款状态。
- 财务：导出活动订单和退款数据。
- 系统管理员：配置权限和查看审计日志。

前端参考项目：后台管理前端，复用列表、表单、弹窗、权限和分页组件。

后端参考项目：营销活动服务、商品 SKU 服务、订单服务和退款服务。

### 范围边界
本次做：
- 拼团活动列表、创建/编辑、详情、启停、复制。
- 拼团规则配置，包括团购价、成团人数、成团时限、活动时间、限购规则、库存占用策略。
- 团单查询、手动成团、失败退款状态查看。
- 权限、数据范围、审计和导出。

本次不做：
- C 端拼团详情页和分享链路。
- 支付通道、退款通道和库存系统底层实现。
- 多级分销、优惠券叠加和会员等级差异价。

### 功能需求列表
| 优先级 | 功能点 | 触发条件 | 输入 | 处理规则 | 输出结果 |
| --- | --- | --- | --- | --- | --- |
| P0 | 活动列表查询 | 进入菜单或点击查询 | 活动名称、商品、状态、时间范围、创建人 | 支持分页、排序、重置、数据范围过滤 | 展示活动列表和统计摘要 |
| P0 | 创建拼团活动 | 点击新增 | 商品 SKU、团购价、成团人数、成团时限、活动时间、限购规则 | 校验价格、库存、时间、人数和权限 | 创建待上线活动 |
| P0 | 编辑拼团活动 | 待上线/未开始活动点击编辑 | 活动基础信息和规则 | 已开始活动只允许编辑部分展示字段 | 保存变更并记录审计 |
| P0 | 启停活动 | 点击上线/下线 | 活动 ID、操作原因 | 校验状态流转、权限和未完成团单 | 更新活动状态 |
| P0 | 活动详情 | 点击详情 | 活动 ID | 汇总规则、SKU、团单、订单和操作日志 | 展示完整活动详情 |
| P0 | 团单处理 | 详情页操作 | 团单 ID、处理动作 | 支持手动成团、查看失败退款、查看参团订单 | 更新团单状态或展示处理结果 |
| P1 | 复制活动 | 列表点击复制 | 活动 ID | 复制基础规则，清空活动时间和库存占用 | 生成草稿活动 |
| P1 | 数据导出 | 点击导出 | 查询条件 | 异步导出并按权限过滤 | 下载导出文件 |

### 用户故事与业务流程
主流程：
1. 运营进入营销管理 / 拼团活动。
2. 系统按租户和数据范围加载活动列表。
3. 运营点击新增，选择商品 SKU 并配置拼团规则。
4. 系统校验价格低于原价、成团人数大于等于 2、活动时间合法、库存可用。
5. 运营保存为待上线活动。
6. 运营上线活动，系统记录审计日志。
7. 用户参团后，系统生成团单；达到人数自动成团，超时未达成则失败退款。
8. 运营在详情页查看团单、订单、退款和操作日志。

异常流程：
- 商品已下架：禁止上线，提示“商品不可售，请更换商品或下线活动”。
- 库存不足：禁止保存或上线，提示可售库存不足。
- 活动时间冲突：阻止保存，提示同 SKU 同时间已有互斥活动。
- 重复提交：提交中禁用按钮，接口幂等处理。
- 无权限：隐藏按钮或禁用并展示无权限提示。

### 数据对象与字段
| 对象 | 字段 | 类型 | 必填 | 默认值 | 校验/说明 |
| --- | --- | --- | --- | --- | --- |
| group_buy_activity | id | long | 是 | - | 活动 ID |
| group_buy_activity | activityName | string | 是 | - | 2-50 字 |
| group_buy_activity | activityStatus | enum | 是 | draft | draft/pending/online/offline/ended |
| group_buy_activity | startTime/endTime | datetime | 是 | - | startTime 小于 endTime |
| group_buy_activity | groupSize | int | 是 | 2 | 2-99 |
| group_buy_activity | groupExpireMinutes | int | 是 | 1440 | 成团时限 |
| group_buy_activity | limitPerUser | int | 否 | 1 | 单人限购 |
| group_buy_sku | skuId | long | 是 | - | 商品 SKU |
| group_buy_sku | groupPrice | decimal | 是 | - | 大于 0 且小于原价 |
| group_buy_sku | activityStock | int | 是 | - | 大于 0 |
| group_buy_team | teamStatus | enum | 是 | forming | forming/success/failed/refunding/refunded |
| group_buy_order | orderNo | string | 是 | - | 关联订单号 |

### 权限与数据范围
| 权限点 | permission key | 角色 | 展示策略 | 数据范围 | 审计 |
| --- | --- | --- | --- | --- | --- |
| 菜单访问 | marketing:groupBuy:view | 运营/客服/财务 | 无权限隐藏菜单 | 同租户 | 记录访问日志 |
| 新增活动 | marketing:groupBuy:create | 运营 | 无权限隐藏按钮 | 同租户 | 记录创建人 |
| 编辑活动 | marketing:groupBuy:update | 运营 | 不可编辑状态禁用 | 创建部门或授权部门 | 记录变更前后 |
| 上线/下线 | marketing:groupBuy:status | 运营主管 | 无权限隐藏 | 创建部门或授权部门 | 记录原因 |
| 手动成团 | marketing:groupBuy:team:manualSuccess | 运营主管 | 高风险二次确认 | 同租户 | 记录操作原因 |
| 导出 | marketing:groupBuy:export | 财务/运营主管 | 无权限隐藏 | 授权部门 | 记录导出条件 |

策略样例：
- RBAC：role=运营主管, resource=groupBuyActivity, action=publish。
- ABAC：condition=同租户且活动所属部门在用户授权部门内。
- 数据范围：tenantId 必须来自登录上下文，禁止前端传入覆盖。

### 验收标准
1. 场景：运营创建合法拼团活动。操作：填写商品 SKU、团购价、成团人数和活动时间后保存。预期：生成待上线活动，列表可查询，审计日志记录创建动作。
2. 场景：团购价高于原价。操作：填写 groupPrice >= salePrice。预期：前端阻止提交并提示“团购价必须低于原价”，后端返回校验错误。
3. 场景：无上线权限。操作：普通客服进入活动列表。预期：上线/下线按钮隐藏或禁用，直接调用 API 返回 403。
4. 场景：活动上线后编辑。操作：编辑已上线活动的商品 SKU。预期：商品 SKU 不可编辑，只允许编辑备注/展示文案等安全字段。
5. 场景：团单超时未成团。操作：构造超时团单。预期：状态变为 failed/refunding，退款状态可在详情页查看。
6. 场景：重复点击保存。操作：连续点击保存按钮。预期：只创建一条活动，按钮提交中禁用。

## 页面设计

### 页面清单及层级关系
| 页面名称 | 菜单层级 | 路由路径 | 组件路径 | 默认落点 | 面包屑 |
| --- | --- | --- | --- | --- | --- |
| 拼团活动列表页 | 营销管理二级菜单 | `/marketing/group-buy/list` | `src/views/marketing/groupBuy/GroupBuyList.vue` | 活动列表首屏 | 营销管理 / 拼团活动 |
| 拼团活动创建/编辑页 | 列表页进入 | `/marketing/group-buy/edit/:id?` | `src/views/marketing/groupBuy/GroupBuyEdit.vue` | 基础信息表单 | 营销管理 / 拼团活动 / 创建编辑 |
| 拼团活动详情页 | 列表页进入 | `/marketing/group-buy/detail/:id` | `src/views/marketing/groupBuy/GroupBuyDetail.vue` | 活动概览 | 营销管理 / 拼团活动 / 详情 |

### 页面布局
拼团活动列表页：
- 顶部筛选区：活动名称、商品 SKU、活动状态、活动时间、创建人。
- 操作区：新增、批量下线、导出。
- 表格区：活动名称、商品、团购价、成团人数、活动时间、状态、成团率、创建人、更新时间、操作。
- 行操作：详情、编辑、复制、上线、下线。

拼团活动创建/编辑页：
- 基础信息区：活动名称、活动时间、活动说明。
- 商品配置区：选择商品 SKU、原价、团购价、活动库存、限购数量。
- 成团规则区：成团人数、成团时限、失败处理、是否允许模拟成团。
- 提交区：保存草稿、保存并上线、取消返回。

拼团活动详情页：
- 概览区：活动状态、成团率、订单数、退款数、活动销售额。
- 规则区：活动基础信息和商品配置。
- 团单区：团单状态、参团用户、剩余时间、订单状态、退款状态。
- 日志区：操作人、操作时间、操作内容、操作原因。

### 字段定义
| 页面 | 字段 key | 展示名 | 类型 | 来源 | 校验/格式化 |
| --- | --- | --- | --- | --- | --- |
| 列表 | activityName | 活动名称 | string | group_buy_activity | 支持模糊查询 |
| 列表 | activityStatus | 活动状态 | enum | group_buy_activity | 字典 group_buy_status |
| 列表 | startTime/endTime | 活动时间 | datetime | group_buy_activity | 时间范围拆成 startTime/endTime |
| 编辑 | skuId | 商品 SKU | long | 商品选择弹窗 | 必填 |
| 编辑 | groupPrice | 团购价 | decimal | 表单输入 | 大于 0 且小于 salePrice |
| 编辑 | activityStock | 活动库存 | int | 表单输入 | 大于 0 且小于等于可售库存 |
| 编辑 | groupSize | 成团人数 | int | 表单输入 | 2-99 |
| 详情 | teamStatus | 团单状态 | enum | group_buy_team | 字典 group_team_status |

### 查询与筛选
- 默认筛选：最近 30 天活动，分页 pageNo=1/pageSize=20。
- 重置逻辑：清空活动名称、商品 SKU、状态、创建人，时间恢复最近 30 天。
- 时间范围提交前必须拆成 startTime/endTime，并移除原 range 字段。
- 导出按当前筛选条件和数据权限异步生成。

### 按钮和操作
| 操作 | 启用条件 | 二次确认 | 提交参数 | 成功反馈 | 失败反馈 |
| --- | --- | --- | --- | --- | --- |
| 新增 | 有 create 权限 | 否 | - | 进入创建页 | 无权限提示 |
| 编辑 | draft/pending 且有 update 权限 | 否 | id | 进入编辑页 | 状态不可编辑 |
| 上线 | pending/offline 且有 status 权限 | 是 | id、reason | 状态变为 online | 展示校验原因 |
| 下线 | online 且有 status 权限 | 是 | id、reason | 状态变为 offline | 展示未完成团单提示 |
| 手动成团 | forming 且有 manualSuccess 权限 | 是 | teamId、reason | 团单变为 success | 展示失败原因 |
| 导出 | 有 export 权限 | 否 | 当前查询条件 | 创建导出任务 | 展示导出失败原因 |

### 页面状态矩阵
每个页面必须覆盖：默认、加载中、空数据、搜索无结果、无权限、接口异常、提交中、提交失败、重复提交、脏数据离开确认。

### 权限控制点
- 路由：`marketing:groupBuy:view`
- 新增：`marketing:groupBuy:create`
- 编辑：`marketing:groupBuy:update`
- 上线/下线：`marketing:groupBuy:status`
- 手动成团：`marketing:groupBuy:team:manualSuccess`
- 导出：`marketing:groupBuy:export`
- API 权限必须与按钮权限一致，后端按 tenantId 和授权部门过滤数据。

### API 契约草案
| 场景 | 方法 | 接口 | 请求参数 | 响应字段 |
| --- | --- | --- | --- | --- |
| 活动分页 | GET | `/api/marketing/group-buy/page` | activityName、skuId、activityStatus、startTime、endTime、pageNo、pageSize | list、page、count |
| 活动详情 | GET | `/api/marketing/group-buy/detail` | id | activity、skuList、teamSummary、logs |
| 创建活动 | POST | `/api/marketing/group-buy/create` | activityName、startTime、endTime、skuList、groupSize、groupExpireMinutes | id |
| 更新活动 | POST | `/api/marketing/group-buy/update` | id、可编辑字段 | success |
| 状态变更 | POST | `/api/marketing/group-buy/status` | id、targetStatus、reason | success |
| 团单分页 | GET | `/api/marketing/group-buy/team/page` | activityId、teamStatus、pageNo、pageSize | list、page、count |
| 商品选择 | GET | `/api/product/sku/page` | keyword、pageNo、pageSize | list、page、count |

### 开发确认要点
- 商品选择弹窗是否复用现有 ProductSelectorModal。
- ApiResult 是否使用 `{ message: { code, message }, traceId, data }` 包装。
- 拼团失败退款由订单服务还是退款服务发起。
- 上线/下线是否需要审批流。

## 测试计划
1. 需求质量测试：确认 PRD 包含范围边界、P0/P1 功能、权限矩阵、数据对象、验收标准和待确认问题。
2. 页面设计质量测试：确认页面清单、路由、组件路径、字段、状态矩阵、权限 key、API 契约完整。
3. 原型覆盖测试：确认 prototype 至少生成列表、创建/编辑、详情三个主页面，且文件路径与页面设计一致。
4. API 契约测试：确认页面读取字段和交付包 API 字段一致，分页返回 list/page/count。
5. 权限测试：按钮显示、禁用、隐藏和后端 403 行为一致。
6. 边界测试：空数据、加载中、接口失败、重复提交、非法价格、库存不足、时间冲突、状态非法流转。
7. 交付测试：交付包必须包含 PRD、页面设计、API 契约、前端文件清单、审查结论、残余风险。

## 产品经理交付检查清单
- [x] 需求分析按步骤拆解完成。
- [x] P0/P1 功能、边界、权限、数据和验收标准完整。
- [x] 页面设计覆盖主页面、入口、路由、字段、交互、状态、权限和 API。
- [x] API 契约足够支撑前端预览和后端开发拆分。
- [x] 测试计划覆盖正常、异常、权限和边界路径。
- [x] 待确认问题已收口到真实产品经理可决策的事项。
