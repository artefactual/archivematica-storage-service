<script setup lang="ts">
import { useI18n } from 'vue-i18n'

const props = defineProps<{
  pageIndex: number
  canPrevious: boolean
  canNext: boolean
}>()

const emit = defineEmits<{
  'update:pageIndex': [number]
}>()

const { t } = useI18n()

const onPrevious = (): void => {
  if (!props.canPrevious) {
    return
  }
  emit('update:pageIndex', props.pageIndex - 1)
}

const onNext = (): void => {
  if (!props.canNext) {
    return
  }
  emit('update:pageIndex', props.pageIndex + 1)
}
</script>

<template>
  <div class="ss-table-pagination__controls">
    <button
      class="ss-table-pagination__link ss-table-pagination__link--previous"
      type="button"
      :class="{ 'ss-table-pagination__link--disabled': !canPrevious }"
      :disabled="!canPrevious"
      @click="onPrevious"
    >
      {{ t('tables.previous') }}
    </button>
    <button
      class="ss-table-pagination__link ss-table-pagination__link--next"
      type="button"
      :class="{ 'ss-table-pagination__link--disabled': !canNext }"
      :disabled="!canNext"
      @click="onNext"
    >
      {{ t('tables.next') }}
    </button>
  </div>
</template>

<style scoped>
.ss-table-pagination__controls {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
}

.ss-table-pagination__link {
  --ss-table-arrow-color: #8c93fe;
  --ss-table-arrow-shadow: rgba(88, 92, 126, 0.55);
  border: 0;
  padding: 0;
  margin: 0;
  position: relative;
  background: transparent;
  color: #111;
  font: inherit;
  line-height: 19px;
  cursor: pointer;
  text-decoration: none;
  white-space: nowrap;
  text-align: right;
}

.ss-table-pagination__link--previous {
  padding-left: 25px;
}

.ss-table-pagination__link--next {
  padding-right: 25px;
  margin-left: 10px;
}

.ss-table-pagination__link--disabled {
  color: #666;
  cursor: pointer;
  --ss-table-arrow-color: #999;
  --ss-table-arrow-shadow: rgba(96, 96, 96, 0.45);
}

.ss-table-pagination__link--previous::before,
.ss-table-pagination__link--next::after {
  content: '';
  position: absolute;
  top: 50%;
  width: 0;
  height: 0;
  transform: translateY(-50%);
  border-top: 5px solid transparent;
  border-bottom: 5px solid transparent;
}

.ss-table-pagination__link--previous::before {
  left: 2px;
  border-right: 7px solid var(--ss-table-arrow-color);
  filter: drop-shadow(1px 1px 1px var(--ss-table-arrow-shadow));
}

.ss-table-pagination__link--next::after {
  right: 2px;
  border-left: 7px solid var(--ss-table-arrow-color);
  filter: drop-shadow(1px 1px 1px var(--ss-table-arrow-shadow));
}

.ss-table-pagination__link:not(:disabled):hover {
  color: #111;
  text-decoration: none;
  --ss-table-arrow-color: #535ce0;
  --ss-table-arrow-shadow: rgba(58, 62, 92, 0.6);
}

.ss-table-pagination__link:disabled {
  color: #666;
  cursor: pointer;
  opacity: 1;
}

.ss-table-pagination__link:active {
  outline: none;
}
</style>
