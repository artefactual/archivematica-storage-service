<script setup lang="ts">
import { computed } from 'vue'
import type { PackageActionsCell } from './types'

const props = defineProps<{
  cell: PackageActionsCell
}>()

type GettextGlobal = typeof globalThis & {
  gettext?: (message: string) => string
}

const translate = (message: string): string => {
  const gettext = (globalThis as GettextGlobal).gettext
  if (typeof gettext === 'function') {
    return gettext(message)
  }
  return message
}

const requestDeleteLabel = computed(() => translate('Request Deletion'))

const directDeleteModalTarget = computed(() => {
  if (!props.cell.directDelete) {
    return ''
  }
  return `#${props.cell.directDelete.modalId}`
})
</script>

<template>
  <template
    v-for="(link, index) in cell.links"
    :key="`${link.href}-${index}`"
  >
    <a :href="link.href">{{ link.label }}</a>
    <span v-if="index < cell.links.length - 1"> | </span>
  </template>

  <span
    v-if="cell.requestDelete && cell.links.length > 0"
    class="ss-table-action-separator"
  > | </span>

  <a
    v-if="cell.requestDelete"
    href="#"
    class="request-delete"
    :data-package-type="cell.requestDelete.packageType"
    :data-package-uuid="cell.requestDelete.packageUuid"
    :data-package-pipeline="cell.requestDelete.pipelineUuid"
  >{{ requestDeleteLabel }}</a>

  <span
    v-if="cell.directDelete && (cell.requestDelete || cell.links.length > 0)"
    class="ss-table-action-separator"
  > | </span>

  <form
    v-if="cell.directDelete"
    method="post"
    :action="cell.directDelete.actionUrl"
    class="ss-table-package-actions-form"
  >
    <input
      type="hidden"
      name="csrfmiddlewaretoken"
      :value="cell.directDelete.csrfToken"
    >
    <button
      class="link"
      type="button"
      :data-am-modal-target="directDeleteModalTarget"
    >
      {{ cell.directDelete.confirmLabel }}
    </button>
    <div
      :id="cell.directDelete.modalId"
      class="confirm-modal modal hide fade"
      tabindex="-1"
      role="dialog"
      :aria-labelledby="cell.directDelete.modalLabelId"
      aria-hidden="true"
    >
      <div class="modal-header">
        <button
          type="button"
          class="close"
          data-dismiss="modal"
          aria-hidden="true"
        >
          &times;
        </button>
        <h3 :id="cell.directDelete.modalLabelId">
          {{ cell.directDelete.modalTitle }}
        </h3>
      </div>
      <div class="modal-body">
        <p>{{ cell.directDelete.promptText }}</p>
      </div>
      <div class="modal-footer">
        <button
          class="btn"
          type="button"
          data-dismiss="modal"
          aria-hidden="true"
        >
          {{ cell.directDelete.closeLabel }}
        </button>
        <button
          class="btn btn-danger"
          type="submit"
        >
          {{ cell.directDelete.confirmLabel }}
        </button>
      </div>
    </div>
  </form>
</template>

<style scoped>
.ss-table-package-actions-form {
  display: inline;
}

.ss-table-action-separator {
  margin: 0 4px;
}
</style>
