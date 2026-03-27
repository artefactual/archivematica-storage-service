<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { TreeView } from '@/shared/components'
import type { DirectoryNode } from '@/location-directory-picker/types'
import { useSpaceBrowser } from '@/location-directory-picker/composables/useSpaceBrowser'

const props = defineProps<{
  spaceUuid: string
  rootPath: string
  selectedPath?: string
}>()

const emit = defineEmits<{
  'select': [path: string]
  'update:selectedPath': [path: string]
}>()

const selectedNode = ref<DirectoryNode | undefined>()
const committedSelectedPath = ref(props.selectedPath ?? '')
const expandedPaths = ref<string[]>([])
const { t } = useI18n()
const { items, loading, error, loadRoot, expandNode, clearError } = useSpaceBrowser(
  t('locationDirectoryPicker.spaceRoot'),
)

const refresh = async () => {
  await loadRoot(props.spaceUuid, props.rootPath)

  if (props.selectedPath) {
    const node = findNodeByPath(items.value, props.selectedPath)
    if (node) {
      selectedNode.value = node
    }
  }
}

const handleToggle = async (node: DirectoryNode) => {
  const key = node.id
  const index = expandedPaths.value.indexOf(key)
  if (index === -1) {
    expandedPaths.value = [...expandedPaths.value, key]
  } else {
    expandedPaths.value = expandedPaths.value.filter(entry => entry !== key)
  }

  await expandNode(props.spaceUuid, node)
}

const handleSelectionChange = (node: DirectoryNode | undefined) => {
  selectedNode.value = node
}

const selectDirectory = () => {
  if (!selectedNode.value) {
    return
  }
  committedSelectedPath.value = selectedNode.value.path
  emit('update:selectedPath', selectedNode.value.path)
  emit('select', selectedNode.value.path)
}

const selectNode = (node: DirectoryNode) => {
  selectedNode.value = node
  selectDirectory()
}

watch(
  () => [props.spaceUuid, props.rootPath],
  () => {
    expandedPaths.value = []
    selectedNode.value = undefined
    committedSelectedPath.value = ''
    clearError()
    void refresh()
  },
  { immediate: false },
)

watch(
  () => props.selectedPath,
  (path) => {
    if (!path || !items.value.length) {
      committedSelectedPath.value = path ?? ''
      return
    }
    const node = findNodeByPath(items.value, path)
    if (node) {
      selectedNode.value = node
    }
    committedSelectedPath.value = path
  },
)

onMounted(() => {
  void refresh()
})

function findNodeByPath(nodes: DirectoryNode[], path: string): DirectoryNode | undefined {
  for (const node of nodes) {
    if (node.path === path) {
      return node
    }
    if (node.children?.length) {
      const child = findNodeByPath(node.children, path)
      if (child) {
        return child
      }
    }
  }
  return undefined
}
</script>

<template>
  <section :aria-label="t('locationDirectoryPicker.ariaLabel')">
    <div
      v-if="loading"
      class="picker-status"
      role="status"
      aria-live="polite"
    >
      <i
        class="fa fa-spinner fa-spin"
        aria-hidden="true"
      />
      <span>{{ t('locationDirectoryPicker.loadingDirectories') }}</span>
    </div>

    <div
      v-else-if="error"
      class="alert alert-danger"
      role="alert"
      aria-live="assertive"
    >
      <h4>{{ t('locationDirectoryPicker.loadFailed') }}</h4>
      <p>{{ error }}</p>
      <button
        type="button"
        class="btn btn-default"
        @click="refresh"
      >
        {{ t('locationDirectoryPicker.retry') }}
      </button>
    </div>

    <div v-else>
      <TreeView
        :items="items"
        :model-value="selectedNode"
        :expanded="expandedPaths"
        :frame-style="'well'"
        :variant="'compact'"
        :auto-focus-on-items-change="true"
        :auto-focus-target="'first'"
        :get-key="node => (node as DirectoryNode).id"
        :get-children="node => (node as DirectoryNode).children"
        :right-toggles="true"
        :enter-toggles="false"
        :actions-visibility="'always'"
        @update:model-value="handleSelectionChange($event as DirectoryNode | undefined)"
        @toggle="handleToggle($event as DirectoryNode)"
      >
        <template #actions="{ node, actionProps }">
          <button
            v-if="node && (node as DirectoryNode).path !== rootPath"
            type="button"
            class="btn btn-link picker-select-action"
            v-bind="actionProps"
            @click.stop.prevent="selectNode(node as DirectoryNode)"
          >
            {{ t('locationDirectoryPicker.select') }}
          </button>
        </template>
      </TreeView>
    </div>
  </section>
</template>

<style scoped>
.picker-status {
  display: flex;
  align-items: center;
  gap: 8px;
}

.picker-select-action {
  padding: 0;
  font-size: 14px;
}
</style>
