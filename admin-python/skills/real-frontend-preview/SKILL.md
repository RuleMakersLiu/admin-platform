---
id: real_frontend_preview
name: real-frontend-preview
description: "Generate previewable real frontend project code for product pipeline prototype stages. Enforces existing-page vs new-page mock boundaries, previewability, incremental edits, and JSON file-array output."
version: 1.0.0
category: development
agent_type: FE
metadata:
  hermes:
    tags: [frontend, preview, prototype, mock-boundary, existing-page, product-pipeline]
    related_skills: [frontend-development, code-review]
---

# Real Frontend Preview

Use this skill when the product pipeline `prototype` stage must generate code that is written into a matched frontend project sandbox and launched by that project's own npm scripts.

## Non-Negotiable Goal

The output must be real frontend project files, not static HTML, not a standalone demo, and not a new scaffold. The generated code must render the requested page in the matched project preview without a first-screen runtime error.

## Decision Order

1. Decide whether the request is a new page or an existing-page change.
2. If the request contains a page location suggestion, new menu entry, route/default-landing proposal, page function list, interface plan for a new management/configuration page, or wording such as "新增页面/新建页面/新增...管理/新增...配置", classify it as a new page unless the user explicitly says it is changing an existing page.
3. Existing page selection is allowed only when the request explicitly names an existing/current/original page or asks to add/modify a field, filter, button, column, or query condition on an existing feature.
4. If it is an existing-page change, identify the confirmed existing frontend page path from project skill or code reference. If no confirmed path exists, output `[]` so the pipeline fails clearly.
5. Preserve the matched project's framework, routing, components, API wrapper, permission style, table/list mixins, and naming conventions.
6. Generate the smallest complete page set needed for the requested preview.

## Isolation Contract

- Treat every pipeline requirement as a fresh run. Do not reuse another requirement's generated page names, fields, API paths, mock data, routes, or business terminology.
- Persistent context may only come from universal prompt rules, project skills, confirmed existing project code, and generalized memory notes.
- A previous failure may inform a general rule, but the rule must be domain-neutral and reusable. Do not encode requirement-specific mappings or examples into shared validators or prompts.
- If a page-design document declares component paths or API paths, validate against those declared facts. Do not infer business-specific translations from labels.

## Page Count Contract

- If page design lists multiple primary pages, generate one real frontend page file for every primary page.
- Do not collapse a multi-page design into a single list page.
- Shared route/API/mock/service modules may be reused, but page components must cover the page list.
- Dialogs, drawers, modals, and subcomponents count as support files, not replacements for primary pages.
- On repair, keep the same page set. Do not drop pages to make review easier.

## Existing-Page Changes

Existing-page changes include wording such as existing/current/original page, add a filter, add a field, modify a button, adjust a list, optimize a page, or supplement a query condition.

Rules:

- Do not treat broad words like "current backend implementation", "current API style", "support query", "new/edit", "status enable/disable", or "page initialization" as proof that an existing frontend page must be selected.
- Modify the confirmed existing page file. Do not create `List.vue`, `index.tsx`, `GeneratedPage`, `PreviewOnly`, `SandboxPreview`, or another semantic replacement page.
- Keep old fields, labels, columns, filters, buttons, imports, mixins, table data flow, pagination, permissions, and API calls unless the user explicitly asks to remove or rename them.
- Only new or changed fields may use mock examples. Existing data must continue to come from the existing page data flow and API wrapper.
- Do not replace a real list loader with local `data()`, `Promise.resolve`, `Mock.mock`, `mockRequestWrapper`, or a new fake API.
- For Vue list pages using `ListMixin` or `STable`, preserve `mixins`, `url.list`, `<s-table :data="loadData">`, existing `columns`, scoped slots, row actions, and imported helpers.
- If the request says add a filter, add a new bound request field. Do not rename or repurpose an old filter. Example: keep `queryParam.productCode` for 商品编号 and add `queryParam.id` for 商品ID.
- API/service edits for old pages must be additive only: pass through new request params, add new response field formatting if needed, and keep old function names and response handling.

