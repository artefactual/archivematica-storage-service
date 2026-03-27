import { describe, expect, it, vi, beforeEach } from 'vitest'
import { defineComponent, h } from 'vue'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18nMock } from '@/shared/i18n'
import TreeView from '@/shared/components/TreeView.vue'
import App from './App.vue'

const mockBrowseSpaceDirectory = vi.fn()

vi.mock('@/shared/http', () => ({
  browseSpaceDirectory: (...args: unknown[]) => mockBrowseSpaceDirectory(...args),
}))

const TreeViewStub = defineComponent({
  name: 'TreeView',
  props: {
    items: {
      type: Array,
      default: () => [],
    },
    modelValue: {
      type: Object,
      default: undefined,
    },
    expanded: {
      type: Array,
      default: () => [],
    },
  },
  setup(props, { slots }) {
    return () => {
      const firstRoot = (props.items as Array<Record<string, unknown>>)[0]
      const firstChild = Array.isArray(firstRoot?.children)
        ? firstRoot.children[0] as Record<string, unknown> | undefined
        : undefined
      const actionNode = firstChild ?? firstRoot

      return h('div', { 'data-testid': 'tree-view' }, [
        JSON.stringify({
          items: props.items,
          selected: props.modelValue,
          expanded: props.expanded,
        }),
        ...(slots.actions?.({
          node: actionNode,
          actionProps: {},
        }) ?? []),
      ])
    }
  },
})

