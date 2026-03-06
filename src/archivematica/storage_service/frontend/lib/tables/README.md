# Tables (Vue)

`tables` is the Vue/TanStack replacement for Storage Service DataTables
views.

This app supports two modes:

- client mode for pages where Django already renders full datasets in HTML
- server compatibility mode for endpoints that still use legacy DataTables
  server-side contracts

## What It Does

- Vue 3 + TanStack Table
- App-scoped table/pager/action markup
- client-side sorting, filtering, and pagination
- shared renderer for multiple table pages (`kind`-based)

## Scope

Current `kind` values:

- `keys-list`
- `users-list`
- `pipelines-list`
- `locations-list`
- `callbacks-list`
- `package-requests-pending`
- `package-requests-closed`
- `packages-server`
- `fixity-logs-server`

## How It Loads

1. Django template renders:
   - a mount node (`data-table-root`)
   - a `json_script` payload
2. `base.html` loads `frontend/tables.js`
3. `index.ts` initializes Vue i18n and mounts `App.vue` for each table root

## Files

- `index.ts`: bootstrap + mount logic
- `App.vue`: shared table renderer
- `TableCellContent.vue`: cell/action rendering for payload cell types
- `TableDecisionFormCell.vue`: per-row package request approval/rejection form cell
- `TablePagination.vue`: pager + page-size selector
- `composables/useTableSearch.ts`: debounced tokenized search composable
- `types.ts`: payload type definitions

## Payload Shape (High Level)

Expected fields:

- `version`
- `kind`
- `columns`
- `rows`
- `ui`

Notes:

- `rows` should contain JSON values only (no pre-rendered HTML)
- represent links/actions with metadata objects (`kind: "link"`, action arrays)
- use column metadata for labels/sortability
