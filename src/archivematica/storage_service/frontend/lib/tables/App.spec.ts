import { nextTick } from 'vue'
import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import App from './App.vue'
import { createI18nMock } from '@/shared/i18n'
import type { TablePayload } from './types'
import { SEARCH_DEBOUNCE_MS } from './composables/useTableSearch'

const mockFetch = vi.fn()

const buildPayload = (): TablePayload => ({
  version: 1,
  kind: 'keys-list',
  columns: [
    { key: 'keyid', label: 'Keyid' },
    { key: 'fingerprint', label: 'Fingerprint' },
    { key: 'actions', label: 'Actions', sortable: false },
  ],
  rows: [
    {
      keyid: {
        kind: 'link',
        text: '1234',
        href: '/administration/key/1234/',
      },
      fingerprint: 'ABCDEF',
      actions: [{ label: 'Delete', href: '/administration/key/delete/1234/', style: 'default' }],
    },
  ],
  ui: {},
})

const buildOutOfOrderPayload = (): TablePayload => ({
  version: 1,
  kind: 'keys-list',
  columns: [
    { key: 'keyid', label: 'Keyid' },
    { key: 'fingerprint', label: 'Fingerprint' },
    { key: 'actions', label: 'Actions' },
  ],
  rows: [
    {
      keyid: {
        kind: 'link',
        text: 'B-Key',
        href: '/administration/key/B/',
      },
      fingerprint: 'bbb',
      actions: [{ label: 'Delete', href: '/administration/key/delete/B/', style: 'default' }],
    },
    {
      keyid: {
        kind: 'link',
        text: 'A-Key',
        href: '/administration/key/A/',
      },
      fingerprint: 'aaa',
      actions: [{ label: 'Delete', href: '/administration/key/delete/A/', style: 'default' }],
    },
  ],
  ui: {},
})

const buildTokenizedSearchPayload = (): TablePayload => ({
  version: 1,
  kind: 'locations-list',
  columns: [
    { key: 'description', label: 'Description' },
    { key: 'actions', label: 'Actions', sortable: false },
  ],
  rows: [
    {
      description: 'Default AIP recovery',
      actions: [{ label: 'Edit', href: '/locations/1/edit/', style: 'default' }],
    },
    {
      description: 'Default transfer source',
      actions: [{ label: 'Edit', href: '/locations/2/edit/', style: 'default' }],
    },
  ],
  ui: {},
})

const buildActionsSearchPayload = (): TablePayload => ({
  version: 1,
  kind: 'locations-list',
  columns: [
    { key: 'description', label: 'Description' },
    { key: 'actions', label: 'Actions', sortable: false },
  ],
  rows: [
    {
      description: 'Default AIP recovery',
      actions: [{ label: 'Delete', href: '/locations/1/delete/', style: 'default' }],
    },
  ],
  ui: {},
})

const buildLargePayload = (): TablePayload => ({
  version: 1,
  kind: 'locations-list',
  columns: [
    { key: 'description', label: 'Description' },
  ],
  rows: Array.from({ length: 1234 }, (_, index) => ({
    description: `Location ${index + 1}`,
  })),
  ui: {},
})

const buildPendingRequestsPayload = (): TablePayload => ({
  version: 1,
  kind: 'package-requests-pending',
  columns: [
    { key: 'file', label: 'File' },
    { key: 'type', label: 'Type' },
    { key: 'reason', label: 'Reason' },
    { key: 'pipeline', label: 'Pipeline' },
    { key: 'user', label: 'User' },
    { key: 'submitted', label: 'Submitted' },
    { key: 'actions', label: 'Approve/Reject', sortable: false },
  ],
  rows: [
    {
      file: 'example-aip',
      type: 'AIP',
      reason: 'cleanup request',
      pipeline: 'Pipeline A',
      user: 'demo@example.com (ID: 1)',
      submitted: '2026-03-03 10:00',
      actions: {
        kind: 'decision-form',
        action: '/packages/delete/requests/',
        method: 'post',
        csrfToken: 'csrf-token',
        eventIdName: 'event_id',
        eventId: 42,
        reasonName: 'status_reason',
        reasonLabel: 'Status reason:',
        reasonValue: 'Needs cleanup',
        reasonErrors: ['A reason is required.'],
        decisionName: 'decision',
        approveValue: 'approve',
        rejectValue: 'reject',
        approveLabel: 'Approve (Delete package)',
        rejectLabel: 'Reject (No change to package)',
      },
    },
  ],
  ui: {},
})

