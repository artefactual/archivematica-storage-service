import { beforeEach, describe, expect, it, vi } from 'vitest'
import { init } from './index'

const ACCESS_PROTOCOL_FIELD_ID = 'id_space-access_protocol'
const PROTOCOL_CONTAINER_ID = 'protocol_form'
const PROTOCOL_URL = '/locations/ajax_space_create_protocol_form/'

type Fixture = {
  protocolField: HTMLSelectElement
  protocolContainer: HTMLElement
}

const setFixture = (): Fixture => {
  document.body.innerHTML = `
    <form data-space-protocol-form-url="${PROTOCOL_URL}">
      <p>
        <label for="${ACCESS_PROTOCOL_FIELD_ID}">Access protocol:</label>
        <select id="${ACCESS_PROTOCOL_FIELD_ID}">
          <option value="FS">Filesystem</option>
          <option value="GPG">GPG</option>
        </select>
      </p>
      <div id="${PROTOCOL_CONTAINER_ID}"><p>Current protocol fields</p></div>
    </form>
  `

  const protocolField = document.getElementById(ACCESS_PROTOCOL_FIELD_ID)
  const protocolContainer = document.getElementById(PROTOCOL_CONTAINER_ID)
  if (!(protocolField instanceof HTMLSelectElement) || !(protocolContainer instanceof HTMLElement)) {
    throw new Error('Failed to build space protocol fixture')
  }

  return { protocolField, protocolContainer }
}

describe('core space-protocol feature', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
    vi.restoreAllMocks()
  })

  it('updates protocol fields when access protocol changes', async () => {
    const { protocolField, protocolContainer } = setFixture()
    const fetchMock = vi.fn().mockResolvedValue(
      new Response('<p>Updated protocol fields</p>', { status: 200 }),
    )
    vi.stubGlobal('fetch', fetchMock)

    init()

    protocolField.value = 'GPG'
    protocolField.dispatchEvent(new Event('change', { bubbles: true }))

    await vi.waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(1)
    })

    const [requestUrl, requestOptions] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(requestUrl).toContain(`${PROTOCOL_URL}?protocol=GPG`)
    expect(requestOptions.credentials).toBe('same-origin')
    await vi.waitFor(() => {
      expect(protocolContainer.innerHTML).toContain('Updated protocol fields')
    })
  })

  it('does nothing when feature root is missing required fields', () => {
    document.body.innerHTML = '<form data-space-protocol-form-url="/foo"></form>'

    expect(() => init()).not.toThrow()
  })
})
