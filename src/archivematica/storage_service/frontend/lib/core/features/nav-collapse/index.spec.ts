import { beforeEach, describe, expect, it } from 'vitest'
import { init } from './index'

const setFixture = (): { trigger: HTMLElement, target: HTMLElement } => {
  document.body.innerHTML = `
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
  })

  it('toggles collapse target classes and aria state', () => {
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

  it('supports href target selectors', () => {
    document.body.innerHTML = `
      <a id="menu-trigger" href="#main-navigation" data-am-toggle="collapse">Menu</a>
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