const buildPackagesServerPayload = (): TablePayload => ({
  version: 1,
  kind: 'packages-server',
  columns: [
    { key: 'uuid', label: 'UUID', sortable: false },
    { key: 'origin_pipeline', label: 'Originating Pipeline' },
    { key: 'current_location', label: 'Current Location' },
    { key: 'size', label: 'Size' },
    { key: 'package_type', label: 'Type' },
    { key: 'replica_of', label: 'Replica Of' },
    { key: 'status', label: 'Status' },
    { key: 'stored', label: 'Stored' },
    { key: 'fixity_date', label: 'Fixity Date' },
    { key: 'fixity_status', label: 'Fixity Status' },
    { key: 'actions', label: 'Actions', sortable: false },
  ],
  rows: [],
  ui: {
    server: {
      mode: 'server-datatables-v1',
      endpoint: '/locations/packages_ajax/',
      defaultSort: {
        columnKey: 'origin_pipeline',
        direction: 'asc',
      },
    },
  },
})

const buildFixityServerPayload = (): TablePayload => ({
  version: 1,
  kind: 'fixity-logs-server',
  columns: [
    { key: 'date', label: 'Date' },
    { key: 'error', label: 'Error' },
  ],
  rows: [],
  ui: {
    server: {
      mode: 'server-datatables-v1',
      endpoint: '/locations/fixity_ajax/',
      filters: {
        'package-uuid': 'pkg-1',
      },
      defaultSort: {
        columnKey: 'date',
        direction: 'desc',
      },
    },
  },
})

const applySearch = async (wrapper: ReturnType<typeof mount>, query: string): Promise<void> => {
  await wrapper.find('input[type="search"]').setValue(query)
  await nextTick()
  vi.advanceTimersByTime(SEARCH_DEBOUNCE_MS)
  await nextTick()
}

const lastFetchUrl = (): string => {
  const calls = mockFetch.mock.calls as unknown[][]
  if (calls.length === 0) {
    return ''
  }
  return String(calls[calls.length - 1][0])
}

