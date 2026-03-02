import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AmClipboardFieldElement, defineAmClipboardField } from './index'

vi.mock('@/shared/i18n', () => ({
  initI18n: vi.fn().mockResolvedValue(undefined),
}))

vi.mock('@/shared/i18n/plain', () => ({
  translate: (value: string) =>
    (
      {
        'clipboardField.copy': 'Copy',
        'clipboardField.copied': 'Copied!',
        'clipboardField.copyFailed': 'Failed to copy. Copy the text manually.',
      } as const
    )[value as 'clipboardField.copy' | 'clipboardField.copied' | 'clipboardField.copyFailed'] ?? value,
}))

const writeText = vi.fn<(text: string) => Promise<void>>()
let upgradeTestElementCounter = 0

const clipboardStub = {
  writeText,
} as unknown as Clipboard

const setClipboard = (): void => {
  Object.defineProperty(navigator, 'clipboard', {
    configurable: true,
    value: clipboardStub,
  })
}

const buildFixture = () => {
  document.body.innerHTML = `
    <am-clipboard-field value="secret-key"></am-clipboard-field>
  `
}

const buildMultilineFixture = () => {
  document.body.innerHTML = '<am-clipboard-field multiline>line 1\nline 2</am-clipboard-field>'
}

describe('clipboard-field web component', () => {
  beforeEach(() => {
    setClipboard()
    writeText.mockReset()
    buildFixture()
    vi.useRealTimers()
    defineAmClipboardField()
  })

  it('renders a disabled input with the legacy copy icon', () => {
    const root = document.querySelector('am-clipboard-field')
    const input = root?.querySelector('input')
    const icon = root?.querySelector('i.am-clipboard-field__icon')
    const button = root?.querySelector('button')
    const status = root?.querySelector('[role="status"]')

    expect(input?.value).toBe('secret-key')
    expect(input?.disabled).toBe(true)
    expect(icon?.classList.contains('icon-share')).toBe(true)
    expect(icon?.getAttribute('aria-hidden')).toBe('true')
    expect(button?.getAttribute('aria-label')).toBe('Copy')
    expect(status?.getAttribute('aria-live')).toBe('polite')
    expect(status?.getAttribute('aria-atomic')).toBe('true')
    expect(status?.classList.contains('sr-only')).toBe(true)
  })

  it('registers the custom element in the CustomElementRegistry', () => {
    expect(customElements.get('am-clipboard-field')).toBe(AmClipboardFieldElement)
  })

  it('updates the rendered input when the value attribute changes', () => {
    const root = document.querySelector('am-clipboard-field') as HTMLElement
    const input = root.querySelector('input') as HTMLInputElement

    expect(input.value).toBe('secret-key')

    root.setAttribute('value', 'rotated-key')

    expect(input.value).toBe('rotated-key')
  })

  it('upgrades an existing element when defined after insertion', () => {
    upgradeTestElementCounter += 1
    const localTag = `am-clipboard-field-upgrade-test-${upgradeTestElementCounter}`

    class UpgradeTestElement extends AmClipboardFieldElement {}

    const root = document.createElement(localTag)
    root.setAttribute('value', 'late-defined-key')
    document.body.append(root)

    expect(root.querySelector('input')).toBeNull()

    customElements.define(localTag, UpgradeTestElement)

    const upgradedInput = root.querySelector('input') as HTMLInputElement | null
    expect(upgradedInput?.value).toBe('late-defined-key')
    expect(root).toBeInstanceOf(UpgradeTestElement)
  })

  it('copies text and shows temporary feedback', async () => {
    writeText.mockResolvedValueOnce()
    vi.useFakeTimers()

    const root = document.querySelector('am-clipboard-field')
    const button = root?.querySelector('button') as HTMLButtonElement
    const icon = root?.querySelector('i.am-clipboard-field__icon') as HTMLElement
    const status = root?.querySelector('[role="status"]') as HTMLElement

    button.click()
    await Promise.resolve()

    expect(writeText).toHaveBeenCalledWith('secret-key')
    expect(status.textContent).toBe('Copied!')
    expect(status.classList.contains('sr-only')).toBe(true)
    expect(status.classList.contains('text-danger')).toBe(false)
    expect(button.getAttribute('aria-label')).toBe('Copied!')
    expect(icon.classList.contains('icon-ok')).toBe(true)

    vi.advanceTimersByTime(1000)

    expect(status.textContent).toBe('')
    expect(status.classList.contains('sr-only')).toBe(true)
    expect(button.getAttribute('aria-label')).toBe('Copy')
    expect(icon.classList.contains('icon-share')).toBe(true)
  })

  it('shows error feedback if clipboard copy fails', async () => {
    writeText.mockRejectedValueOnce(new Error('nope'))
    const consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => undefined)

    const root = document.querySelector('am-clipboard-field')
    const button = root?.querySelector('button') as HTMLButtonElement
    const status = root?.querySelector('[role="status"]') as HTMLElement

    button.click()
    await Promise.resolve()
    await Promise.resolve()

    expect(status.textContent).toBe('Failed to copy. Copy the text manually.')
    expect(status.classList.contains('sr-only')).toBe(false)
    expect(status.classList.contains('text-danger')).toBe(true)
    expect(button.getAttribute('aria-label')).toBe('Failed to copy. Copy the text manually.')
    expect(consoleErrorSpy).toHaveBeenCalled()

    consoleErrorSpy.mockRestore()
  })

  it('renders a disabled textarea in multiline mode and copies its value', async () => {
    writeText.mockResolvedValueOnce()
    buildMultilineFixture()

    const root = document.querySelector('am-clipboard-field')
    const field = root?.querySelector('textarea') as HTMLTextAreaElement
    const button = root?.querySelector('button') as HTMLButtonElement

    expect(field.disabled).toBe(true)
    expect(field.classList.contains('input-xxlarge')).toBe(true)
    expect(field.classList.contains('uneditable-input')).toBe(true)
    expect(field.value).toBe('line 1\nline 2')

    button.click()
    await Promise.resolve()

    expect(writeText).toHaveBeenCalledWith('line 1\nline 2')
  })
})
