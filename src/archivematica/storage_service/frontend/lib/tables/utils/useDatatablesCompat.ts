import type { PaginationState, SortingState } from '@tanstack/vue-table'
import type { TableColumn } from '../types'

type BuildDatatablesCompatParamsOptions = {
  columns: TableColumn[]
  pagination: PaginationState
  sorting: SortingState
  search: string
  draw: number
  filters?: Record<string, string>
}

const serializeSortDirection = (isDescending: boolean | undefined): string => {
  return isDescending ? 'desc' : 'asc'
}

const sortableByIndex = (columns: TableColumn[], index: number): boolean => {
  const column = columns[index]
  if (!column) {
    return false
  }
  return column.sortable ?? true
}

const resolveSortColumnIndex = (
  columns: TableColumn[],
  sorting: SortingState,
): number | null => {
  const first = sorting[0]
  if (!first) {
    return null
  }

  const index = columns.findIndex(column => column.key === first.id)
  if (index < 0 || !sortableByIndex(columns, index)) {
    return null
  }
  return index
}

export const buildDatatablesCompatParams = (
  options: BuildDatatablesCompatParamsOptions,
): URLSearchParams => {
  const params = new URLSearchParams()
  const { columns, pagination, sorting, search, draw, filters } = options

  params.set('sEcho', String(Math.max(draw, 1)))
  params.set('iDisplayStart', String(Math.max(pagination.pageIndex * pagination.pageSize, 0)))
  params.set('iDisplayLength', String(Math.max(pagination.pageSize, 1)))
  params.set('sSearch', search)

  columns.forEach((column, index) => {
    params.set(`bSortable_${index}`, String(column.sortable ?? true))
  })

  const sortColumnIndex = resolveSortColumnIndex(columns, sorting)
  if (sortColumnIndex === null) {
    params.set('iSortingCols', '0')
  } else {
    params.set('iSortingCols', '1')
    params.set('iSortCol_0', String(sortColumnIndex))
    params.set('sSortDir_0', serializeSortDirection(sorting[0]?.desc))
  }

  Object.entries(filters ?? {}).forEach(([key, value]) => {
    if (value.length > 0) {
      params.set(key, value)
    }
  })

  return params
}
