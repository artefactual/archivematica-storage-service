import { computed, nextTick, ref } from 'vue'
import { describe, expect, it, vi } from 'vitest'
import type { TableColumn, TableRow } from '../types'
import { SEARCH_DEBOUNCE_MS, useTableSearch } from './useTableSearch'

const columns = ref<TableColumn[]>([
  { key: 'description', label: 'Description' },
  { key: 'status', label: 'Status' },
  { key: 'actions', label: 'Actions', sortable: false },
])

const makeRows = () =>
  ref<TableRow[]>([
    {
      description: 'Default AIP recovery',
      status: 'enabled',
      actions: [{ label: 'Edit', href: '/locations/1/edit/', style: 'default' }],
    },
    {
      description: 'Pipeline temporary location',
      status: 'disabled',
      actions: [{ label: 'Delete', href: '/locations/2/delete/', style: 'default' }],
    },
  ])

const displayValueForColumn = (row: TableRow, key: string): string => {
  const value = row[key]
  if (value === null || value === undefined) {
    return ''
  }
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
    return String(value)
  }
  return ''
}

describe('useTableSearch', () => {
  it('applies a debounced global filter value', async () => {
    vi.useFakeTimers()
    try {
      const search = useTableSearch({
        rows: makeRows(),
        columns: computed(() => columns.value),
        displayValueForColumn,
      })

      search.searchFilterInput.value = 'default recovery'
      await nextTick()
      expect(search.globalFilter.value).toBe('')

      vi.advanceTimersByTime(SEARCH_DEBOUNCE_MS)
      await nextTick()
      expect(search.globalFilter.value).toBe('default recovery')
    } finally {
      vi.useRealTimers()
    }
  })

  it('filters using tokenized AND matching and ignores actions labels', () => {
    const rows = makeRows()
    const search = useTableSearch({
      rows,
      columns: computed(() => columns.value),
      displayValueForColumn,
    })

    const firstRow = rows.value[0]
    const secondRow = rows.value[1]
    expect(firstRow).toBeDefined()
    expect(secondRow).toBeDefined()

    expect(search.tokenizedGlobalFilter(firstRow!, 'default recovery')).toBe(true)
    expect(search.tokenizedGlobalFilter(secondRow!, 'default recovery')).toBe(false)
    expect(search.tokenizedGlobalFilter(firstRow!, 'edit')).toBe(false)
    expect(search.tokenizedGlobalFilter(secondRow!, 'delete')).toBe(false)
  })
})
