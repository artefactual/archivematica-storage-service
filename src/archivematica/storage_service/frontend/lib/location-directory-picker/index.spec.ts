import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'

const { initI18nMock } = vi.hoisted(() => ({
  initI18nMock: vi.fn(),
}))

vi.mock('@/shared/i18n', () => ({
  i18n: {
    install: () => undefined,
  },
  initI18n: initI18nMock,
}))

vi.mock('./App.vue', () => ({
  default: defineComponent({
    name: 'AppStub',
    props: {
      selectedPath: {
        type: String,
        default: '',
      },
    },
    emits: ['select'],
    setup(props, { emit }) {
      return () => h('div', [
        h('div', { 'data-testid': 'selected-path' }, props.selectedPath),
        h('button', {
          'data-testid': 'emit-select',
          'type': 'button',
          'onClick': () => emit('select', '/var/storage/home/selected'),
        }),
        h('button', {
          'data-testid': 'emit-current-select',
          'type': 'button',
          'onClick': () => emit('select', props.selectedPath),
        }),
      ])
    },
  }),
}))

describe('location-directory-picker bootstrap', () => {
  beforeEach(() => {
    vi.resetModules()
    vi.clearAllMocks()
    initI18nMock.mockResolvedValue(undefined)

    document.body.innerHTML = `
      <div
        id="location-directory-picker"
        data-space-uuid="2e008d73-33d0-4aa6-917b-9fd6f4031915"
        data-root-path="/var/storage"
        data-selected-relative-path="home/old"
      ></div>
    `
  })

  afterEach(() => {
    document.body.innerHTML = ''
  })

  const getMountEl = () => {
    const mountEl = document.getElementById('location-directory-picker')
    if (!mountEl) {
      throw new Error('Mount element not found in test DOM.')
    }
    return mountEl
  }

  const getSelectedPathText = (mountEl: HTMLElement) => {
    return mountEl.querySelector('[data-testid="selected-path"]')?.textContent
  }

  const triggerSelect = (mountEl: HTMLElement) => {
    const button = mountEl.querySelector<HTMLButtonElement>('[data-testid="emit-select"]')
    if (!button) {
      throw new Error('Select button not found in test DOM.')
    }
    button.click()
  }

  const triggerCurrentSelect = (mountEl: HTMLElement) => {
    const button = mountEl.querySelector<HTMLButtonElement>('[data-testid="emit-current-select"]')
    if (!button) {
      throw new Error('Current select button not found in test DOM.')
    }
    button.click()
  }

  it('dispatches selected-path once per directory selection', async () => {
    await import('./index')
    await Promise.resolve()
    await Promise.resolve()

    const mountEl = getMountEl()
    let selectedPathEventCount = 0
    mountEl.addEventListener('location-directory-picker:selected-path', () => {
      selectedPathEventCount += 1
    })

    triggerSelect(mountEl)
    await Promise.resolve()
    await Promise.resolve()

    expect(selectedPathEventCount).toBe(1)
  })

  it('updates selected path when mount attributes change after bootstrap', async () => {
    await import('./index')
    await Promise.resolve()
    await Promise.resolve()

    const mountEl = getMountEl()
    expect(getSelectedPathText(mountEl)).toBe('/var/storage/home/old')

    mountEl.setAttribute('data-selected-relative-path', 'home/new')
    await Promise.resolve()
    await Promise.resolve()

    expect(getSelectedPathText(mountEl)).toBe('/var/storage/home/new')
  })

  it('keeps selected paths relative for object storage roots', async () => {
    document.body.innerHTML = `
      <div
        id="location-directory-picker"
        data-space-uuid="2e008d73-33d0-4aa6-917b-9fd6f4031915"
        data-root-path=""
        data-selected-relative-path="/transfers/foo"
      ></div>
    `

    await import('./index')
    await Promise.resolve()
    await Promise.resolve()

    const mountEl = getMountEl()
    expect(getSelectedPathText(mountEl)).toBe('transfers/foo')

    triggerCurrentSelect(mountEl)
    await Promise.resolve()
    await Promise.resolve()

    expect(mountEl.getAttribute('data-selected-relative-path')).toBe('transfers/foo')
  })

  it('uses latest manual relative path after a prior selection', async () => {
    await import('./index')
    await Promise.resolve()
    await Promise.resolve()

    const mountEl = getMountEl()

    triggerSelect(mountEl)
    await Promise.resolve()
    await Promise.resolve()
    expect(getSelectedPathText(mountEl)).toBe('/var/storage/home/selected')

    mountEl.setAttribute('data-selected-relative-path', 'home/manual')
    await Promise.resolve()
    await Promise.resolve()

    expect(getSelectedPathText(mountEl)).toBe('/var/storage/home/manual')
  })
})
