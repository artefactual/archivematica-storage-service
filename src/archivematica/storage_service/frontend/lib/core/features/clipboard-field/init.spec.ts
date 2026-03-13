import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

type Deferred = {
  promise: Promise<void>
  resolve: () => void
  reject: (reason?: unknown) => void
}

const LABELS = {
  'clipboardField.copy': 'Copy',
  'clipboardField.copied': 'Copied!',
  'clipboardField.copyFailed': 'Failed to copy. Copy the text manually.',
} as const

const createDeferred = (): Deferred => {
  let resolve!: () => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<void>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

const mockI18nModule = (
  initI18n: () => Promise<void>,
  isLocaleReady: () => boolean = () => true,
): void => {
  vi.doMock('@/shared/i18n', () => ({
    i18n: {
      global: {
        te: (key: string) => isLocaleReady() && key in LABELS,
        t: (key: string) => LABELS[key as keyof typeof LABELS] ?? key,
      },
    },
    initI18n,
  }))
}

describe('clipboard-field init', () => {
  beforeEach(() => {
    vi.resetModules()
    vi.restoreAllMocks()
    document.body.innerHTML = ''
  })

  afterEach(() => {
    vi.doUnmock('@/shared/i18n')
  })

  it('defines the element even if i18n init rejects', async () => {
    const initI18n = vi.fn().mockRejectedValue(new Error('boom'))
    const consoleWarnSpy = vi.spyOn(console, 'warn').mockImplementation(() => undefined)

    mockI18nModule(initI18n)

    const defineSpy = vi.spyOn(customElements, 'define').mockImplementation(() => undefined)
    vi.spyOn(customElements, 'get').mockReturnValue(undefined)

    const { init } = await import('./index')

    await expect(init()).resolves.toBeUndefined()

    expect(initI18n).toHaveBeenCalledTimes(1)
    expect(defineSpy).toHaveBeenCalledTimes(1)
    expect(defineSpy).toHaveBeenCalledWith(
      'am-clipboard-field',
      expect.any(Function),
    )
    expect(consoleWarnSpy).toHaveBeenCalled()
  })

  it('waits for i18n before defining and renders translated labels', async () => {
    const deferred = createDeferred()
    let localeReady = false

    mockI18nModule(
      vi.fn(async () => {
        await deferred.promise
        localeReady = true
      }),
      () => localeReady,
    )

    const { init } = await import('./index')
    const initPromise = init()

    expect(customElements.get('am-clipboard-field')).toBeUndefined()

    deferred.resolve()
    await initPromise

    expect(customElements.get('am-clipboard-field')).toBeDefined()

    document.body.innerHTML = '<am-clipboard-field value="secret-key"></am-clipboard-field>'
    const button = document.querySelector('button')
    expect(button?.getAttribute('aria-label')).toBe('Copy')
    expect(button?.getAttribute('aria-label')).not.toBe('clipboardField.copy')
  })
})
