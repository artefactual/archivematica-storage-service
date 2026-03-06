<script setup lang="ts">
import { computed } from 'vue'
import type {
  DecisionFormCell,
  LinkCell,
  LinkListCell,
  PackageActionsCell,
  StatusWithLinkCell,
  TableAction,
  TableActionStyle,
  TextWithLinksCell,
} from './types'
import TableDecisionFormCell from './TableDecisionFormCell.vue'
import TablePackageActionsCell from './TablePackageActionsCell.vue'

const props = defineProps<{
  columnId: string
  value: unknown
}>()

const isLinkCell = (value: unknown): value is LinkCell => {
  if (!value || typeof value !== 'object') {
    return false
  }
  const maybeCell = value as Partial<LinkCell>
  return (
    maybeCell.kind === 'link'
    && typeof maybeCell.text === 'string'
    && typeof maybeCell.href === 'string'
  )
}

const isLinkListCell = (value: unknown): value is LinkListCell => {
  if (!value || typeof value !== 'object') {
    return false
  }
  const maybeCell = value as Partial<LinkListCell>
  return maybeCell.kind === 'link-list' && Array.isArray(maybeCell.items)
}

const isTextWithLinksCell = (value: unknown): value is TextWithLinksCell => {
  if (!value || typeof value !== 'object') {
    return false
  }
  const maybeCell = value as Partial<TextWithLinksCell>
  return (
    maybeCell.kind === 'text-with-links'
    && typeof maybeCell.text === 'string'
    && Array.isArray(maybeCell.items)
  )
}

const isTableAction = (value: unknown): value is TableAction => {
  if (!value || typeof value !== 'object') {
    return false
  }
  const maybeAction = value as Partial<TableAction>
  return typeof maybeAction.label === 'string' && typeof maybeAction.href === 'string'
}

const isStatusWithLinkCell = (value: unknown): value is StatusWithLinkCell => {
  if (!value || typeof value !== 'object') {
    return false
  }
  const maybeCell = value as Partial<StatusWithLinkCell>
  return maybeCell.kind === 'status-with-link' && typeof maybeCell.text === 'string'
}

const isPackageActionsCell = (value: unknown): value is PackageActionsCell => {
  if (!value || typeof value !== 'object') {
    return false
  }
  const maybeCell = value as Partial<PackageActionsCell>
  return maybeCell.kind === 'package-actions' && Array.isArray(maybeCell.links)
}

const isDecisionFormCell = (value: unknown): value is DecisionFormCell => {
  if (!value || typeof value !== 'object') {
    return false
  }
  const maybeCell = value as Partial<DecisionFormCell>
  return (
    maybeCell.kind === 'decision-form'
    && typeof maybeCell.action === 'string'
    && typeof maybeCell.csrfToken === 'string'
    && typeof maybeCell.eventIdName === 'string'
    && typeof maybeCell.eventId === 'number'
    && typeof maybeCell.reasonName === 'string'
    && typeof maybeCell.reasonLabel === 'string'
    && typeof maybeCell.decisionName === 'string'
    && typeof maybeCell.approveValue === 'string'
    && typeof maybeCell.rejectValue === 'string'
    && typeof maybeCell.approveLabel === 'string'
    && typeof maybeCell.rejectLabel === 'string'
  )
}

const actions = computed<TableAction[]>(() => {
  if (props.columnId !== 'actions') {
    return []
  }
  if (!Array.isArray(props.value)) {
    return []
  }
  return props.value.filter(isTableAction).map(action => ({
    label: action.label,
    href: action.href,
    style: action.style ?? 'default',
  }))
})

const asDecisionFormCell = computed<DecisionFormCell | null>(() => {
  return isDecisionFormCell(props.value) ? props.value : null
})

const asStatusWithLinkCell = computed<StatusWithLinkCell | null>(() => {
  return isStatusWithLinkCell(props.value) ? props.value : null
})

const asPackageActionsCell = computed<PackageActionsCell | null>(() => {
  return isPackageActionsCell(props.value) ? props.value : null
})

const valueText = computed(() => {
  if (props.value === null || props.value === undefined) {
    return ''
  }
  if (typeof props.value === 'string' || typeof props.value === 'number' || typeof props.value === 'boolean') {
    return String(props.value)
  }
  return ''
})

