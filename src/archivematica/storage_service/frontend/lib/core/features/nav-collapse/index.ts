const TRIGGER_SELECTOR = '[data-am-toggle="collapse"]'
const OPEN_CLASS = 'in'

let listenersBound = false

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

const setExpanded = (trigger: HTMLElement, isExpanded: boolean): void => {
  trigger.setAttribute('aria-expanded', String(isExpanded))
}

const applyExpandedState = (target: HTMLElement, isExpanded: boolean): void => {
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
  const target = resolveTarget(trigger)
  if (!target) return

  const isExpanded = target.classList.contains(OPEN_CLASS)
  setExpanded(trigger, isExpanded)
  applyExpandedState(target, isExpanded)
}

const syncAllTriggers = (): void => {
  for (const trigger of document.querySelectorAll<HTMLElement>(TRIGGER_SELECTOR)) {
    syncTriggerState(trigger)
  }
}

const toggleCollapse = (trigger: HTMLElement): void => {
  const target = resolveTarget(trigger)
  if (!target) return

  const isExpanded = target.classList.contains(OPEN_CLASS)
  applyExpandedState(target, !isExpanded)
  setExpanded(trigger, !isExpanded)
}

const bindListeners = (): void => {
  if (listenersBound) return
  listenersBound = true

  document.addEventListener('click', (event) => {
    const target = event.target
    if (!(target instanceof Element)) return

    const trigger = target.closest<HTMLElement>(TRIGGER_SELECTOR)
    if (!trigger) return

    event.preventDefault()
    toggleCollapse(trigger)
  })
}

export const init = (): void => {
  syncAllTriggers()
  bindListeners()
}
