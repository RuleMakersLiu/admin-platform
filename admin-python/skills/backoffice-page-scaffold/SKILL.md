---
id: backoffice_page_scaffold
name: backoffice-page-scaffold
description: "Constrain admin/backoffice frontend prototype generation to stable list, detail, modal, selector, and create/edit page scaffolds while filling only requirement-specific fields, APIs, and labels."
version: 1.0.0
category: development
agent_type: FE
metadata:
  hermes:
    tags: [frontend, admin, backoffice, scaffold, prototype, page-design]
    related_skills: [real-frontend-preview, frontend-development, code-review]
---

# Backoffice Page Scaffold

Use this skill whenever a product pipeline prototype stage generates an admin or backoffice management UI. The page skeleton is fixed; only fields, labels, APIs, permissions, and domain data change per requirement.

## Scaffold Decision

Start from the page-design document and classify every declared page or component into one of these archetypes:

- List page
- Detail page
- Create/edit modal or drawer
- Create/edit full page
- Selector modal
- Supporting API, mock, route, or shared component module

Generate every primary page declared by the page design. Dialogs, drawers, and selector components support pages; they do not replace primary pages.

## New Page Versus Existing Page

- A requirement with "页面位置建议", "页面功能", menu placement, route/default landing, interface planning, or a new management/configuration capability is a new page request unless it explicitly says it is modifying an existing page.
- Existing pages may be inspected as style and component references, but they are not target files for a new page.
- Do not select an order list, product list, activity list, or any other unrelated existing list page just because the new page also has search, table, create/edit, status, or export behavior.
- Only classify a request as an existing-page change when it explicitly mentions an existing/current/original page or asks to add/modify a field, filter, column, button, or behavior on a known existing feature.
- For ordinary admin/configuration CRUD pages, model "新增/编辑" as a modal, drawer, or shared form component attached to the list page by default. Do not promote create and edit into separate primary route pages unless the requirement explicitly asks for independent create/edit routes, breadcrumbs, or multi-step forms.

## List Page Contract

A list page must include:

- Search form fields declared by the page design, with reset behavior.
- Toolbar actions declared as buttons or operations.
- Table columns declared by the page design.
- Row actions declared by the page design.
- A data loader wired to the matched project's table component pattern.
- Pagination that maps table parameters to request parameters and returns a normalized page object.
- Loading, empty, request-failed, and safe default states.

For STable-style loaders, accept `parameter`, merge it with search state, pass page number and size to the API, and return an object containing at least `list`, `page`, `pageNo`, `pageSize`, `count`, and `totalCount`.

If mock or fallback pagination is used, it must slice or generate records by `pageNo` and `pageSize`; page 1 and page 2 must not return the same unchanged record set.

## Detail Page Contract

A detail page must include:

- Route or prop based identity loading when the page design requires it.
- Read-only sections for declared fields.
- Back/close behavior that matches the project routing or modal pattern.
- Loading, not-found, and request-failed states.
- Safe object and array defaults before rendering nested fields.

## Create/Edit Contract

A create/edit modal, drawer, or full page must include:

- Reactive visible/open state when rendered as a modal or drawer.
- Form model, validation rules, reset logic, submit loading, cancel behavior, and success/error feedback.
- Open methods for create and edit modes.
- API or fallback save behavior compatible with the page-design API contract.
- Event emission or route return behavior that refreshes the parent list.

Every template reference, visible binding, handler, computed value, and prop used by the create/edit UI must be declared in `data`, `props`, `computed`, or `methods`.

When page design writes "新增/编辑" as a combined operation, a single create/edit modal/drawer or shared form component covers both actions. It should not force two separate primary pages named create and edit.

## Selector Modal Contract

A selector modal must include:

- Search fields, reset behavior, table loader, pagination, and selectable rows.
- Confirm and cancel behavior.
- A stable selected-row state and emitted result.
- Safe default arrays before using array methods.

## API And File Contracts

- Use the page-design declared frontend paths when provided. Normalize aliases such as `@/views/...` to project file paths such as `src/views/...`.
- Keep page file names stable across retries. Do not invent a new semantic name for the same declared page after a repair.
- Cover every API endpoint declared by the page design in the API/service module or an explicitly referenced fallback module.
- Match the project skill response envelope and request wrapper conventions.
- New pages may include preview-safe fallback data, but existing pages must preserve their real data flow and only add requested fields.

## Button And Action Contract

- Treat only page-design buttons, toolbar actions, row operations, and form actions as required visible actions.
- Do not treat page names, section titles, sorting text, API names, drawer names, modal names, component names, or popup descriptions as standalone buttons.
- Action labels must be user-visible commands such as "新建批次", "编辑", "启用", "停用", "复制", or "导出". Do not require visible controls named "新建/编辑抽屉", "创建/编辑页", "编辑弹窗", or similar container/component labels.
- Every required action must have a visible control and a defined handler.
- If a declared create/edit action exists, generate the corresponding modal, drawer, or page integration rather than a placeholder button.

## Self Review Before Returning

Before returning prototype files, compare the generated files against the page design:

1. Every primary page has a corresponding file.
2. Every declared page path is generated or intentionally normalized to a project path.
3. Every declared button/action is visible and wired.
4. Every table loader handles pagination fields and list data.
5. Every API declared by the page design is covered.
6. No template reference points to an undefined reactive field or handler.
7. Mock or fallback list data changes by page number.

Return files only after the scaffold review passes.
