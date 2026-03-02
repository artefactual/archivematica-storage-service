type ModalApi = {
  show: (modal: HTMLElement, opener?: HTMLElement | null) => void
  hide: (modal: HTMLElement, options?: Readonly<{ restoreFocus?: boolean }>) => void
}

const BROWSE_BUTTON_ID = 'id_relative_path_browse'
const MODAL_API_WAIT_MS = 300
const MODAL_API_POLL_INTERVAL_MS = 25
const FALLBACK_BACKDROP_ATTR = 'data-am-location-form-backdrop'
const FALLBACK_MODAL_ATTR = 'data-am-location-form-fallback-modal'
const FALLBACK_OWNS_BACKDROP_ATTR = 'data-am-location-form-owns-backdrop'

const resolveModalApi = (): ModalApi | undefined => {
  return window.StorageServiceModal
}

const waitForModalApi = async (): Promise<ModalApi | undefined> => {
  const immediate = resolveModalApi()
  if (immediate) return immediate

  const maxAttempts = Math.ceil(MODAL_API_WAIT_MS / MODAL_API_POLL_INTERVAL_MS)
  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    await new Promise<void>((resolve) => {
      window.setTimeout(resolve, MODAL_API_POLL_INTERVAL_MS)
    })

    const api = resolveModalApi()
    if (api) return api
  }

  return undefined
}

const showModalFallback = (modal: HTMLElement): void => {
  modal.setAttribute(FALLBACK_MODAL_ATTR, 'true')
  modal.style.display = 'block'
  modal.classList.remove('hide')
  modal.classList.add('in')
  modal.setAttribute('aria-hidden', 'false')

  if (!document.querySelector('.modal-backdrop')) {
    const backdrop = document.createElement('div')
    backdrop.className = 'modal-backdrop fade in'
    backdrop.setAttribute(FALLBACK_BACKDROP_ATTR, 'true')
    document.body.append(backdrop)
    modal.setAttribute(FALLBACK_OWNS_BACKDROP_ATTR, 'true')
    document.body.classList.add('modal-open')
    return
  }

  modal.setAttribute(FALLBACK_OWNS_BACKDROP_ATTR, 'false')
}

const hideModalFallback = (modal: HTMLElement): void => {
  const ownsBackdrop = modal.getAttribute(FALLBACK_OWNS_BACKDROP_ATTR) === 'true'
  modal.removeAttribute(FALLBACK_MODAL_ATTR)
  modal.removeAttribute(FALLBACK_OWNS_BACKDROP_ATTR)
  modal.classList.remove('in')
  modal.classList.add('hide')
  modal.style.display = 'none'
  modal.setAttribute('aria-hidden', 'true')

  if (ownsBackdrop) {
    const fallbackBackdrops = document.querySelectorAll<HTMLElement>(
      `.modal-backdrop[${FALLBACK_BACKDROP_ATTR}="true"]`,
    )

    for (const backdrop of fallbackBackdrops) {
      backdrop.remove()
    }
  }

  if (
    ownsBackdrop
    && document.querySelectorAll('.modal.in').length === 0
    && document.querySelectorAll('.modal-backdrop').length === 0
  ) {
    document.body.classList.remove('modal-open')
  }
}

const openModal = async (modal: HTMLElement, opener: HTMLElement): Promise<void> => {
  const api = await waitForModalApi()
  if (api) {
    api.show(modal, opener)
    return
  }
  showModalFallback(modal)
}

const closeModal = (modal: HTMLElement): void => {
  if (modal.getAttribute(FALLBACK_MODAL_ATTR) === 'true') {
    hideModalFallback(modal)
    return
  }

  const api = resolveModalApi()
  if (api) {
    api.hide(modal)
    return
  }
  hideModalFallback(modal)
}

const createBrowseButton = (label: string): HTMLInputElement => {
  const button = document.createElement('input')
  button.id = BROWSE_BUTTON_ID
  button.type = 'button'
  button.value = label
  button.className = 'btn'
  button.setAttribute('data-am-modal-target', '#directory-select-modal')
  return button
}

export const initLocationFormModal = (): void => {
  const relativePathInput = document.getElementById('id_relative_path')
  const pickerMount = document.getElementById('location-directory-picker')
  const pickerModal = document.getElementById('directory-select-modal')

  if (!(relativePathInput instanceof HTMLInputElement || relativePathInput instanceof HTMLTextAreaElement)) return
  if (!(pickerMount instanceof HTMLElement)) return
  if (!(pickerModal instanceof HTMLElement)) return
  if (pickerMount.dataset.modalReady === 'true') return

  const browseLabel = pickerMount.dataset.browseLabel ?? 'Browse'

  let browseButton = document.getElementById(BROWSE_BUTTON_ID)
  if (!(browseButton instanceof HTMLInputElement)) {
    browseButton = createBrowseButton(browseLabel)
    relativePathInput.insertAdjacentElement('afterend', browseButton)
  }

  browseButton.addEventListener('click', (event) => {
    pickerMount.setAttribute('data-selected-relative-path', relativePathInput.value || '')

    // Primary path: declarative trigger is handled by the modal feature listener.
    if (resolveModalApi()) {
      return
    }

    // Fallback path: modal feature not ready yet, use bounded wait + direct show.
    event.preventDefault()
    void openModal(pickerModal, browseButton)
  })

  pickerModal.addEventListener('click', (event) => {
    const target = event.target
    if (!(target instanceof Element)) return

    const dismiss = target.closest<HTMLElement>('[data-dismiss="modal"]')
    if (!dismiss) return

    event.preventDefault()
    closeModal(pickerModal)
  })

  pickerMount.addEventListener('location-directory-picker:selected-path', (event) => {
    const detail = event instanceof CustomEvent && event.detail
      ? event.detail as { relativePath?: string }
      : {}

    relativePathInput.value = detail.relativePath ?? ''
    closeModal(pickerModal)
  })

  pickerMount.dataset.modalReady = 'true'
}
