import { flushPromises, mount } from '@vue/test-utils'
import type { PaginationState, SortingState } from '@tanstack/vue-table'
import { defineComponent, nextTick, ref, type Ref } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { TableColumn, TableRow } from '../types'
import { useServerDatatable } from './useServerDatatable'

type SourceRow = {
  value: string
}

type Deferred<T> = {
  promise: Promise<T>
  resolve: (value: T) => void
  reject: (reason?: unknown) => void
}

type FetchResponse = {
  ok: boolean
  status?: number
  json?: () => Promise<unknown>
}

type ServerTableState = {
  rows: Ref<TableRow[]>
  totalRecords: Ref<number>
  totalDisplayRecords: Ref<number>
  loading: Ref<boolean>
  error: Ref<string | null>
  refetch: () => Promise<void>
}

const mockFetch = vi.fn()

const createDeferred = <T>(): Deferred<T> => {
  let resolve: (value: T) => void = () => {}
  let reject: (reason?: unknown) => void = () => {}
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })
  return { promise, resolve, reject }
}

const columns: TableColumn[] = [{ key: 'value', label: 'Value' }]

const requireTableState = (state: ServerTableState | null): ServerTableState => {
  if (state === null) {
    throw new Error('Failed to initialize useServerDatatable test harness.')
  }
  return state
}

const mountHarness = () => {
  const pagination = ref<PaginationState>({ pageIndex: 0, pageSize: 10 })
  const sorting = ref<SortingState>([])
  const search = ref('')
  let tableState: ServerTableState | null = null

  const Harness = defineComponent({
    setup() {
      tableState = useServerDatatable<SourceRow>({
        endpoint: '/locations/packages_ajax/',
        columns,
        pagination,
        sorting,
        search,
        mapRow: (row: SourceRow): TableRow => ({ value: row.value }),
      })
      return {}
    },
    template: '<div />',
  })

  const wrapper = mount(Harness)
  const initializedTableState = requireTableState(tableState)

  return {
    wrapper,
    search,
    tableState: initializedTableState,
  }
}

describe('useServerDatatable', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', mockFetch)
    mockFetch.mockReset()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('ignores stale responses after a newer request starts', async () => {
    const firstRequest = createDeferred<FetchResponse>()
    const secondRequest = createDeferred<FetchResponse>()
    mockFetch
      .mockImplementationOnce(() => firstRequest.promise as Promise<Response>)
      .mockImplementationOnce(() => secondRequest.promise as Promise<Response>)

    const { wrapper, search, tableState } = mountHarness()
    await nextTick()

    search.value = 'fresh'
    await nextTick()

    expect(mockFetch).toHaveBeenCalledTimes(2)
    const firstCallInit = mockFetch.mock.calls[0]?.[1] as RequestInit
    expect((firstCallInit.signal as AbortSignal).aborted).toBe(true)

    secondRequest.resolve({
      ok: true,
      json: async () => ({
        iTotalRecords: 1,
        iTotalDisplayRecords: 1,
        aaData: [{ value: 'fresh-result' }],
      }),
    })
    await flushPromises()

    expect(tableState.rows.value).toEqual([{ value: 'fresh-result' }])
    expect(tableState.error.value).toBeNull()

    firstRequest.resolve({
      ok: true,
      json: async () => ({
        iTotalRecords: 1,
        iTotalDisplayRecords: 1,
        aaData: [{ value: 'stale-result' }],
      }),
    })
    await flushPromises()

    expect(tableState.rows.value).toEqual([{ value: 'fresh-result' }])
    wrapper.unmount()
  })

  it('sets an error for failed requests and clears it on successful retry', async () => {
    mockFetch.mockResolvedValueOnce({ ok: false, status: 500 } as FetchResponse)
    const { wrapper, tableState } = mountHarness()
    await flushPromises()

    expect(tableState.error.value).toBe('Request failed: 500')
    expect(tableState.rows.value).toEqual([])
    expect(tableState.loading.value).toBe(false)

    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        iTotalRecords: 1,
        iTotalDisplayRecords: 1,
        aaData: [{ value: 'retry-result' }],
      }),
    } as FetchResponse)

    await tableState.refetch()
    await flushPromises()

    expect(tableState.error.value).toBeNull()
    expect(tableState.rows.value).toEqual([{ value: 'retry-result' }])
    wrapper.unmount()
  })
})
