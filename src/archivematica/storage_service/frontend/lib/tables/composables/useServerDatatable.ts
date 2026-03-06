import { computed, onBeforeUnmount, ref, watch, type Ref } from 'vue'
import type { PaginationState, SortingState } from '@tanstack/vue-table'
import { buildDatatablesCompatParams } from '../utils/useDatatablesCompat'
import type { TableColumn, TableRow } from '../types'

type DatatablesAjaxResponse<TRow> = {
  iTotalRecords?: number
  iTotalDisplayRecords?: number
  aaData?: TRow[]
}

type UseServerDatatableOptions<TSourceRow> = {
  endpoint: string
  columns: TableColumn[]
  pagination: Ref<PaginationState>
  sorting: Ref<SortingState>
  search: Ref<string>
  filters?: Record<string, string>
  mapRow: (row: TSourceRow) => TableRow
}

const toNonNegativeInteger = (value: unknown): number => {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return Math.max(Math.trunc(value), 0)
  }
  if (typeof value === 'string') {
    const parsed = Number.parseInt(value, 10)
    if (!Number.isNaN(parsed)) {
      return Math.max(parsed, 0)
    }
  }
  return 0
}

const isAbortError = (error: unknown): boolean => {
  return error instanceof DOMException && error.name === 'AbortError'
}

export const useServerDatatable = <TSourceRow>(
  options: UseServerDatatableOptions<TSourceRow>,
) => {
  const rows = ref<TableRow[]>([])
  const totalRecords = ref(0)
  const totalDisplayRecords = ref(0)
  const loading = ref(false)
  const error = ref<string | null>(null)
  const drawCounter = ref(0)

  let activeController: AbortController | null = null
  let activeRequest = 0

  const queryState = computed(() => ({
    endpoint: options.endpoint,
    filters: options.filters ?? {},
    pageIndex: options.pagination.value.pageIndex,
    pageSize: options.pagination.value.pageSize,
    search: options.search.value,
    sortId: options.sorting.value[0]?.id ?? '',
    sortDesc: options.sorting.value[0]?.desc ?? false,
  }))

  const fetchRows = async (): Promise<void> => {
    activeController?.abort()
    const controller = new AbortController()
    activeController = controller
    activeRequest += 1
    const requestId = activeRequest

    drawCounter.value += 1
    loading.value = true
    error.value = null

    const params = buildDatatablesCompatParams({
      columns: options.columns,
      pagination: options.pagination.value,
      sorting: options.sorting.value,
      search: options.search.value,
      draw: drawCounter.value,
      filters: options.filters,
    })

    const separator = options.endpoint.includes('?') ? '&' : '?'
    const url = `${options.endpoint}${separator}${params.toString()}`

    try {
      const response = await fetch(url, {
        method: 'GET',
        headers: {
          'X-Requested-With': 'XMLHttpRequest',
        },
        credentials: 'same-origin',
        signal: controller.signal,
      })
      if (!response.ok) {
        throw new Error(`Request failed: ${response.status}`)
      }

      const payload = await response.json() as DatatablesAjaxResponse<TSourceRow>
      if (requestId !== activeRequest) {
        return
      }

      const sourceRows = Array.isArray(payload.aaData) ? payload.aaData : []
      rows.value = sourceRows.map(options.mapRow)
      totalRecords.value = toNonNegativeInteger(payload.iTotalRecords)
      totalDisplayRecords.value = toNonNegativeInteger(payload.iTotalDisplayRecords)
    } catch (err) {
      if (requestId !== activeRequest || isAbortError(err)) {
        return
      }
      rows.value = []
      totalRecords.value = 0
      totalDisplayRecords.value = 0
      error.value = err instanceof Error ? err.message : 'Request failed'
    } finally {
      if (requestId === activeRequest) {
        loading.value = false
      }
    }
  }

  watch(queryState, () => {
    void fetchRows()
  }, { immediate: true })

  onBeforeUnmount(() => {
    activeController?.abort()
  })

  return {
    rows,
    totalRecords,
    totalDisplayRecords,
    loading,
    error,
    refetch: fetchRows,
  }
}
