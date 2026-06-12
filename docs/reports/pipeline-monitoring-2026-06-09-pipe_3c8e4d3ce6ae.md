# Pipeline Monitoring Notes: pipe_3c8e4d3ce6ae

## Context

- Date: 2026-06-09
- Pipeline ID: `pipe_3c8e4d3ce6ae`
- Requirement: `我想在商品管理平台做拼团和秒杀活动`
- Current observed state at last check: `running / prototype / retry_count=0`
- Completed stages at last check: `requirement`, `page_design`

## Issues Found

### P0: API response format is not constrained to the target project convention

- User-reported issue: 接口响应格式没有约束好，示例没符合项目要求。
- Evidence from `page_design`: response examples include flat shapes such as:
  - `{ "code": 200, "msg": "success", "data": true }`
  - references to `ApiResult<PageResult<ActivityVO>>` without enforcing the actual JSON envelope.
- Expected project convention from `wealth-admin-home` skill snapshot:
  - Top-level response should be `{"message":{"message":"ok","code":0},"traceId":"","data":...}`.
  - Success code defaults to `0`, not HTTP-style `200` in the business envelope.
  - `message` is an object, not a string field or `msg`.
- Risk:
  - Later frontend contract review may fail due to response-shape mismatch.
  - Generated frontend may parse `code/msg/data` incorrectly and diverge from existing project request handling.
  - Backend API contract examples may mislead implementation and tests.
- Optimization:
  - Add a hard API-contract rule to prompts/checks: all `wealth-admin-home` examples must use the nested `message` envelope.
  - Reject or auto-fix any generated API example using flat `{code,message,msg,data}` shapes.
  - In code review, treat response-envelope mismatch as a blocking issue, not a style nit.

#### Follow-up evidence from prototype

- `prototype` generated `src/api/activityManage.js`.
- `updateActivityStatus` mock still returns a flat response shape:
  - `{ code: 200, message: '操作成功' }`
- This confirms the response-format constraint did not carry from project skill into prototype generation.
- Recommendation: do not approve this prototype as-is unless the next review/fix pass rewrites mock and contract examples to the project envelope.

### P1: Page-design scope is broad for a first pass

- Evidence: `page_design` proposes list, edit/create, detail, product selection modal, publish/cancel flows, permissions, audit points, and multiple API drafts.
- Risk:
  - Prototype generation may be too large and more likely to omit files, fields, validation, or route wiring.
  - Contract review may surface many unrelated issues at once.
- Optimization:
  - If the goal is a smaller v1, constrain the first iteration to activity list plus create/edit core fields.
  - Defer detail page, high-risk cancel audit UX, and advanced product modal filters unless explicitly needed now.

### P0: Frontend prototype does not converge to the page design after repeated feedback

- User-reported issue: 前端代码始终无法达到页面设计的效果，反馈了 3 轮也不行。
- Evidence:
  - `page_design` describes a multi-page activity-management experience with list, create/edit, detail, product-selection modal, status actions, permissions, validation, and API contracts.
  - Initial `prototype` output only produced:
    - `src/api/activityManage.js`
    - `src/views/activityManage/ActivityManageList.vue`
  - The generated scope is visibly narrower than the page design, and repeated feedback did not close the gap.
- Risk:
  - The repair loop may be optimizing local code snippets instead of validating against the full `page_design` acceptance surface.
  - Users may spend multiple feedback rounds without meaningful convergence.
  - The pipeline can appear to progress while the deliverable remains unusable for design review.
- Optimization:
  - Add an explicit page-design coverage checklist before accepting `prototype`: required pages, files, routes, dialogs, fields, actions, permissions, validation rules, and API calls.
  - In `prototype` review, fail fast if required page-design elements are missing instead of waiting for manual feedback.
  - Split overly broad page designs into deterministic v1 scope before generation, or require the prototype to generate all declared files.
  - Include a diff-style summary after each repair pass: which user feedback items were fixed, which remain missing, and why.

### P1: API paths and permission keys may be invented instead of grounded

- Evidence: `page_design` proposes paths like `/api/activity/list`, `/api/activity/save`, `/api/activity/updateStatus`, and permissions like `activity:add`, `activity:publish`.
- Risk:
  - Generated frontend may not align with existing backend route naming or permission tree conventions.
  - Review may fail if the API contract cannot map to existing BFF/service patterns.
- Optimization:
  - Require the next stage to mark invented endpoints as draft-only.
  - Prefer existing route/service naming conventions from the matched projects when available.
  - Make permission keys explicit TODOs unless the project already has corresponding menu/button permission records.

### P1: Preview page can become abnormally stuck, possibly due to sandbox runtime

- User-reported issue: 不知道什么页面异常的卡，需要注意；不确定是否由沙箱导致。
- Risk:
  - A stuck preview page can be misdiagnosed as generated frontend code failure.
  - Sandbox-preview runtime issues may come from dev-server startup, proxy routing, preview token/cookie, API proxy, asset loading, browser console errors, or long-running JS loops.
  - If the pipeline only records "preview unusable" without environment evidence, later repair may target the wrong layer.
- Optimization:
  - When preview appears stuck, capture evidence from both layers:
    - Pipeline state: `status`, `current_stage`, `retry_count`, `prototype.code_files`, stage errors.
    - Sandbox layer: preview start result, dev-server port, proxy status, preview token validity, browser console/network errors.
  - Validate through the real browser path: `/api/flow/pipeline/{pipeline_id}/sandbox-preview/`, not only internal container URLs.
  - Classify the failure before feedback:
    - generated-code runtime error,
    - sandbox/dev-server failure,
    - gateway/proxy/token failure,
    - backend mock/API shape failure,
    - browser performance or infinite-loop issue.
  - Add a short "preview health" checkpoint before asking the user for another manual feedback round.

## Monitoring Notes

- Pipeline creation and matching succeeded.
- `requirement` took about two minutes from LLM response to persisted output, but completed successfully.
- `page_design` also completed and advanced after confirmation.
- No hard failure has been observed yet.

## Notify Conditions

- Notify immediately if the pipeline enters `failed`.
- Notify if `current_stage` remains unchanged with no `update_time` movement for several minutes.
- Notify if `retry_count` increases or the flow loops between `prototype`, `delivery`, and `code_review`.
- Notify if generated API examples still use the wrong flat response format after prototype/code review.
