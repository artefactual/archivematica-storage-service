export type TableKind = (
  | 'keys-list'
  | 'users-list'
  | 'pipelines-list'
  | 'locations-list'
  | 'callbacks-list'
  | 'package-requests-pending'
  | 'package-requests-closed'
  | 'packages-server'
  | 'fixity-logs-server'
)

export type TableActionStyle = 'default' | 'primary' | 'destructive'

export type TableAction = {
  label: string
  href: string
  style: TableActionStyle
}

export type LinkCell = {
  kind: 'link'
  text: string
  href: string
}

export type LinkItem = {
  text: string
  href: string
}

export type StatusWithLinkCell = {
  kind: 'status-with-link'
  text: string
  link?: LinkItem
}

export type RequestDeleteAction = {
  packageType: string
  packageUuid: string
  pipelineUuid: string
}

export type DirectDeleteAction = {
  actionUrl: string
  csrfToken: string
  modalId: string
  modalLabelId: string
  modalTitle: string
  promptText: string
  closeLabel: string
  confirmLabel: string
}

export type PackageActionLink = {
  label: string
  href: string
}

export type PackageActionsCell = {
  kind: 'package-actions'
  links: PackageActionLink[]
  requestDelete?: RequestDeleteAction
  directDelete?: DirectDeleteAction
}

export type LinkListCell = {
  kind: 'link-list'
  items: LinkItem[]
  emptyText?: string
  separator?: string
}

export type TextWithLinksCell = {
  kind: 'text-with-links'
  text: string
  items: LinkItem[]
  connector?: string
}

export type DecisionFormCell = {
  kind: 'decision-form'
  action: string
  method?: 'post'
  csrfToken: string
  eventIdName: string
  eventId: number
  reasonName: string
  reasonLabel: string
  reasonValue?: string
  reasonErrors?: string[]
  decisionName: string
  approveValue: string
  rejectValue: string
  approveLabel: string
  rejectLabel: string
}

export type TableCell = (
  | string
  | number
  | boolean
  | LinkCell
  | StatusWithLinkCell
  | LinkListCell
  | TextWithLinksCell
  | DecisionFormCell
  | PackageActionsCell
)

export type TableRow = Record<string, TableCell | TableAction[]>

export type TableColumn = {
  key: string
  label: string
  sortable?: boolean
}

export type SortDirection = 'asc' | 'desc'

export type DatatablesDefaultSort = {
  columnKey: string
  direction?: SortDirection
}

export type DatatablesServerUiConfig = {
  mode: 'server-datatables-v1'
  endpoint: string
  filters?: Record<string, string>
  defaultSort?: DatatablesDefaultSort
}

export type TableUiConfig = {
  server?: DatatablesServerUiConfig
} & Record<string, unknown>

export type TablePayload = {
  version: number
  kind: TableKind
  columns: TableColumn[]
  rows: TableRow[]
  ui: TableUiConfig
}
