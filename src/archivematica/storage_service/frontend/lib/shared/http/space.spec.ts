import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { browseSpaceDirectory } from '@/shared/http/space'

const mockFetch = vi.fn()

describe('space http', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', mockFetch)
    mockFetch.mockReset()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('calls the space browse endpoint with path query', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      text: async () => JSON.stringify({ entries: [], directories: [] }),
    })

    await browseSpaceDirectory('space-uuid', '/home')

    expect(mockFetch).toHaveBeenCalled()
    const [url] = mockFetch.mock.calls[0] as [string, RequestInit?]
    const parsed = new URL(url)
    expect(parsed.pathname).toBe('/api/v2/space/space-uuid/browse/')
    expect(parsed.searchParams.get('path')).toBe('/home')
  })

  it('omits query when path is empty', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      text: async () => JSON.stringify({ entries: [], directories: [] }),
    })

    await browseSpaceDirectory('space-uuid', '')

    const [url] = mockFetch.mock.calls[0] as [string, RequestInit?]
    const parsed = new URL(url)
    expect(parsed.pathname).toBe('/api/v2/space/space-uuid/browse/')
    expect(parsed.searchParams.get('path')).toBeNull()
  })

  it('forwards request options', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      text: async () => JSON.stringify({ entries: [], directories: [] }),
    })

    const signal = new AbortController().signal
    await browseSpaceDirectory('space-uuid', '/tmp', { signal })

    const [, init] = mockFetch.mock.calls[0] as [string, RequestInit?]
    expect(init?.signal).toBe(signal)
  })

  it('throws when response is empty', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      text: async () => '',
    })

    await expect(browseSpaceDirectory('space-uuid', '/tmp')).rejects.toThrow('Expected JSON response')
  })
})
