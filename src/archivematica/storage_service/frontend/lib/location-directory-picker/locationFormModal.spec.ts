import { beforeEach, describe, expect, it, vi } from 'vitest'
import { initLocationFormModal } from './locationFormModal'

const setFixture = (): {
  input: HTMLInputElement
  mount: HTMLElement
  modal: HTMLElement
} => {
  document.body.innerHTML = `
    <input id="id_relative_path" value="" />
    <div
      id="location-directory-picker"
      data-browse-label="Browse"
      data-space-uuid="space-uuid"
      data-root-path="/a"
      data-selected-relative-path=""
    ></div>
    <div id="directory-select-modal" class="modal hide" aria-hidden="true">
      <button type="button" data-dismiss="modal">Close</button>
    </div>
  `

  const input = document.getElementById('id_relative_path')
  const mount = document.getElementById('location-directory-picker')
  const modal = document.getElementById('directory-select-modal')
  if (
    !(input instanceof HTMLInputElement)
    || !(mount instanceof HTMLElement)
    || !(modal instanceof HTMLElement)
  ) {
    throw new Error('Missing location form fixture')
  }

  return { input, mount, modal }
}

const setTextareaFixture = (): {
  textarea: HTMLTextAreaElement
  mount: HTMLElement
  modal: HTMLElement
} => {
  document.body.innerHTML = `
    <textarea id="id_relative_path"></textarea>
    <div
      id="location-directory-picker"
      data-browse-label="Browse"
      data-space-uuid="space-uuid"
      data-root-path="/a"
      data-selected-relative-path=""
    ></div>
    <div id="directory-select-modal" class="modal hide" aria-hidden="true">
      <button type="button" data-dismiss="modal">Close</button>
    </div>
  `

  const textarea = document.getElementById('id_relative_path')
  const mount = document.getElementById('location-directory-picker')
  const modal = document.getElementById('directory-select-modal')
  if (
    !(textarea instanceof HTMLTextAreaElement)
    || !(mount instanceof HTMLElement)
    || !(modal instanceof HTMLElement)
  ) {
    throw new Error('Missing location form textarea fixture')
  }

  return { textarea, mount, modal }
}

