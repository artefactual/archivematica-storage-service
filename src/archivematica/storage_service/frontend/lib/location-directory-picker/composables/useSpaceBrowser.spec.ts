import { describe, expect, it } from 'vitest'
import type { Base64String } from '@/shared/encoding/base64'
import {
  decodeBrowseResponse,
  joinPath,
  mapBrowseResponseToDirectoryNodes,
  toTreeKey,
} from '@/location-directory-picker/composables/useSpaceBrowser'

describe('useSpaceBrowser helpers', () => {
  it('decodes base64 browse payload entries and directories', () => {
    const decoded = decodeBrowseResponse({
      entries: ['Y2hpbGRfMQ==', 'ZmlsZS50eHQ='] as Base64String[],
      directories: ['Y2hpbGRfMQ=='] as Base64String[],
    })

    expect(decoded.entries).toEqual(['child_1', 'file.txt'])
    expect(decoded.directories).toEqual(['child_1'])
  })

  it('joins path segments safely', () => {
    expect(joinPath('/var/storage', 'child_1')).toBe('/var/storage/child_1')
    expect(joinPath('/var/storage/', 'child_1')).toBe('/var/storage/child_1')
    expect(joinPath('', 'child_1')).toBe('child_1')
  })

  it('maps only directories into tree nodes', () => {
    const nodes = mapBrowseResponseToDirectoryNodes(
      {
        entries: ['child_1', 'file.txt', 'child_2'],
        directories: ['child_1', 'child_2'],
      },
      '/var/storage',
    )

    expect(nodes).toEqual([
      {
        id: 'path:/var/storage/child_1',
        label: 'child_1',
        path: '/var/storage/child_1',
        children: [],
        loaded: false,
        loading: false,
        loadError: null,
      },
      {
        id: 'path:/var/storage/child_2',
        label: 'child_2',
        path: '/var/storage/child_2',
        children: [],
        loaded: false,
        loading: false,
        loadError: null,
      },
    ])
  })

  it('namespaces tree keys for roots and paths separately', () => {
    expect(toTreeKey('', true)).toBe('root:')
    expect(toTreeKey('space-root')).toBe('path:space-root')
    expect(toTreeKey('/')).toBe('path:/')
    expect(toTreeKey('/', true)).toBe('root:/')
  })
})
