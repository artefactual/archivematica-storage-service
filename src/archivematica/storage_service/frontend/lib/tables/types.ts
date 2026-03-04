export type TableKind = (
  | 'keys-list'
  | 'users-list'
  | 'pipelines-list'
  | 'locations-list'
  | 'callbacks-list'
  | 'package-requests-pending'
  | 'package-requests-closed'
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
  | LinkListCell
  | TextWithLinksCell
  | DecisionFormCell
)

export type TableRow = Record<string, TableCell | TableAction[]>

export type TableColumn = {
  key: string
  label: string
  sortable?: boolean
}

export type TablePayload = {
  version: number
  kind: TableKind
  columns: TableColumn[]
  rows: TableRow[]
  ui: Record<string, unknown>
}