## New Pages

New pages include requests that create a page or feature with no confirmed existing page path.

Rules:

- Page location suggestions, menu placement, route/default-landing proposals, and page function sections are strong new-page signals. They define where the new page should live; they are not a request to choose an unrelated existing list page.
- For a new configuration or management page, do not reuse an order/list/product page merely because it has similar table/search/edit/status UI patterns. Use existing pages only as style examples, not as target files.
- Generate a real page component at a project-appropriate path plus the minimum API/service or route files required by the project.
- For ordinary admin/configuration CRUD pages, default to a list page plus create/edit modal, drawer, or shared form component. Do not generate separate create and edit primary route pages unless the page design explicitly requires independent routes and breadcrumbs for those pages.
- New pages must include mock data so the preview works before backend implementation.
- New pages that call real `request(...)` APIs must include a mock/fallback path that returns preview data when the real API is unavailable.
- Mock data must live in an isolated service/helper for the new page and must not shadow or duplicate an existing real request function name.
- Mock fields must match the page fields and the API contract candidate fields exactly.
- List mocks must return a pagination object that includes `list`, `page`, `pageNo`, `pageSize`, `count`, and `totalCount`.
- Detail/edit/config mocks must return objects and the page must default missing objects to `{}` and missing arrays to `[]`.
- A combined "新增/编辑" action can be satisfied by one modal/drawer/form component with both create and edit handlers. Do not count the words "新增/编辑" as two missing primary pages by themselves.
- Required visible actions are user commands, not container names. A drawer or modal label such as "新建/编辑抽屉" should be implemented as a form container opened by visible commands like "新建批次" and row-level "编辑"; the UI does not need a literal button named "新建/编辑抽屉".

## Uni-App And Miniapp Projects

- Do not treat uni-app or miniapp repositories as ordinary web admin projects.
- For uni-app monorepos, generate files under the matched app's real structure, for example `apps/<app>/pages/**/index.vue` and `apps/<app>/api/*.ts`, unless the project skill explicitly gives a different convention.
- Generate source pages for the real app, not only a browser-only HTML page. Native miniapp projects may additionally need `public/sandbox-miniapp-preview.html` for browser validation, but that file does not replace the source page files.
- Preserve the project's confirmed API wrapper. Do not invent named imports such as `import { http } from '@hc-agent/http'` unless the project skill or code reference proves that export exists.
- If the real API wrapper is not confirmed and the page is new, keep preview data isolated in a page-specific mock/helper whose fields match the API contract. Do not shadow an existing real request function name.

## Permission Helpers

- Use `hasPermission`, `v-action`, permission directives, or global permission helpers only when the matched project skill or code reference confirms they exist.
- If permission behavior is required but the helper is not confirmed, define a small local helper in the generated page so the preview remains runnable, and keep the permission keys visible in the code.
- Never render a template expression that references an undefined permission helper.

## Previewability

- Every template event handler and rendered slot must have an implementation.
- Buttons must perform visible UI behavior: open modal/drawer, update local state, reset filters, submit with loading, show success/error, or navigate using existing router patterns.
- Guard all possible undefined values before using `.length`, `.map`, `.filter`, nested fields, or table data.
- Include loading, empty, search-empty, no-permission, submit-failed, and interface-failed states where the page type needs them.
- Do not import unconfirmed components, directives, global variables, plugins, or styles.
- Do not generate `package.json`, `vite.config.*`, `main.*`, `App.*`, or `index.html` for web projects.

## Output

Return only a valid JSON array of file objects:

```json
[
  {"path": "src/views/module/ExistingPage.vue", "content": "complete file content"}
]
```

No Markdown, no code fences, no explanation text. If the required existing page cannot be identified, return `[]`.
