import { beforeEach, describe, expect, it, vi } from 'vitest'
import { init } from './index'

type Fixture = {
  requestDeleteLink: HTMLAnchorElement
}

const PACKAGE_UUID = '65ef6700-29ec-45f0-938d-bdf6cb93d90c'
const PIPELINE_UUID = 'f63d53ec-8f24-4e86-b7f0-c737dfd2b1ab'

const setFixture = (): Fixture => {
  document.body.innerHTML = `
    <h1>All Packages</h1>
    <div
      id="user-data-packages"
      data-uri="/"
      data-user-id="3"
      data-user-email="test@example.com"
      data-user-username="test"
      data-user-api-key="abc123"
    ></div>
    <a
      id="request-delete"
      href="#"
      class="request-delete"
      data-package-uuid="${PACKAGE_UUID}"
      data-package-pipeline="${PIPELINE_UUID}"
      data-package-type="DIP"
    >Request Deletion</a>
  `

  const requestDeleteLink = document.getElementById('request-delete')
  if (!(requestDeleteLink instanceof HTMLAnchorElement)) {
    throw new Error('Failed to build package request-delete fixture')
  }

  return { requestDeleteLink }
}

describe('core package-request-delete feature', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
    vi.restoreAllMocks()
  })

  it('submits deletion requests and renders success feedback', async () => {
    const { requestDeleteLink } = setFixture()
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ message: 'Request submitted.' }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    init()
    requestDeleteLink.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }))

    await vi.waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(1)
    })

    const [requestUrl, requestOptions] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(requestUrl).toContain(`/api/v2/file/${PACKAGE_UUID}/delete_aip/`)
    expect(requestOptions.method).toBe('POST')
    expect(requestOptions.headers).toEqual({
      'Authorization': 'ApiKey test:abc123',
      'Content-Type': 'application/json; charset=utf-8',
    })
    const payload = JSON.parse(String(requestOptions.body))
    expect(payload).toEqual({
      event_reason: `Storage Service user wants to delete DIP ${PACKAGE_UUID}.`,
      pipeline: PIPELINE_UUID,
      user_id: '3',
      user_email: 'test@example.com',
    })

    await vi.waitFor(() => {
      expect(document.getElementById('package-delete-alert')).not.toBeNull()
    })

    const alert = document.getElementById('package-delete-alert')
    expect(alert?.classList.contains('alert-success')).toBe(true)
    expect(alert?.textContent).toBe('Request submitted.')
  })

  it('renders warning feedback when deletion request fails', async () => {
    const { requestDeleteLink } = setFixture()
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ message: 'Request rejected.' }), {
        status: 400,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    init()
    requestDeleteLink.click()

    await vi.waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(1)
    })

    await vi.waitFor(() => {
      expect(document.getElementById('package-delete-alert')).not.toBeNull()
    })

    const alert = document.getElementById('package-delete-alert')
    expect(alert?.classList.contains('alert-warning')).toBe(true)
    expect(alert?.textContent).toBe('Request rejected.')
  })

  it('skips requests when user metadata is missing', async () => {
    const { requestDeleteLink } = setFixture()
    document.getElementById('user-data-packages')?.removeAttribute('data-user-api-key')
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)

    init()
    requestDeleteLink.click()
    await Promise.resolve()

    expect(fetchMock).not.toHaveBeenCalled()
    expect(document.getElementById('package-delete-alert')).toBeNull()
  })
})
