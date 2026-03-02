import { beforeEach, describe, expect, it } from 'vitest'
import { hideModal, init, showModal } from './index'

const setFixture = (): HTMLElement => {
  document.body.innerHTML = `
    <a id="open-modal" href="#dialog" data-am-toggle="modal">Open</a>
    <div id="dialog" class="modal hide fade" tabindex="-1" role="dialog" aria-hidden="true">
      <div class="modal-header">
        <button id="dismiss-button" type="button" data-dismiss="modal">Close</button>
      </div>
      <div class="modal-body">
        <p>Body</p>
      </div>
    </div>
  `
  const modal = document.getElementById('dialog')
  if (!(modal instanceof HTMLElement)) {
    throw new Error('Missing modal fixture')
  }
  return modal
}

describe('core modal feature', () => {
  beforeEach(() => {
    document.body.className = ''
    document.body.innerHTML = ''
    delete window.StorageServiceModal
  })

  it('shows and hides a modal with backdrop classes', () => {
    const modal = setFixture()

    showModal(modal)
    expect(modal.classList.contains('in')).toBe(true)
    expect(modal.classList.contains('hide')).toBe(false)
    expect(modal.style.display).toBe('block')
    expect(document.body.classList.contains('modal-open')).toBe(true)
    expect(document.querySelector('.modal-backdrop')).not.toBeNull()

    hideModal(modal)
    expect(modal.classList.contains('in')).toBe(false)
    expect(modal.classList.contains('hide')).toBe(true)
    expect(modal.style.display).toBe('none')
    expect(document.body.classList.contains('modal-open')).toBe(false)
    expect(document.querySelector('.modal-backdrop')).toBeNull()
  })

  it('closes modal when a data-dismiss trigger is clicked', () => {
    const modal = setFixture()
    init()
    showModal(modal)

    const dismiss = document.getElementById('dismiss-button') as HTMLButtonElement
    const clickEvent = new MouseEvent('click', { bubbles: true, cancelable: true })
    const notCanceled = dismiss.dispatchEvent(clickEvent)

    expect(notCanceled).toBe(false)
    expect(modal.classList.contains('in')).toBe(false)
    expect(modal.classList.contains('hide')).toBe(true)
  })

  it('opens modal through data-toggle trigger and closes on escape', () => {
    const modal = setFixture()
    init()

    const open = document.getElementById('open-modal') as HTMLAnchorElement
    open.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }))
    expect(modal.classList.contains('in')).toBe(true)

    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    expect(modal.classList.contains('in')).toBe(false)
  })

  it('exposes StorageServiceModal global API for imperative usage', () => {
    const modal = setFixture()
    init()

    window.StorageServiceModal?.show(modal)
    expect(modal.classList.contains('in')).toBe(true)

    window.StorageServiceModal?.hide(modal)
    expect(modal.classList.contains('in')).toBe(false)
  })
})
