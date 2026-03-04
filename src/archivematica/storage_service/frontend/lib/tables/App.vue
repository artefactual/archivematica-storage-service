<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import {
  getCoreRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  type ColumnDef,
  type PaginationState,
  type SortingState,
  type Updater,
  useVueTable,
} from '@tanstack/vue-table'
import { useI18n } from 'vue-i18n'
import TableCellContent from './TableCellContent.vue'
import TablePagination from './TablePagination.vue'
import { useTableSearch } from './useTableSearch'
import type {
  LinkCell,
  LinkListCell,
  TablePayload,
  TableRow,
  TableAction,
  TableCell,
  TextWithLinksCell,
} from './types'

const props = defineProps<{
  payload: TablePayload
}>()

const { t, locale } = useI18n()

const PAGE_SIZE_OPTIONS = [10, 25, 50, 100] as const

const initialSorting = (): SortingState => {
  const firstSortableColumn = props.payload.columns.find(
    column => column.sortable ?? true,
  )
  if (!firstSortableColumn) {
    return []
  }
  return [{ id: firstSortableColumn.key, desc: false }]
}

const sorting = ref<SortingState>(initialSorting())
const pagination = ref<PaginationState>({
  pageIndex: 0,
  pageSize: 10,
})

const updateRef = <T>(updater: Updater<T>, target: { value: T }): void => {
  if (typeof updater === 'function') {
    target.value = (updater as (old: T) => T)(target.value)
    return
  }
  target.value = updater
}

const isLinkCell = (value: unknown): value is LinkCell => {
  if (!value || typeof value !== 'object') {
    return false
  }
  const maybeCell = value as Partial<LinkCell>
  return (
    maybeCell.kind === 'link'
    && typeof maybeCell.text === 'string'
    && typeof maybeCell.href === 'string'
  )
}

const isLinkListCell = (value: unknown): value is LinkListCell => {
  if (!value || typeof value !== 'object') {
    return false
  }
  const maybeCell = value as Partial<LinkListCell>
  return maybeCell.kind === 'link-list' && Array.isArray(maybeCell.items)
}

const isTextWithLinksCell = (value: unknown): value is TextWithLinksCell => {
  if (!value || typeof value !== 'object') {
    return false
  }
  const maybeCell = value as Partial<TextWithLinksCell>
  return (
    maybeCell.kind === 'text-with-links'
    && typeof maybeCell.text === 'string'
    && Array.isArray(maybeCell.items)
  )
}

const isTableAction = (value: unknown): value is TableAction => {
  if (!value || typeof value !== 'object') {
    return false
  }
  const maybeAction = value as Partial<TableAction>
  return typeof maybeAction.label === 'string' && typeof maybeAction.href === 'string'
}

const cellText = (value: unknown): string => {
  if (value === null || value === undefined) {
    return ''
  }
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
    return String(value)
  }
  if (Array.isArray(value)) {
    return value
      .filter(isTableAction)
      .map(action => action.label)
      .join(' ')
  }
  if (isLinkCell(value)) {
    return value.text
  }
  if (isLinkListCell(value)) {
    return value.items.map(item => item.text).join(' ')
  }
  if (isTextWithLinksCell(value)) {
    const suffix = value.items.map(item => item.text).join(' ')
    return `${value.text} ${suffix}`.trim()
  }
  return ''
}

const displayValueForColumn = (row: TableRow, key: string): string => cellText(row[key])

const {
  searchFilterInput,
  globalFilter,
  tokenizedGlobalFilter,
} = useTableSearch({
  rows: computed(() => props.payload.rows),
  columns: computed(() => props.payload.columns),
  displayValueForColumn,
})

const filteredRows = computed(() => {
  if (globalFilter.value.trim() === '') {
    return props.payload.rows
  }
  return props.payload.rows.filter(row => tokenizedGlobalFilter(row, globalFilter.value))
})

watch(globalFilter, () => {
  pagination.value.pageIndex = 0
})

const columnLabelByKey = computed(() => {
  const map = new Map<string, string>()
  props.payload.columns.forEach((column) => {
    map.set(column.key, column.label)
  })
  return map
})

const columns = computed<ColumnDef<TableRow>[]>(() => {
  return props.payload.columns.map(column => ({
    id: column.key,
    accessorFn: row => row[column.key] as TableCell | TableAction[],
    enableSorting: column.sortable ?? true,
    sortingFn: (rowA, rowB, columnId) => {
      const a = cellText(rowA.getValue(columnId)).toLocaleLowerCase()
      const b = cellText(rowB.getValue(columnId)).toLocaleLowerCase()
      return a.localeCompare(b, undefined, {
        numeric: true,
        sensitivity: 'base',
      })
    },
  }))
})

