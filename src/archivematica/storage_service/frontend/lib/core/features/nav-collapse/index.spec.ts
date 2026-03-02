import { beforeEach, describe, expect, it } from 'vitest'
import { init } from './index'

let mobileViewport = false

const setMobileViewport = (enabled: boolean): void => {
  mobileViewport = enabled
}

const installMatchMedia = (): void => {
  Object.defineProperty(window, 'matchMedia', {
    configurable: true,
    writable: true,
    value: (query: string): MediaQueryList => ({
      matches: query === '(max-width: 979px)' ? mobileViewport : false,
      media: query,
      onchange: null,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      addListener: () => undefined,
      removeListener: () => undefined,
      dispatchEvent: () => false,
    }),
  })
}

const setFixture = (): { trigger: HTMLElement, target: HTMLElement } => {
  document.body.innerHTML = `
    <div class="navbar">
      <button
        id="menu-trigger"
        type="button"
        data-am-toggle="collapse"
        data-am-target="#main-navigation"
        aria-controls="main-navigation"
        aria-expanded="false"
      >
        Menu
      </button>
    </div>
    <div id="main-navigation" class="nav-collapse collapse" aria-hidden="true"></div>
  `

  const trigger = document.getElementById('menu-trigger')
  const target = document.getElementById('main-navigation')
  if (!(trigger instanceof HTMLElement) || !(target instanceof HTMLElement)) {
    throw new Error('Missing collapse fixture')
  }

  return { trigger, target }
}

describe('core nav-collapse feature', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
    setMobileViewport(false)
    installMatchMedia()
  })

  it('keeps navigation expanded and accessible in desktop mode', () => {
    const { trigger, target } = setFixture()
    init()

    expect(trigger.getAttribute('aria-expanded')).toBe('true')
    expect(target.getAttribute('aria-hidden')).toBeNull()
    expect(target.classList.contains('in')).toBe(false)
    expect(target.style.height).toBe('')
    expect(target.style.overflow).toBe('')

    trigger.click()

    expect(trigger.getAttribute('aria-expanded')).toBe('true')
    expect(target.getAttribute('aria-hidden')).toBeNull()
    expect(target.classList.contains('in')).toBe(false)
    expect(target.style.height).toBe('')
    expect(target.style.overflow).toBe('')
  })

  it('toggles collapse target classes and aria state in mobile mode', () => {
    setMobileViewport(true)
    const { trigger, target } = setFixture()
    init()

    expect(trigger.getAttribute('aria-expanded')).toBe('false')
    expect(target.getAttribute('aria-hidden')).toBe('true')
    expect(target.classList.contains('in')).toBe(false)
    expect(target.style.height).toBe('0px')
    expect(target.style.overflow).toBe('hidden')

    trigger.click()

    expect(trigger.getAttribute('aria-expanded')).toBe('true')
    expect(target.getAttribute('aria-hidden')).toBe('false')
    expect(target.classList.contains('in')).toBe(true)
    expect(target.style.height).toBe('auto')
    expect(target.style.overflow).toBe('visible')

    trigger.click()

    expect(trigger.getAttribute('aria-expanded')).toBe('false')
    expect(target.getAttribute('aria-hidden')).toBe('true')
    expect(target.classList.contains('in')).toBe(false)
    expect(target.style.height).toBe('0px')
    expect(target.style.overflow).toBe('hidden')
  })

  it('re-syncs collapse state on viewport resize', () => {
    setMobileViewport(true)
    const { trigger, target } = setFixture()
    init()

    trigger.click()
    expect(target.classList.contains('in')).toBe(true)
    expect(target.getAttribute('aria-hidden')).toBe('false')

    setMobileViewport(false)
    window.dispatchEvent(new Event('resize'))

    expect(trigger.getAttribute('aria-expanded')).toBe('true')
    expect(target.getAttribute('aria-hidden')).toBeNull()
    expect(target.classList.contains('in')).toBe(false)
    expect(target.style.height).toBe('')
    expect(target.style.overflow).toBe('')

    setMobileViewport(true)
    window.dispatchEvent(new Event('resize'))

    expect(trigger.getAttribute('aria-expanded')).toBe('false')
    expect(target.getAttribute('aria-hidden')).toBe('true')
    expect(target.classList.contains('in')).toBe(false)
    expect(target.style.height).toBe('0px')
    expect(target.style.overflow).toBe('hidden')
  })

  it('ignores non-nav collapse triggers outside navbar', () => {
    setMobileViewport(true)
    document.body.innerHTML = `
      <a id="other-trigger" href="#other-target" data-am-toggle="collapse">Toggle</a>
      <div id="other-target" class="collapse"></div>
    `
    init()

    const trigger = document.getElementById('other-trigger')
    const target = document.getElementById('other-target')
    if (!(trigger instanceof HTMLElement) || !(target instanceof HTMLElement)) {
      throw new Error('Missing non-nav collapse fixture')
    }

    const clickEvent = new MouseEvent('click', { bubbles: true, cancelable: true })
    const notCanceled = trigger.dispatchEvent(clickEvent)

    expect(notCanceled).toBe(true)
    expect(target.classList.contains('in')).toBe(false)
    expect(target.getAttribute('aria-hidden')).toBeNull()
  })

  it('ignores navbar collapse triggers that do not target nav-collapse', () => {
    setMobileViewport(true)
    document.body.innerHTML = `
      <div class="navbar">
        <a id="menu-trigger" href="#other-target" data-am-toggle="collapse">Menu</a>
      </div>
      <div id="other-target" class="collapse"></div>
    `
    init()

    const trigger = document.getElementById('menu-trigger')
    const target = document.getElementById('other-target')
    if (!(trigger instanceof HTMLElement) || !(target instanceof HTMLElement)) {
      throw new Error('Missing malformed nav collapse fixture')
    }

    const clickEvent = new MouseEvent('click', { bubbles: true, cancelable: true })
    const notCanceled = trigger.dispatchEvent(clickEvent)

    expect(notCanceled).toBe(true)
    expect(target.classList.contains('in')).toBe(false)
    expect(target.getAttribute('aria-hidden')).toBeNull()
  })

  it('supports href target selectors in mobile mode', () => {
    setMobileViewport(true)
    document.body.innerHTML = `
      <div class="navbar">
        <a id="menu-trigger" href="#main-navigation" data-am-toggle="collapse">Menu</a>
      </div>
      <div id="main-navigation" class="nav-collapse collapse"></div>
    `
    init()

    const trigger = document.getElementById('menu-trigger')
    const target = document.getElementById('main-navigation')
    if (!(trigger instanceof HTMLElement) || !(target instanceof HTMLElement)) {
      throw new Error('Missing collapse fixture')
    }

    trigger.click()
    expect(target.classList.contains('in')).toBe(true)
    expect(trigger.getAttribute('aria-expanded')).toBe('true')
  })
})
