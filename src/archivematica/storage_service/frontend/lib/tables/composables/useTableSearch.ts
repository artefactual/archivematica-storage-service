import { computed, ref, watch, type Ref } from 'vue'
import { refDebounced } from '@vueuse/core'
import type { TableColumn, TableRow } from '../types'

export const SEARCH_DEBOUNCE_MS = 100

type UseTableSearchOptions = {
  rows: Ref<TableRow[]>
  columns: Ref<TableColumn[]>
  displayValueForColumn: (row: TableRow, key: string) => string
}

export const useTableSearch = ({
  rows,
  columns,
  displayValueForColumn,
}: UseTableSearchOptions) => {
  const searchFilterInput = ref('')
  const globalFilter = ref('')
  const debouncedSearchFilterInput = refDebounced(
    searchFilterInput,
    SEARCH_DEBOUNCE_MS,
  )

  const searchableColumnKeys = computed(() =>
    columns.value
      .filter(column => column.key !== 'actions')
      .map(column => column.key),
  )

  const searchableTextByRow = computed(() => {
    const searchableKeys = searchableColumnKeys.value
    const index = new Map<TableRow, string>()
    for (const row of rows.value) {
      const searchableText = searchableKeys
        .map(key => displayValueForColumn(row, key).toLowerCase())
        .join(' ')
      index.set(row, searchableText)
    }
    return index
  })

  let lastFilterValue = ''
  let lastFilterTokens: string[] = []
  const tokensForFilterValue = (filterValue: string): string[] => {
    if (filterValue === lastFilterValue) {
      return lastFilterTokens
    }

    lastFilterValue = filterValue
    lastFilterTokens = filterValue
      .toLowerCase()
      .trim()
      .split(/\s+/)
      .filter(Boolean)
    return lastFilterTokens
  }

  const tokenizedGlobalFilter = (row: TableRow, filterValue: string): boolean => {
    const tokens = tokensForFilterValue(filterValue)
    if (tokens.length === 0) {
      return true
    }

    const searchableText = searchableTextByRow.value.get(row) ?? ''
    return tokens.every(token => searchableText.includes(token))
  }

  watch(debouncedSearchFilterInput, (value) => {
    globalFilter.value = value
  })

  return {
    searchFilterInput,
    globalFilter,
    tokenizedGlobalFilter,
  }
}