const table = useVueTable({
  get data() {
    return filteredRows.value
  },
  get columns() {
    return columns.value
  },
  state: {
    get sorting() {
      return sorting.value
    },
    get pagination() {
      return pagination.value
    },
  },
  onSortingChange: (updater) => {
    updateRef(updater, sorting)
    pagination.value.pageIndex = 0
  },
  onPaginationChange: updater => updateRef(updater, pagination),
  getCoreRowModel: getCoreRowModel(),
  getSortedRowModel: getSortedRowModel(),
  getPaginationRowModel: getPaginationRowModel(),
})

const rows = computed(() => table.getRowModel().rows)
const pageSizeOptions = [...PAGE_SIZE_OPTIONS]
const sortedColumnId = computed(() => sorting.value[0]?.id ?? null)
const totalRowsCount = computed(() => props.payload.rows.length)
const filteredRowsCount = computed(() => filteredRows.value.length)

const pageStart = computed(() => {
  if (rows.value.length === 0) {
    return 0
  }
  return pagination.value.pageIndex * pagination.value.pageSize + 1
})

const pageEnd = computed(() => {
  if (rows.value.length === 0) {
    return 0
  }
  return pagination.value.pageIndex * pagination.value.pageSize + rows.value.length
})

const numberFormatter = computed(() => new Intl.NumberFormat(locale.value))
const formatNumber = (value: number): string => numberFormatter.value.format(value)

const infoText = computed(() => {
  if (filteredRowsCount.value < totalRowsCount.value) {
    return t('tables.infoFiltered', {
      start: formatNumber(pageStart.value),
      end: formatNumber(pageEnd.value),
      filtered: formatNumber(filteredRowsCount.value),
      total: formatNumber(totalRowsCount.value),
    })
  }

  if (filteredRowsCount.value === 0) {
    return t('tables.infoEmpty')
  }

  return t('tables.info', {
    start: formatNumber(pageStart.value),
    end: formatNumber(pageEnd.value),
    total: formatNumber(filteredRowsCount.value),
  })
})

const sortIndicatorClass = (state: false | 'asc' | 'desc'): string => {
  if (state === 'asc') {
    return 'ss-table-sort-icon--asc'
  }
  if (state === 'desc') {
    return 'ss-table-sort-icon--desc'
  }
  return 'ss-table-sort-icon--unsorted'
}

const updatePageIndex = (nextPageIndex: number): void => {
  table.setPageIndex(nextPageIndex)
}

const updatePageSize = (nextPageSize: number): void => {
  table.setPageSize(nextPageSize)
  table.setPageIndex(0)
}

const onPageSizeChange = (event: Event): void => {
  const target = event.target
  if (!(target instanceof HTMLSelectElement)) {
    return
  }

  const next = Number.parseInt(target.value, 10)
  if (Number.isNaN(next)) {
    return
  }
  updatePageSize(next)
}
</script>

<template>
  <div class="ss-table">
    <div class="ss-table-controls">
      <div class="ss-table-length">
        <label class="ss-table-length__label">
          <span>{{ t('tables.show') }}</span>
          <select
            class="ss-table-length__select"
            :value="pagination.pageSize"
            @change="onPageSizeChange"
          >
            <option
              v-for="size in pageSizeOptions"
              :key="size"
              :value="size"
            >
              {{ size }}
            </option>
          </select>
          <span>{{ t('tables.entries') }}</span>
        </label>
      </div>

      <div class="ss-table-toolbar">
        <label class="ss-table-toolbar__label">
          <span>{{ t('tables.search') }}</span>
          <input
            v-model="searchFilterInput"
            class="ss-table-search-input"
            type="search"
          >
        </label>
      </div>
    </div>

    <table class="ss-table-grid">
      <thead>
        <tr>
          <th
            v-for="column in table.getAllLeafColumns()"
            :key="column.id"
          >
            <button
              v-if="column.getCanSort()"
              class="ss-table-sort-button"
              type="button"
              @click="column.toggleSorting(column.getIsSorted() === 'asc')"
            >
              {{ columnLabelByKey.get(column.id) || column.id }}
              <span
                class="ss-table-sort-indicator"
                aria-hidden="true"
              >
                <i :class="sortIndicatorClass(column.getIsSorted())" />
              </span>
            </button>
            <span
              v-else
              class="ss-table-header-label"
            >
              {{ columnLabelByKey.get(column.id) || column.id }}
            </span>
          </th>
        </tr>
      </thead>

      <tbody v-if="rows.length > 0">
        <tr
          v-for="(row, rowNumber) in rows"
          :key="row.id"
          :class="rowNumber % 2 === 0 ? 'ss-table-row--odd' : 'ss-table-row--even'"
        >
          <td
            v-for="cell in row.getVisibleCells()"
            :key="cell.id"
            :class="{ 'ss-table-cell--sorted': sortedColumnId === cell.column.id }"
          >
            <TableCellContent
              :column-id="cell.column.id"
              :value="cell.getValue()"
            />
          </td>
        </tr>
      </tbody>

      <tbody v-else>
        <tr class="ss-table-row--odd">
          <td
            class="ss-table-cell--empty"
            :colspan="table.getAllLeafColumns().length"
          >
            {{ t('tables.noRecords') }}
          </td>
        </tr>
      </tbody>
    </table>

    <div class="ss-table-info">
      {{ infoText }}
    </div>

    <div class="ss-table-pagination">
      <TablePagination
        :page-index="pagination.pageIndex"
        :can-previous="table.getCanPreviousPage()"
        :can-next="table.getCanNextPage()"
        @update:page-index="updatePageIndex"
      />
    </div>
  </div>
