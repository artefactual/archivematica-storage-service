import { computed, ref, type Ref } from 'vue'
import { decodeBase64 } from '@/shared/encoding/base64'
import type { Base64String } from '@/shared/encoding/base64'
import { HttpError, browseSpaceDirectory, type SpaceBrowseResponse } from '@/shared/http'
import type { DecodedBrowseResponse, DirectoryNode } from '@/location-directory-picker/types'

const joinPath = (basePath: string, entryName: string) => {
  if (!basePath) {
    return entryName
  }
  return `${basePath.replace(/\/$/, '')}/${entryName}`
}

const normalizeErrorMessage = (error: unknown): string => {
  if (error instanceof HttpError) {
    const message = error.bodyText?.trim()
    if (message) {
      return message
    }
  }
  if (error instanceof Error && error.message) {
    return error.message
  }
  return 'Failed to browse space directory.'
}

const decodeBrowseResponse = (response: SpaceBrowseResponse): DecodedBrowseResponse => {
  const entries = Array.isArray(response.entries)
    ? response.entries.map(entry => decodeBase64(entry as Base64String))
    : []
  const directories = Array.isArray(response.directories)
    ? response.directories.map(entry => decodeBase64(entry as Base64String))
    : []

  return {
    entries,
    directories,
  }
}

const toTreeKey = (path: string, isRoot = false): string => {
  return `${isRoot ? 'root' : 'path'}:${path}`
}

const mapBrowseResponseToDirectoryNodes = (
  response: DecodedBrowseResponse,
  currentPath: string,
): DirectoryNode[] => {
  const directories = new Set(response.directories)

  return response.entries
    .filter(entry => directories.has(entry))
    .map((entry) => {
      const path = joinPath(currentPath, entry)
      return {
        id: toTreeKey(path),
        label: entry,
        path,
        children: [],
        loaded: false,
        loading: false,
        loadError: null,
      } satisfies DirectoryNode
    })
}

const getRootLabel = (path: string, spaceRootLabel: string): string => {
  if (path === '') {
    return spaceRootLabel
  }

  return path.split('/').filter(Boolean).pop() ?? path
}

const createRootNode = (path: string, spaceRootLabel: string): DirectoryNode => ({
  id: toTreeKey(path, true),
  label: getRootLabel(path, spaceRootLabel),
  path,
  children: [],
  loaded: false,
  loading: false,
  loadError: null,
})

export function useSpaceBrowser(spaceRootLabel: string) {
  const items: Ref<DirectoryNode[]> = ref([])
  const loading: Ref<boolean> = ref(false)
  const error: Ref<string | null> = ref(null)

  const loadChildren = async (spaceUuid: string, path: string, signal?: AbortSignal) => {
    const response = await browseSpaceDirectory(spaceUuid, path, signal ? { signal } : undefined)
    const decoded = decodeBrowseResponse(response)
    return mapBrowseResponseToDirectoryNodes(decoded, path)
  }

  const loadRoot = async (spaceUuid: string, rootPath: string, signal?: AbortSignal) => {
    items.value = []
    error.value = null

    if (!spaceUuid) {
      error.value = 'A valid space UUID is required.'
      return
    }

    loading.value = true

    const root = createRootNode(rootPath, spaceRootLabel)
    root.loading = true
    items.value = [root]

    try {
      root.children = await loadChildren(spaceUuid, root.path, signal)
      root.loaded = true
      root.loadError = null
    } catch (err) {
      const message = normalizeErrorMessage(err)
      root.loaded = false
      root.children = []
      root.loadError = message
      error.value = message
    } finally {
      root.loading = false
      loading.value = false
      // Reassign to ensure reactive updates after nested mutations.
      items.value = [...items.value]
    }
  }

  const expandNode = async (spaceUuid: string, node: DirectoryNode, signal?: AbortSignal) => {
    if (node.loading || node.loaded) {
      return
    }

    node.loading = true
    node.loadError = null

    try {
      node.children = await loadChildren(spaceUuid, node.path, signal)
      node.loaded = true
    } catch (err) {
      node.children = []
      node.loaded = false
      node.loadError = normalizeErrorMessage(err)
    } finally {
      node.loading = false
      items.value = [...items.value]
    }
  }

  return {
    items,
    loading: computed(() => loading.value),
    error: computed(() => error.value),
    loadRoot,
    expandNode,
    clearError: () => {
      error.value = null
    },
  }
}

export {
  decodeBrowseResponse,
  mapBrowseResponseToDirectoryNodes,
  joinPath,
  toTreeKey,
}
