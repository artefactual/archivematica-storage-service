import { nextTick } from 'vue'
import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import App from './App.vue'
import { createI18nMock } from '@/shared/i18n'
import type { TablePayload } from './types'
import { SEARCH_DEBOUNCE_MS } from './useTableSearch'

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

const applySearch = async (wrapper: ReturnType<typeof mount>, query: string): Promise<void> => {
  await wrapper.find('input[type="search"]').setValue(query)
  await nextTick()
  vi.advanceTimersByTime(SEARCH_DEBOUNCE_MS)
  await nextTick()
}

describe('tables/App', () => {
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
})