describe('LocationDirectoryPickerApp', () => {
  beforeEach(() => {
    mockBrowseSpaceDirectory.mockReset()
  })

  it('loads and renders root directories', async () => {
    mockBrowseSpaceDirectory.mockResolvedValueOnce({
      entries: ['Y2hpbGRfMQ==', 'Y2hpbGRfMg=='],
      directories: ['Y2hpbGRfMQ==', 'Y2hpbGRfMg=='],
    })

    const wrapper = mount(App, {
      props: {
        spaceUuid: '7d20c992-bc92-4f92-a794-7161ff2cc08b',
        rootPath: '/var/storage',
      },
      global: {
        plugins: [createI18nMock()],
        stubs: {
          TreeView: TreeViewStub,
        },
      },
    })

    await flushPromises()

    expect(mockBrowseSpaceDirectory).toHaveBeenCalledWith(
      '7d20c992-bc92-4f92-a794-7161ff2cc08b',
      '/var/storage',
      undefined,
    )
    expect(wrapper.text()).toContain('child_1')
    expect(wrapper.text()).toContain('child_2')
  })

  it('loads and labels object storage roots when root path is empty', async () => {
    mockBrowseSpaceDirectory.mockResolvedValueOnce({
      entries: ['dHJhbnNmZXJz'],
      directories: ['dHJhbnNmZXJz'],
    })

    const wrapper = mount(App, {
      props: {
        spaceUuid: '7d20c992-bc92-4f92-a794-7161ff2cc08b',
        rootPath: '',
      },
      global: {
        plugins: [createI18nMock()],
        stubs: {
          TreeView: TreeViewStub,
        },
      },
    })

    await flushPromises()

    const tree = wrapper.findComponent(TreeViewStub)

    expect(mockBrowseSpaceDirectory).toHaveBeenCalledWith(
      '7d20c992-bc92-4f92-a794-7161ff2cc08b',
      '',
      undefined,
    )
    expect(tree.props('expanded')).toEqual([])
    expect(wrapper.text()).toContain('Space root')
    expect(wrapper.text()).toContain('transfers')
  })

  it('reveals empty-root children after expanding the synthetic root', async () => {
    mockBrowseSpaceDirectory.mockResolvedValueOnce({
      entries: ['c3BhY2Utcm9vdA=='],
      directories: ['c3BhY2Utcm9vdA=='],
    })

    const wrapper = mount(App, {
      props: {
        spaceUuid: '7d20c992-bc92-4f92-a794-7161ff2cc08b',
        rootPath: '',
      },
      global: {
        plugins: [createI18nMock()],
      },
    })

    await flushPromises()

    const tree = wrapper.findComponent(TreeView)
    const [rootNode] = tree.props('items') as Array<Record<string, unknown>>

    expect(wrapper.findAll('.tree-node-label').map(node => node.text())).toEqual(['Space root'])
    expect(rootNode?.id).toBe('root:')

    const rootTreeNode = wrapper.findComponent({ name: 'TreeNode' })
    rootTreeNode.vm.$emit('toggle', rootNode)
    await flushPromises()

    expect(wrapper.findAll('.tree-node-label').map(node => node.text())).toEqual([
      'Space root',
      'space-root',
    ])
    expect((tree.props('expanded') as string[])).toContain('root:')
    expect(mockBrowseSpaceDirectory).toHaveBeenCalledTimes(1)
  })

  it('keeps filesystem root labels for non-empty root paths', async () => {
    mockBrowseSpaceDirectory.mockResolvedValueOnce({
      entries: ['Y2hpbGRfMQ=='],
      directories: ['Y2hpbGRfMQ=='],
    })

    const wrapper = mount(App, {
      props: {
        spaceUuid: '7d20c992-bc92-4f92-a794-7161ff2cc08b',
        rootPath: '/',
      },
      global: {
        plugins: [createI18nMock()],
        stubs: {
          TreeView: TreeViewStub,
        },
      },
    })

    await flushPromises()

    expect(wrapper.text()).toContain('"label":"/"')
    expect(wrapper.text()).not.toContain('Space root')
  })

  it('loads children when a directory is toggled', async () => {
    mockBrowseSpaceDirectory
      .mockResolvedValueOnce({
        entries: ['Y2hpbGRfMQ=='],
        directories: ['Y2hpbGRfMQ=='],
      })
      .mockResolvedValueOnce({
        entries: ['bmVzdGVk'],
        directories: ['bmVzdGVk'],
      })

    const wrapper = mount(App, {
      props: {
        spaceUuid: '7d20c992-bc92-4f92-a794-7161ff2cc08b',
        rootPath: '/var/storage',
      },
      global: {
        plugins: [createI18nMock()],
        stubs: {
          TreeView: TreeViewStub,
        },
      },
    })

    await flushPromises()

    const tree = wrapper.findComponent(TreeViewStub)
    tree.vm.$emit('toggle', {
      id: 'path:/var/storage/child_1',
      path: '/var/storage/child_1',
      label: 'child_1',
      children: [],
      loaded: false,
      loading: false,
    })

    await flushPromises()

    expect(mockBrowseSpaceDirectory).toHaveBeenNthCalledWith(
      2,
      '7d20c992-bc92-4f92-a794-7161ff2cc08b',
      '/var/storage/child_1',
      undefined,
    )
  })

  it('emits selected directory path', async () => {
    mockBrowseSpaceDirectory.mockResolvedValueOnce({
      entries: ['Y2hpbGRfMQ=='],
      directories: ['Y2hpbGRfMQ=='],
    })

    const wrapper = mount(App, {
      props: {
        spaceUuid: '7d20c992-bc92-4f92-a794-7161ff2cc08b',
        rootPath: '/var/storage',
        selectedPath: '/var/storage/child_1',
      },
      global: {
        plugins: [createI18nMock()],
        stubs: {
          TreeView: TreeViewStub,
        },
      },
    })

    await flushPromises()

    const selectButton = wrapper.find('button.picker-select-action')
    await selectButton.trigger('click')

    expect(wrapper.emitted('update:selectedPath')?.[0]?.[0]).toBe('/var/storage/child_1')
    expect(wrapper.emitted('select')?.[0]?.[0]).toBe('/var/storage/child_1')
  })

  it('does not emit selection when browsing focus changes only', async () => {
    mockBrowseSpaceDirectory.mockResolvedValueOnce({
      entries: ['Y2hpbGRfMQ=='],
      directories: ['Y2hpbGRfMQ=='],
    })

    const wrapper = mount(App, {
      props: {
        spaceUuid: '7d20c992-bc92-4f92-a794-7161ff2cc08b',
        rootPath: '/var/storage',
      },
      global: {
        plugins: [createI18nMock()],
        stubs: {
          TreeView: TreeViewStub,
        },
      },
    })

    await flushPromises()

    const tree = wrapper.findComponent(TreeViewStub)
    tree.vm.$emit('update:modelValue', {
      id: 'path:/var/storage/child_1',
      path: '/var/storage/child_1',
      label: 'child_1',
      children: [],
      loaded: false,
      loading: false,
    })
    await flushPromises()

    expect(wrapper.emitted('update:selectedPath')).toBeUndefined()
    expect(wrapper.emitted('select')).toBeUndefined()
  })
})
