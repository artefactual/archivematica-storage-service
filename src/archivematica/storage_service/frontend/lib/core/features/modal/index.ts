type ModalState = {
  backdrop: HTMLDivElement | null
  opener: HTMLElement | null
}

declare global {
  interface Window {
    StorageServiceModal?: {
      show: (modal: HTMLElement, opener?: HTMLElement | null) => void
      hide: (modal: HTMLElement, options?: Readonly<{ restoreFocus?: boolean }>) => void
      toggle: (modal: HTMLElement, opener?: HTMLElement | null) => void
    }
  }
}

const MODAL_SELECTOR = '.modal'
const MODAL_OPEN_TRIGGER_SELECTOR = '[data-am-toggle="modal"], [data-am-modal-target]'
const MODAL_VISIBLE_CLASS = 'in'
const MODAL_HIDDEN_CLASS = 'hide'
const MODAL_OPEN_CLASS = 'modal-open'
const BACKDROP_CLASS = 'modal-backdrop'
const BACKDROP_FADE_CLASS = 'fade'
const BACKDROP_VISIBLE_CLASS = 'in'

const modalStates = new WeakMap<HTMLElement, ModalState>()
let listenersBound = false

const getModalState = (modal: HTMLElement): ModalState => {
  const state = modalStates.get(modal)
  if (state) return state

  const nextState: ModalState = {
    backdrop: null,
    opener: null,
  }
  modalStates.set(modal, nextState)
  return nextState
}

const getOpenModals = (): HTMLElement[] => {
  return Array.from(document.querySelectorAll<HTMLElement>(`${MODAL_SELECTOR}.${MODAL_VISIBLE_CLASS}`))
}

const dispatchModalEvent = (
  modal: HTMLElement,
  name: string,
  cancelable: boolean,
): boolean => {
  return modal.dispatchEvent(new Event(name, { bubbles: true, cancelable }))
}

const resolveFocusable = (modal: HTMLElement): HTMLElement | null => {
  return modal.querySelector<HTMLElement>(
    [
      '[autofocus]',
      'button:not([disabled])',
      '[href]',
      'input:not([disabled])',
      'select:not([disabled])',
      'textarea:not([disabled])',
      '[tabindex]:not([tabindex="-1"])',
    ].join(','),
  )
}

const focusModal = (modal: HTMLElement): void => {
  const target = resolveFocusable(modal)
  if (target) {
    target.focus()
    return
  }

  if (!modal.hasAttribute('tabindex')) {
    modal.setAttribute('tabindex', '-1')
  }
  modal.focus()
}

const appendBackdrop = (modal: HTMLElement): void => {
  const state = getModalState(modal)
  if (state.backdrop) return

  const backdrop = document.createElement('div')
  backdrop.className = `${BACKDROP_CLASS} ${BACKDROP_FADE_CLASS}`
  backdrop.addEventListener('click', () => {
    hideModal(modal)
  })

  document.body.append(backdrop)
  // Triggering layout allows fade styles to animate consistently.
  void backdrop.offsetWidth
  backdrop.classList.add(BACKDROP_VISIBLE_CLASS)
  state.backdrop = backdrop
  document.body.classList.add(MODAL_OPEN_CLASS)
}

const removeBackdrop = (modal: HTMLElement): void => {
  const state = getModalState(modal)
  if (state.backdrop) {
    state.backdrop.classList.remove(BACKDROP_VISIBLE_CLASS)
    state.backdrop.remove()
    state.backdrop = null
  }

  if (getOpenModals().length === 0) {
    document.body.classList.remove(MODAL_OPEN_CLASS)
  }
}

const setModalVisible = (modal: HTMLElement, visible: boolean): void => {
  if (visible) {
    modal.style.display = 'block'
    modal.classList.remove(MODAL_HIDDEN_CLASS)
    modal.classList.add(MODAL_VISIBLE_CLASS)
    modal.setAttribute('aria-hidden', 'false')
    return
  }

  modal.classList.remove(MODAL_VISIBLE_CLASS)
  modal.classList.add(MODAL_HIDDEN_CLASS)
  modal.style.display = 'none'
  modal.setAttribute('aria-hidden', 'true')
}

