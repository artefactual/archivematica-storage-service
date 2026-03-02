const COLLAPSE_TRIGGER_SELECTOR = '[data-am-toggle="collapse"]'
const NAV_TRIGGER_SELECTOR = `.navbar ${COLLAPSE_TRIGGER_SELECTOR}`
const OPEN_CLASS = 'in'
const MOBILE_MEDIA_QUERY = '(max-width: 979px)'

let listenersBound = false
let resizeListenerBound = false

const isMobileViewport = (): boolean => {
  if (typeof window.matchMedia === 'function') {
    return window.matchMedia(MOBILE_MEDIA_QUERY).matches
  }
  return window.innerWidth <= 979
}

const resolveSelector = (trigger: HTMLElement): string | null => {
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

const resolveTarget = (trigger: HTMLElement): HTMLElement | null => {
  const selector = resolveSelector(trigger)
  if (!selector) return null
  return document.querySelector<HTMLElement>(selector)
}

const resolveNavTarget = (trigger: HTMLElement): HTMLElement | null => {
  const target = resolveTarget(trigger)
  if (!target?.classList.contains('nav-collapse')) {
    return null
  }
  return target
}

const setExpanded = (trigger: HTMLElement, isExpanded: boolean): void => {
  trigger.setAttribute('aria-expanded', String(isExpanded))
}

const applyExpandedState = (
  target: HTMLElement,
  isExpanded: boolean,
  shouldCollapse: boolean,
): void => {
  if (!shouldCollapse) {
    target.classList.remove(OPEN_CLASS)
    target.removeAttribute('aria-hidden')
    target.style.height = ''
    target.style.overflow = ''
    return
  }

  target.classList.toggle(OPEN_CLASS, isExpanded)
  target.setAttribute('aria-hidden', String(!isExpanded))

  if (!target.classList.contains('nav-collapse')) {
    return
  }

  if (isExpanded) {
    target.style.height = 'auto'
    target.style.overflow = 'visible'
    return
  }

  target.style.height = '0px'
  target.style.overflow = 'hidden'
}

const syncTriggerState = (trigger: HTMLElement): void => {
  const target = resolveNavTarget(trigger)
  if (!target) return

  const shouldCollapse = isMobileViewport()
  const isExpanded = shouldCollapse
    ? target.classList.contains(OPEN_CLASS)
    : true
  setExpanded(trigger, isExpanded)
  applyExpandedState(target, isExpanded, shouldCollapse)
}

const syncAllTriggers = (): void => {
  for (const trigger of document.querySelectorAll<HTMLElement>(NAV_TRIGGER_SELECTOR)) {
    syncTriggerState(trigger)
  }
}

const toggleCollapse = (trigger: HTMLElement): void => {
  const target = resolveNavTarget(trigger)
  if (!target) return

  if (!isMobileViewport()) {
    setExpanded(trigger, true)
    applyExpandedState(target, true, false)
    return
  }

  const isExpanded = target.classList.contains(OPEN_CLASS)
  applyExpandedState(target, !isExpanded, true)
  setExpanded(trigger, !isExpanded)
}

const bindListeners = (): void => {
  if (listenersBound) return
  listenersBound = true

  document.addEventListener('click', (event) => {
    const target = event.target
    if (!(target instanceof Element)) return

    const trigger = target.closest<HTMLElement>(COLLAPSE_TRIGGER_SELECTOR)
    if (!trigger?.closest('.navbar')) return
    if (!resolveNavTarget(trigger)) return

    event.preventDefault()
    toggleCollapse(trigger)
  })
}

const bindResizeListener = (): void => {
  if (resizeListenerBound) return
  resizeListenerBound = true

  window.addEventListener('resize', () => {
    syncAllTriggers()
  })
}

export const init = (): void => {
  syncAllTriggers()
  bindListeners()
  bindResizeListener()
}
