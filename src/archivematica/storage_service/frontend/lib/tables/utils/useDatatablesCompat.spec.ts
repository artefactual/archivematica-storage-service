import { describe, expect, it } from 'vitest'
import { buildDatatablesCompatParams } from './useDatatablesCompat'

describe('buildDatatablesCompatParams', () => {
  it('builds pagination, search and sortable parameters', () => {
    const params = buildDatatablesCompatParams({
      columns: [
        { key: 'uuid', label: 'UUID', sortable: false },
        { key: 'origin_pipeline', label: 'Originating Pipeline', sortable: true },
      ],
      pagination: { pageIndex: 2, pageSize: 25 },
      sorting: [],
      search: 'abc',
      draw: 7,
      filters: {
        'location-uuid': '1234',
      },
    })

    expect(params.get('sEcho')).toBe('7')
    expect(params.get('iDisplayStart')).toBe('50')
    expect(params.get('iDisplayLength')).toBe('25')
    expect(params.get('sSearch')).toBe('abc')
    expect(params.get('iSortingCols')).toBe('0')
    expect(params.get('bSortable_0')).toBe('false')
    expect(params.get('bSortable_1')).toBe('true')
    expect(params.get('location-uuid')).toBe('1234')
  })

  it('maps sorting state to legacy DataTables sort parameters', () => {
    const params = buildDatatablesCompatParams({
      columns: [
        { key: 'date', label: 'Date' },
        { key: 'error', label: 'Error' },
      ],
      pagination: { pageIndex: 0, pageSize: 10 },
      sorting: [{ id: 'date', desc: true }],
      search: '',
      draw: 1,
    })

    expect(params.get('iSortingCols')).toBe('1')
    expect(params.get('iSortCol_0')).toBe('0')
    expect(params.get('sSortDir_0')).toBe('desc')
  })

  it('ignores sorting for unsortable columns', () => {
    const params = buildDatatablesCompatParams({
      columns: [
        { key: 'actions', label: 'Actions', sortable: false },
      ],
      pagination: { pageIndex: 0, pageSize: 10 },
      sorting: [{ id: 'actions', desc: false }],
      search: '',
      draw: 0,
    })

    expect(params.get('sEcho')).toBe('1')
    expect(params.get('iSortingCols')).toBe('0')
    expect(params.get('iSortCol_0')).toBeNull()
    expect(params.get('sSortDir_0')).toBeNull()
  })
})