describe('locationFormModal integration', () => {
  beforeEach(() => {
    vi.useRealTimers()
    document.body.className = ''
    document.body.innerHTML = ''
    delete window.StorageServiceModal
  })

  it('uses StorageServiceModal when it becomes available during bounded wait', async () => {
    const { modal } = setFixture()
    const show = vi.fn<(target: HTMLElement, opener?: HTMLElement | null) => void>()
    const hide = vi.fn<(target: HTMLElement, options?: Readonly<{ restoreFocus?: boolean }>) => void>()
    const toggle = vi.fn<(target: HTMLElement, opener?: HTMLElement | null) => void>()

    initLocationFormModal()

    const browse = document.getElementById('id_relative_path_browse')
    if (!(browse instanceof HTMLInputElement)) {
      throw new Error('Missing browse button')
    }

    vi.useFakeTimers()
    browse.click()

    window.setTimeout(() => {
      window.StorageServiceModal = { show, hide, toggle }
    }, 25)

    await vi.advanceTimersByTimeAsync(50)

    expect(show).toHaveBeenCalledTimes(1)
    expect(show).toHaveBeenCalledWith(modal, browse)
  })

  it('uses declarative trigger attributes when API is already available', () => {
    const { modal } = setFixture()
    const show = vi.fn<(target: HTMLElement, opener?: HTMLElement | null) => void>()
    const hide = vi.fn<(target: HTMLElement, options?: Readonly<{ restoreFocus?: boolean }>) => void>()
    const toggle = vi.fn<(target: HTMLElement, opener?: HTMLElement | null) => void>()
    window.StorageServiceModal = { show, hide, toggle }

    initLocationFormModal()

    const browse = document.getElementById('id_relative_path_browse')
    if (!(browse instanceof HTMLInputElement)) {
      throw new Error('Missing browse button')
    }

    expect(browse.getAttribute('data-am-modal-target')).toBe('#directory-select-modal')

    browse.click()

    // In this path opening is declarative, so this helper should not call show directly.
    expect(show).not.toHaveBeenCalled()
    expect(modal.classList.contains('in')).toBe(false)
  })

  it('falls back to direct modal show when API never initializes', async () => {
    const { modal } = setFixture()
    initLocationFormModal()

    const browse = document.getElementById('id_relative_path_browse')
    if (!(browse instanceof HTMLInputElement)) {
      throw new Error('Missing browse button')
    }

    vi.useFakeTimers()
    browse.click()

    await vi.advanceTimersByTimeAsync(400)

    expect(modal.classList.contains('in')).toBe(true)
    expect(modal.classList.contains('hide')).toBe(false)
    expect(modal.style.display).toBe('block')
    expect(modal.getAttribute('aria-hidden')).toBe('false')
    expect(modal.getAttribute('data-am-location-form-owns-backdrop')).toBe('true')
    expect(document.body.classList.contains('modal-open')).toBe(true)
    expect(document.querySelector('.modal-backdrop')).not.toBeNull()
  })

  it('uses direct fallback hide on selected path when API is unavailable', async () => {
    const { input, mount, modal } = setFixture()
    initLocationFormModal()

    const browse = document.getElementById('id_relative_path_browse')
    if (!(browse instanceof HTMLInputElement)) {
      throw new Error('Missing browse button')
    }

    vi.useFakeTimers()
    browse.click()
    await vi.advanceTimersByTimeAsync(400)

    mount.dispatchEvent(new CustomEvent('location-directory-picker:selected-path', {
      detail: { relativePath: 'AIPs/example' },
      bubbles: true,
    }))

    expect(input.value).toBe('AIPs/example')
    expect(modal.classList.contains('in')).toBe(false)
    expect(modal.classList.contains('hide')).toBe(true)
    expect(modal.style.display).toBe('none')
    expect(modal.getAttribute('aria-hidden')).toBe('true')
    expect(document.body.classList.contains('modal-open')).toBe(false)
    expect(document.querySelector('.modal-backdrop')).toBeNull()
  })

  it('keeps fallback cleanup path if API appears after fallback open', async () => {
    const { mount, modal } = setFixture()
    const show = vi.fn<(target: HTMLElement, opener?: HTMLElement | null) => void>()
    const hide = vi.fn<(target: HTMLElement, options?: Readonly<{ restoreFocus?: boolean }>) => void>()
    const toggle = vi.fn<(target: HTMLElement, opener?: HTMLElement | null) => void>()

    initLocationFormModal()

    const browse = document.getElementById('id_relative_path_browse')
    if (!(browse instanceof HTMLInputElement)) {
      throw new Error('Missing browse button')
    }

    vi.useFakeTimers()
    browse.click()
    await vi.advanceTimersByTimeAsync(400)

    window.StorageServiceModal = { show, hide, toggle }

    mount.dispatchEvent(new CustomEvent('location-directory-picker:selected-path', {
      detail: { relativePath: 'AIPs/example' },
      bubbles: true,
    }))

    expect(modal.classList.contains('in')).toBe(false)
    expect(modal.classList.contains('hide')).toBe(true)
    expect(document.body.classList.contains('modal-open')).toBe(false)
    expect(document.querySelector('.modal-backdrop')).toBeNull()
    expect(hide).not.toHaveBeenCalled()
  })

  it('handles data-dismiss clicks via fallback when API is unavailable', async () => {
    const { modal } = setFixture()
    initLocationFormModal()

    const browse = document.getElementById('id_relative_path_browse')
    const dismiss = modal.querySelector('[data-dismiss="modal"]')
    if (!(browse instanceof HTMLInputElement) || !(dismiss instanceof HTMLButtonElement)) {
      throw new Error('Missing dismiss fixture')
    }

    vi.useFakeTimers()
    browse.click()
    await vi.advanceTimersByTimeAsync(400)

    dismiss.click()

    expect(modal.classList.contains('in')).toBe(false)
    expect(modal.classList.contains('hide')).toBe(true)
    expect(modal.style.display).toBe('none')
    expect(document.body.classList.contains('modal-open')).toBe(false)
    expect(document.querySelector('.modal-backdrop')).toBeNull()
  })

  it('does not remove shared backdrop or modal-open in ownsBackdrop=false fallback path', async () => {
    const { modal } = setFixture()
    const sharedBackdrop = document.createElement('div')
    sharedBackdrop.className = 'modal-backdrop fade in'
    document.body.append(sharedBackdrop)
    document.body.classList.add('modal-open')

    initLocationFormModal()

    const browse = document.getElementById('id_relative_path_browse')
    if (!(browse instanceof HTMLInputElement)) {
      throw new Error('Missing browse button')
    }

    vi.useFakeTimers()
    browse.click()
    await vi.advanceTimersByTimeAsync(400)

    expect(modal.getAttribute('data-am-location-form-owns-backdrop')).toBe('false')

    const dismiss = modal.querySelector('[data-dismiss="modal"]')
    if (!(dismiss instanceof HTMLButtonElement)) {
      throw new Error('Missing dismiss fixture')
    }

    dismiss.click()

    expect(document.querySelector('.modal-backdrop')).toBe(sharedBackdrop)
    expect(document.body.classList.contains('modal-open')).toBe(true)
    expect(modal.getAttribute('data-am-location-form-owns-backdrop')).toBeNull()
  })

  it('removes owned fallback backdrop and modal-open on close', async () => {
    const { modal } = setFixture()
    initLocationFormModal()

    const browse = document.getElementById('id_relative_path_browse')
    if (!(browse instanceof HTMLInputElement)) {
      throw new Error('Missing browse button')
    }

    vi.useFakeTimers()
    browse.click()
    await vi.advanceTimersByTimeAsync(400)

    expect(modal.getAttribute('data-am-location-form-owns-backdrop')).toBe('true')
    expect(document.querySelector('.modal-backdrop')).not.toBeNull()
    expect(document.body.classList.contains('modal-open')).toBe(true)

    const dismiss = modal.querySelector('[data-dismiss="modal"]')
    if (!(dismiss instanceof HTMLButtonElement)) {
      throw new Error('Missing dismiss fixture')
    }

    dismiss.click()

    expect(document.querySelector('.modal-backdrop')).toBeNull()
    expect(document.body.classList.contains('modal-open')).toBe(false)
    expect(modal.getAttribute('data-am-location-form-owns-backdrop')).toBeNull()
  })

  it('initializes browse button and updates textarea relative path fields', () => {
    const { textarea, mount } = setTextareaFixture()
    initLocationFormModal()

    const browse = document.getElementById('id_relative_path_browse')
    if (!(browse instanceof HTMLInputElement)) {
      throw new Error('Missing browse button for textarea field')
    }

    mount.dispatchEvent(new CustomEvent('location-directory-picker:selected-path', {
      detail: { relativePath: 'AIPs/from-textarea' },
      bubbles: true,
    }))

    expect(textarea.value).toBe('AIPs/from-textarea')
  })
})