const isModalOpen = (modal: HTMLElement): boolean => {
  return modal.classList.contains(MODAL_VISIBLE_CLASS)
}

const closeOtherModals = (except: HTMLElement): void => {
  for (const modal of getOpenModals()) {
    if (modal === except) continue
    hideModal(modal, { restoreFocus: false })
  }
}

const resolveActiveElement = (): HTMLElement | null => {
  return document.activeElement instanceof HTMLElement ? document.activeElement : null
}

export const showModal = (modal: HTMLElement, opener?: HTMLElement | null): void => {
  if (isModalOpen(modal)) return
  if (!dispatchModalEvent(modal, 'show', true)) return

  closeOtherModals(modal)

  const state = getModalState(modal)
  state.opener = opener ?? resolveActiveElement()

  setModalVisible(modal, true)
  appendBackdrop(modal)
  focusModal(modal)
  dispatchModalEvent(modal, 'shown', false)
}

export const hideModal = (
  modal: HTMLElement,
  options: Readonly<{ restoreFocus?: boolean }> = {},
): void => {
  if (!isModalOpen(modal)) return
  if (!dispatchModalEvent(modal, 'hide', true)) return

  const state = getModalState(modal)
  const shouldRestoreFocus = options.restoreFocus !== false

  setModalVisible(modal, false)
  removeBackdrop(modal)

  if (shouldRestoreFocus && state.opener) {
    state.opener.focus()
  }
  state.opener = null

  dispatchModalEvent(modal, 'hidden', false)
}

export const toggleModal = (modal: HTMLElement, opener?: HTMLElement | null): void => {
  if (isModalOpen(modal)) {
    hideModal(modal)
    return
  }
  showModal(modal, opener)
}

const resolveSelectorFromTrigger = (trigger: HTMLElement): string | null => {
  const customTarget = trigger.getAttribute('data-am-modal-target')
  if (customTarget?.startsWith('#')) {
    return customTarget
  }

  const dataTarget = trigger.getAttribute('data-am-target')
  if (dataTarget?.startsWith('#')) {
    return dataTarget
  }

  const href = trigger.getAttribute('href')
  if (href?.startsWith('#') && href !== '#') {
    return href
  }

  return null
}

const resolveModalFromTrigger = (trigger: HTMLElement): HTMLElement | null => {
  const selector = resolveSelectorFromTrigger(trigger)
  if (!selector) return null
  return document.querySelector<HTMLElement>(selector)
}

const bindDocumentListeners = (): void => {
  if (listenersBound) return
  listenersBound = true

  document.addEventListener('click', (event) => {
    const target = event.target
    if (!(target instanceof Element)) return

    const dismissTrigger = target.closest<HTMLElement>('[data-dismiss="modal"]')
    if (dismissTrigger) {
      const modal = dismissTrigger.closest<HTMLElement>(MODAL_SELECTOR)
      if (modal) {
        event.preventDefault()
        hideModal(modal)
      }
      return
    }

    const toggleTrigger = target.closest<HTMLElement>(MODAL_OPEN_TRIGGER_SELECTOR)
    if (!toggleTrigger) return

    const modal = resolveModalFromTrigger(toggleTrigger)
    if (!modal) return

    event.preventDefault()
    showModal(modal, toggleTrigger)
  })

  document.addEventListener('keydown', (event) => {
    if (event.key !== 'Escape') return

    const openModals = getOpenModals()
    const topModal = openModals[openModals.length - 1]
    if (!topModal) return

    event.preventDefault()
    hideModal(topModal)
  })
}

const exposeGlobalApi = (): void => {
  window.StorageServiceModal = {
    show: showModal,
    hide: hideModal,
    toggle: toggleModal,
  }
}

export const init = (): void => {
  bindDocumentListeners()
  exposeGlobalApi()
}