</template>

<style scoped>
.ss-table {
  position: relative;
  clear: both;
  width: 100%;
}

.ss-table-controls {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 6px;
}

.ss-table-length__label {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  margin: 0;
}

.ss-table-length__select {
  width: 220px;
  height: 30px;
  padding: 4px;
  margin: 0;
  font: inherit;
  border: 1px solid #ccc;
  border-radius: 4px;
  background: #fff;
}

.ss-table-toolbar {
  margin-bottom: 12px;
  margin-left: auto;
}

.ss-table-toolbar__label {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  margin: 0;
}

.ss-table-search-input {
  width: 206px;
  padding: 4px 6px;
  margin: 0;
  font: inherit;
  border: 1px solid #ccc;
  border-radius: 4px;
}

.ss-table-grid {
  margin: 0 auto;
  clear: both;
  width: 100%;
  border-collapse: collapse;
}

.ss-table-grid td {
  padding: 3px 10px;
  text-align: left;
  vertical-align: middle;
  border: 0;
}

.ss-table-grid td.ss-table-cell--empty {
  text-align: center;
}

.ss-table-grid thead th {
  padding: 3px 18px 3px 10px;
  border-bottom: 1px solid #000;
  font-weight: 700;
  white-space: nowrap;
  text-align: center;
  vertical-align: middle;
}

.ss-table-row--odd {
  background: #e2e4ff;
}

.ss-table-row--even {
  background: #fff;
}

.ss-table-row--odd .ss-table-cell--sorted {
  background: #d3d6ff;
}

.ss-table-row--even .ss-table-cell--sorted {
  background: #eaebff;
}

.ss-table-sort-button {
  position: relative;
  background: transparent;
  border: 0;
  color: inherit;
  cursor: pointer;
  font: inherit;
  padding: 0 14px 0 0;
  width: 100%;
  display: block;
  text-align: center;
}

.ss-table-sort-indicator {
  position: absolute;
  top: 50%;
  right: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 12px;
  height: 12px;
  margin: 0;
  transform: translateY(-50%);
}

.ss-table-header-label {
  display: block;
  text-align: center;
}

.ss-table-sort-indicator i {
  line-height: 0;
  font-style: normal;
}

.ss-table-sort-icon--asc,
.ss-table-sort-icon--desc {
  display: inline-block;
  width: 0;
  height: 0;
  border-left: 4px solid transparent;
  border-right: 4px solid transparent;
}

.ss-table-sort-icon--asc {
  border-bottom: 6px solid currentColor;
}

.ss-table-sort-icon--desc {
  border-top: 6px solid currentColor;
}

.ss-table-sort-icon--unsorted {
  display: inline-flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  width: 8px;
  line-height: 0;
}

.ss-table-sort-icon--unsorted::before,
.ss-table-sort-icon--unsorted::after {
  content: '';
  display: block;
  width: 0;
  height: 0;
  border-left: 4px solid transparent;
  border-right: 4px solid transparent;
}

.ss-table-sort-icon--unsorted::before {
  border-bottom: 5px solid #dcdcdc;
}

.ss-table-sort-icon--unsorted::after {
  border-top: 5px solid #dcdcdc;
}

.ss-table-sort-icon--asc {
  border-bottom-color: #7a80dd;
}

.ss-table-sort-icon--desc {
  border-top-color: #7a80dd;
}

.ss-table-info {
  clear: both;
  float: left;
  margin-top: 8px;
}

.ss-table-pagination {
  float: right;
  margin-top: 8px;
}

.ss-table::after {
  content: '';
  display: table;
  clear: both;
}
</style>
