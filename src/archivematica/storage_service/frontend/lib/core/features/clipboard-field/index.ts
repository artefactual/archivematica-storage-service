import './style.css'
import { initI18n } from '@/shared/i18n'
import { translate } from '@/shared/i18n/plain'

const CUSTOM_ELEMENT_NAME = 'am-clipboard-field'
const RESET_DELAY_MS = 1000

type Labels = Readonly<{
  copy: string
  copied: string
  copyFailed: string
}>

const getLabels = (): Labels => ({
  copy: translate('clipboardField.copy'),
  copied: translate('clipboardField.copied'),
  copyFailed: translate('clipboardField.copyFailed'),
})

export class AmClipboardFieldElement extends HTMLElement {
  private button: HTMLButtonElement | null = null
  private field: HTMLInputElement | HTMLTextAreaElement | null = null
  private icon: HTMLElement | null = null
  private status: HTMLElement | null = null
  private resetTimerId: number | null = null
  private bound = false

  static get observedAttributes(): string[] {
    return ['value']
  }

  connectedCallback(): void {
    if (!this.hasAttribute('role')) {
      this.setAttribute('role', 'group')
    }

    if (!this.querySelector('.am-clipboard-field__input-group')) {
      this.render()
    }

    this.cacheElements()
    if (!this.classList.contains('am-clipboard-field')) {
      this.classList.add('am-clipboard-field')
    }
    if (!this.bound && this.button) {
      this.button.addEventListener('click', this.onCopyClick)
      this.bound = true
    }
  }

  disconnectedCallback(): void {
    if (this.button && this.bound) {
      this.button.removeEventListener('click', this.onCopyClick)
    }
    this.bound = false
    this.clearResetTimer()
  }

  attributeChangedCallback(name: string, _oldValue: string | null, newValue: string | null): void {
    if (name !== 'value') return
    if (this.field) {
      this.field.value = newValue ?? ''
    }
  }

  private render(): void {
    const labels = getLabels()
    const value = this.getAttribute('value') ?? this.textContent ?? ''
    const multiline = this.hasAttribute('multiline')
    const doc = this.ownerDocument

    // Light DOM keeps existing SS Bootstrap 2 styles working.
    const inputGroup = doc.createElement('div')
    inputGroup.className = 'input-prepend am-clipboard-field__input-group'

    const button = doc.createElement('button')
    button.className = 'btn am-clipboard-field__button'
    button.type = 'button'
    button.title = labels.copy
    button.setAttribute('aria-label', labels.copy)
    button.style.margin = '0 -1px 0 0'

    const icon = doc.createElement('i')
    icon.className = 'icon-share am-clipboard-field__icon'
    icon.setAttribute('aria-hidden', 'true')

    button.append(icon)
    inputGroup.append(button)

    if (multiline) {
      const textarea = doc.createElement('textarea')
      textarea.className = 'input-xxlarge uneditable-input am-clipboard-field__input'
      textarea.value = value
      textarea.disabled = true
      textarea.style.cursor = 'default'
      textarea.style.resize = 'vertical'
      textarea.style.height = '100px'
      inputGroup.append(textarea)
    } else {
      const input = doc.createElement('input')
      input.type = 'text'
      input.className = 'input-xxlarge am-clipboard-field__input'
      input.value = value
      input.disabled = true
      input.style.cursor = 'default'
      inputGroup.append(input)
    }

    const status = doc.createElement('p')
    status.className = 'help-block sr-only am-clipboard-field__status'
    status.setAttribute('role', 'status')
    status.setAttribute('aria-live', 'polite')
    status.setAttribute('aria-atomic', 'true')

    this.replaceChildren(inputGroup, status)
  }

  private cacheElements(): void {
    this.button = this.querySelector<HTMLButtonElement>('button')
    this.field = this.querySelector<HTMLInputElement | HTMLTextAreaElement>('input, textarea')
    this.icon = this.querySelector<HTMLElement>('i.am-clipboard-field__icon')
    this.status = this.querySelector<HTMLElement>('[role="status"]')
  }

  private clearResetTimer(): void {
    if (this.resetTimerId === null) return
    window.clearTimeout(this.resetTimerId)
    this.resetTimerId = null
  }

  private setStatus(text: string): void {
    if (this.status) {
      this.status.textContent = text
    }
  }

  private setStatusVisible(isVisible: boolean): void {
    if (!this.status) return
    this.status.classList.toggle('sr-only', !isVisible)
  }

  private setStatusIsError(isError: boolean): void {
    if (!this.status) return
    this.status.classList.toggle('text-danger', isError)
  }

  private setButtonLabel(text: string): void {
    if (!this.button) return
    this.button.setAttribute('aria-label', text)
    this.button.setAttribute('title', text)
  }

  private setCopiedIconState(isCopied: boolean): void {
    if (!this.icon) return

    this.icon.classList.toggle('icon-share', !isCopied)
    this.icon.classList.toggle('icon-ok', isCopied)
    this.icon.classList.toggle('am-clipboard-field-icon-copied', isCopied)
    if (!isCopied) {
      this.icon.classList.remove('am-clipboard-field-icon-copied-animate')
      return
    }

    // Re-add the class so rapid successive successful copies replay the motion.
    this.icon.classList.remove('am-clipboard-field-icon-copied-animate')
    // Force reflow to restart the keyframe animation.
    void this.icon.offsetWidth
    this.icon.classList.add('am-clipboard-field-icon-copied-animate')
  }

  private resetFeedback(): void {
    const labels = getLabels()
    this.setCopiedIconState(false)
    this.setStatus('')
    this.setStatusVisible(false)
    this.setStatusIsError(false)
    this.setButtonLabel(labels.copy)
  }

  private showCopiedFeedback(): void {
    const labels = getLabels()

    this.clearResetTimer()
    this.setCopiedIconState(true)
    this.setStatus(labels.copied)
    this.setStatusVisible(false)
    this.setStatusIsError(false)
    this.setButtonLabel(labels.copied)

    this.resetTimerId = window.setTimeout(() => {
      this.resetFeedback()
      this.resetTimerId = null
    }, RESET_DELAY_MS)
  }

  private showCopyError(): void {
    const labels = getLabels()
    this.clearResetTimer()
    this.setCopiedIconState(false)
    this.setStatus(labels.copyFailed)
    this.setStatusVisible(true)
    this.setStatusIsError(true)
    this.setButtonLabel(labels.copyFailed)
  }

  private readonly onCopyClick = (): void => {
    void this.copyValue()
  }

  private async copyValue(): Promise<void> {
    if (!this.field) return

    try {
      if (!navigator.clipboard?.writeText) {
        throw new Error('Clipboard API is not available')
      }

      await navigator.clipboard.writeText(this.field.value)
      this.showCopiedFeedback()
    } catch (err) {
      console.error('Failed to copy clipboard field value:', err)
      this.showCopyError()
    }
  }
}

export const defineAmClipboardField = (): void => {
  if (customElements.get(CUSTOM_ELEMENT_NAME)) return
  customElements.define(CUSTOM_ELEMENT_NAME, AmClipboardFieldElement)
}

export async function init(): Promise<void> {
  try {
    await initI18n()
  } catch (error) {
    console.warn('Failed to initialize clipboard field i18n:', error)
  } finally {
    defineAmClipboardField()
  }
}