describe('tables/App', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', mockFetch)
    mockFetch.mockReset()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('renders rows, links and actions', () => {
    const wrapper = mount(App, {
      props: { payload: buildPayload() },
      global: {
        plugins: [createI18nMock()],
      },
    })

    expect(wrapper.text()).toContain('1234')
    expect(wrapper.text()).toContain('ABCDEF')
    expect(wrapper.text()).toContain('Delete')
    expect(wrapper.find('a[href="/administration/key/1234/"]').exists()).toBe(true)
  })

  it('shows empty message when search filters all rows out', async () => {
    vi.useFakeTimers()
    try {
      const wrapper = mount(App, {
        props: { payload: buildPayload() },
        global: {
          plugins: [createI18nMock()],
        },
      })

      await applySearch(wrapper, 'missing-value')

      expect(wrapper.text()).toContain('No matching records found')
      expect(wrapper.text()).toContain(
        'Showing 0 to 0 of 0 entries (filtered from 1 total entries)',
      )
      expect(wrapper.find('tbody tr').classes()).toContain('ss-table-row--odd')
    } finally {
      vi.useRealTimers()
    }
  })

  it('matches space-separated search terms with smart tokenized filtering', async () => {
    vi.useFakeTimers()
    try {
      const wrapper = mount(App, {
        props: { payload: buildTokenizedSearchPayload() },
        global: {
          plugins: [createI18nMock()],
        },
      })

      await applySearch(wrapper, 'default recovery')

      expect(wrapper.text()).toContain('Default AIP recovery')
      expect(wrapper.text()).not.toContain('Default transfer source')
      expect(wrapper.text()).not.toContain('No matching records found')
    } finally {
      vi.useRealTimers()
    }
  })

  it('does not match rows by actions labels', async () => {
    vi.useFakeTimers()
    try {
      const wrapper = mount(App, {
        props: { payload: buildActionsSearchPayload() },
        global: {
          plugins: [createI18nMock()],
        },
      })

      await applySearch(wrapper, 'delete')

      expect(wrapper.text()).toContain('No matching records found')
      expect(wrapper.text()).not.toContain('Default AIP recovery')
    } finally {
      vi.useRealTimers()
    }
  })

  it('sorts by first column ascending on initial render', () => {
    const wrapper = mount(App, {
      props: { payload: buildOutOfOrderPayload() },
      global: {
        plugins: [createI18nMock()],
      },
    })

    const firstColumnValues = wrapper
      .findAll('tbody tr td:first-child')
      .map(cell => cell.text().trim())

    expect(firstColumnValues).toEqual(['A-Key', 'B-Key'])
  })

  it('formats pager info numbers with locale-aware separators', () => {
    const wrapper = mount(App, {
      props: { payload: buildLargePayload() },
      global: {
        plugins: [createI18nMock()],
      },
    })

    expect(wrapper.text()).toContain('Showing 1 to 10 of 1,234 entries')
  })

  it('renders package request decision forms in actions cells', () => {
    const wrapper = mount(App, {
      props: { payload: buildPendingRequestsPayload() },
      global: {
        plugins: [createI18nMock()],
      },
    })

    const form = wrapper.find('form[action="/packages/delete/requests/"]')
    expect(form.exists()).toBe(true)
    expect(form.find('input[name="csrfmiddlewaretoken"]').attributes('value')).toBe('csrf-token')
    expect(form.find('input[name="event_id"]').attributes('value')).toBe('42')
    const reasonTextarea = form.find('textarea[name="status_reason"]')
    expect((reasonTextarea.element as HTMLTextAreaElement).value).toContain('Needs cleanup')
    expect(form.text()).toContain('Approve (Delete package)')
    expect(form.text()).toContain('Reject (No change to package)')
    expect(wrapper.text()).toContain('A reason is required.')
  })

  it('renders server-side package rows and action controls', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        iTotalRecords: 1,
        iTotalDisplayRecords: 1,
        sEcho: 1,
        aaData: [
          {
            uuid: 'pkg-1',
            origin_pipeline: { text: 'Pipeline A', href: '/pipelines/1/' },
            current_location: { text: '/var/aip/pkg-1.7z', href: '/download/pkg-1/' },
            size: '1 KB',
            package_type: 'AIP',
            replica_of: '',
            status: { text: 'Stored', update_href: '/packages/pkg-1/status/' },
            stored: '2026-03-05 12:00',
            fixity_date: '2026-03-05 12:01',
            fixity_status: { text: 'Success', href: '/fixity/pkg-1/' },
            actions: {
              pointer_file_href: '/pointer/pkg-1/',
              download_href: '/download/pkg-1/',
              reingest_href: '/reingest/pkg-1/',
              request_delete: {
                package_type: 'AIP',
                package_uuid: 'pkg-1',
                pipeline_uuid: 'pipeline-1',
              },
              direct_delete: {
                action_url: '/packages/pkg-1/delete/',
                csrf_token: 'csrf-token',
                modal_id: 'confirm-delete-pkg-1',
                modal_label_id: 'confirm-delete-title-pkg-1',
                modal_title: 'Delete package',
                prompt_text: 'Confirm delete',
                close_label: 'Close',
                confirm_label: 'Delete',
              },
            },
          },
        ],
      }),
    })

    const wrapper = mount(App, {
      props: { payload: buildPackagesServerPayload() },
      global: {
        plugins: [createI18nMock()],
      },
    })

    await flushPromises()

    expect(mockFetch).toHaveBeenCalledTimes(1)
    expect(wrapper.text()).toContain('pkg-1')
    expect(wrapper.find('a.request-delete[data-package-uuid="pkg-1"]').exists()).toBe(true)
    expect(wrapper.find('form[action="/packages/pkg-1/delete/"]').exists()).toBe(true)
    expect(wrapper.find('#confirm-delete-pkg-1').exists()).toBe(true)
  })

  it('builds legacy DataTables query params for server sorting, paging and search', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        iTotalRecords: 200,
        iTotalDisplayRecords: 200,
        sEcho: 1,
        aaData: [{ date: '2026-03-05', error: '' }],
      }),
    })

    const wrapper = mount(App, {
      props: { payload: buildFixityServerPayload() },
      global: {
        plugins: [createI18nMock()],
      },
    })

    await flushPromises()

    const firstCallUrl = String(mockFetch.mock.calls[0][0])
    expect(firstCallUrl).toContain('/locations/fixity_ajax/?')
    expect(firstCallUrl).toContain('iSortCol_0=0')
    expect(firstCallUrl).toContain('sSortDir_0=desc')
    expect(firstCallUrl).toContain('package-uuid=pkg-1')

    await wrapper.findAll('.ss-table-sort-button')[1]?.trigger('click')
    await flushPromises()
    const sortCallUrl = lastFetchUrl()
    expect(sortCallUrl).toContain('iSortCol_0=1')
    expect(sortCallUrl).toContain('sSortDir_0=asc')

    await wrapper.find('.ss-table-length__select').setValue('25')
    await flushPromises()
    const pageSizeUrl = lastFetchUrl()
    expect(pageSizeUrl).toContain('iDisplayLength=25')

    await wrapper.find('.ss-table-pagination__link--next').trigger('click')
    await flushPromises()
    const nextPageUrl = lastFetchUrl()
    expect(nextPageUrl).toContain('iDisplayStart=25')

    vi.useFakeTimers()
    try {
      await applySearch(wrapper, 'disk error')
      await flushPromises()
    } finally {
      vi.useRealTimers()
    }
    const searchUrl = lastFetchUrl()
    expect(searchUrl).toContain('sSearch=disk+error')
    expect(searchUrl).toContain('iDisplayStart=0')
  })
})