const asLinkCell = computed<LinkCell | null>(() => {
  return isLinkCell(props.value) ? props.value : null
})

const asLinkListCell = computed<LinkListCell | null>(() => {
  return isLinkListCell(props.value) ? props.value : null
})

const asTextWithLinksCell = computed<TextWithLinksCell | null>(() => {
  return isTextWithLinksCell(props.value) ? props.value : null
})

const actionClass = (style: TableActionStyle): string => {
  if (style === 'primary') {
    return 'ss-table-action-link ss-table-action-link--primary'
  }
  if (style === 'destructive') {
    return 'ss-table-action-link ss-table-action-link--destructive'
  }
  return 'ss-table-action-link'
}

const linkListSeparator = (cell: LinkListCell): string => cell.separator || ', '
</script>

<template>
  <template v-if="columnId === 'actions' && asDecisionFormCell">
    <TableDecisionFormCell :cell="asDecisionFormCell" />
  </template>

  <template v-else-if="columnId === 'actions' && asPackageActionsCell">
    <TablePackageActionsCell :cell="asPackageActionsCell" />
  </template>

  <template v-else-if="columnId === 'actions'">
    <template
      v-for="(action, index) in actions"
      :key="`${action.href}-${index}`"
    >
      <a
        :href="action.href"
        :class="actionClass(action.style)"
      >
        {{ action.label }}
      </a>
      <span
        v-if="index < actions.length - 1"
        class="ss-table-action-separator"
      >
        |
      </span>
    </template>
  </template>

  <template v-else-if="asLinkCell">
    <a :href="asLinkCell.href">
      {{ asLinkCell.text }}
    </a>
  </template>

  <template v-else-if="asStatusWithLinkCell">
    <span>{{ asStatusWithLinkCell.text }}</span>
    <template v-if="asStatusWithLinkCell.link">
      <span> (</span>
      <a :href="asStatusWithLinkCell.link.href">{{ asStatusWithLinkCell.link.text }}</a>
      <span>)</span>
    </template>
  </template>

  <template v-else-if="asLinkListCell">
    <template v-if="asLinkListCell.items.length > 0">
      <template
        v-for="(item, index) in asLinkListCell.items"
        :key="`${item.href}-${index}`"
      >
        <a :href="item.href">{{ item.text }}</a>
        <span v-if="index < asLinkListCell.items.length - 1">
          {{ linkListSeparator(asLinkListCell) }}
        </span>
      </template>
    </template>
    <template v-else>
      {{ asLinkListCell.emptyText || '' }}
    </template>
  </template>

  <template v-else-if="asTextWithLinksCell">
    <span>{{ asTextWithLinksCell.text }}</span>
    <template v-if="asTextWithLinksCell.items.length > 0">
      <span v-if="asTextWithLinksCell.connector">
        {{ ` ${asTextWithLinksCell.connector} ` }}
      </span>
      <template
        v-for="(item, index) in asTextWithLinksCell.items"
        :key="`${item.href}-${index}`"
      >
        <a :href="item.href">{{ item.text }}</a>
        <span v-if="index < asTextWithLinksCell.items.length - 1">, </span>
      </template>
    </template>
  </template>

  <template v-else>
    {{ valueText }}
  </template>
</template>

<style scoped>
.ss-table-action-link {
  color: #08c;
  text-decoration: none;
}

.ss-table-action-link:hover {
  color: #005580;
  text-decoration: underline;
}

.ss-table-action-link--primary,
.ss-table-action-link--destructive {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 3px;
  border: 1px solid transparent;
  text-decoration: none;
}

.ss-table-action-link--primary {
  color: #fff;
  background: #006dcc;
  border-color: #0044cc;
}

.ss-table-action-link--primary:hover {
  color: #fff;
  background: #0044cc;
  text-decoration: none;
}

.ss-table-action-link--destructive {
  color: #fff;
  background: #bd362f;
  border-color: #802420;
}

.ss-table-action-link--destructive:hover {
  color: #fff;
  background: #802420;
  text-decoration: none;
}

.ss-table-action-separator {
  margin: 0 6px;
}
</style>
