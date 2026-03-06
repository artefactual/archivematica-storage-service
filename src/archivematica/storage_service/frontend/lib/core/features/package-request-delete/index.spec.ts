import { beforeEach, describe, expect, it, vi } from 'vitest'
import { init } from './index'

type Fixture = {
  requestDeleteLink: HTMLAnchorElement
}

const DELETE_REQUEST_URL = '/packages/65ef6700-29ec-45f0-938d-bdf6cb93d90c/request_deletion/'
const CSRF_TOKEN = 'csrf-token'

const setFixture = (): Fixture => {
  document.body.innerHTML = `
    <h1>All Packages</h1>
    <a
      id="request-delete"
      href="#"
      class="request-delete"
      data-package-request-delete-url="${DELETE_REQUEST_URL}"
      data-package-request-delete-csrf-token="${CSRF_TOKEN}"
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
    expect(requestUrl).toBe(`http://localhost:3000${DELETE_REQUEST_URL}`)
    expect(requestOptions.method).toBe('POST')
    expect(requestOptions.credentials).toBe('same-origin')
    const requestHeaders = new Headers(requestOptions.headers)
    expect(requestHeaders.get('X-Requested-With')).toBe('XMLHttpRequest')
    expect(requestHeaders.get('X-CSRFToken')).toBe(CSRF_TOKEN)
    expect(requestOptions.body).toBeNull()

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

  it('skips requests when request URL metadata is missing', async () => {
    const { requestDeleteLink } = setFixture()
    requestDeleteLink.removeAttribute('data-package-request-delete-url')
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)

    init()
    requestDeleteLink.click()
    await Promise.resolve()

    expect(fetchMock).not.toHaveBeenCalled()
    expect(document.getElementById('package-delete-alert')).toBeNull()
  })
})
