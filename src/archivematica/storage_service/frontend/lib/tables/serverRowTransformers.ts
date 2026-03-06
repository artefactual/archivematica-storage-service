import { translate } from '@/shared/i18n/plain'
import type { TableRow } from './types'

type AjaxLinkCell = {
  text: string
  href: string | null
}

type AjaxStatusCell = {
  text: string
  update_href: string | null
}

type AjaxFixityStatusCell = {
  text: string
  href: string
}

type AjaxRequestDeleteAction = {
  action_url: string
  csrf_token: string
}

type AjaxDirectDeleteAction = {
  action_url: string
  csrf_token: string
  modal_id: string
  modal_label_id: string
  modal_title: string
  prompt_text: string
  close_label: string
  confirm_label: string
}

type AjaxActionsCell = {
  pointer_file_href: string | null
  download_href: string | null
  reingest_href: string | null
  request_delete: AjaxRequestDeleteAction | null
  direct_delete: AjaxDirectDeleteAction | null
}

export type PackageAjaxRow = {
  uuid: string
  origin_pipeline: AjaxLinkCell
  current_location: AjaxLinkCell
  size: string
  package_type: string
  replica_of: string
  status: AjaxStatusCell
  stored: string
  fixity_date: string
  fixity_status: AjaxFixityStatusCell
  actions: AjaxActionsCell
}

export type FixityLogAjaxRow = {
  date: string
  error: string
}

const toTextOrLinkCell = (cell: AjaxLinkCell): TableRow[string] => {
  if (cell.href) {
    return {
      kind: 'link',
      text: cell.text,
      href: cell.href,
    }
  }
  return cell.text
}

export const toPackageTableRow = (row: PackageAjaxRow): TableRow => {
  const links: Array<{ label: string, href: string }> = []
  if (row.actions.pointer_file_href) {
    links.push({
      label: translate('packageActions.pointerFile'),
      href: row.actions.pointer_file_href,
    })
  }
  if (row.actions.download_href) {
    links.push({
      label: translate('packageActions.download'),
      href: row.actions.download_href,
    })
  }
  if (row.actions.reingest_href) {
    links.push({
      label: translate('packageActions.reingest'),
      href: row.actions.reingest_href,
    })
  }

  return {
    uuid: row.uuid,
    origin_pipeline: toTextOrLinkCell(row.origin_pipeline),
    current_location: toTextOrLinkCell(row.current_location),
    size: row.size,
    package_type: row.package_type,
    replica_of: row.replica_of,
    status: {
      kind: 'status-with-link',
      text: row.status.text,
      link: row.status.update_href
        ? {
            text: translate('packageActions.updateStatus'),
            href: row.status.update_href,
          }
        : undefined,
    },
    stored: row.stored,
    fixity_date: row.fixity_date,
    fixity_status: {
      kind: 'link',
      text: row.fixity_status.text,
      href: row.fixity_status.href,
    },
    actions: {
      kind: 'package-actions',
      links,
      requestDelete: row.actions.request_delete
        ? {
            actionUrl: row.actions.request_delete.action_url,
            csrfToken: row.actions.request_delete.csrf_token,
          }
        : undefined,
      directDelete: row.actions.direct_delete
        ? {
            actionUrl: row.actions.direct_delete.action_url,
            csrfToken: row.actions.direct_delete.csrf_token,
            modalId: row.actions.direct_delete.modal_id,
            modalLabelId: row.actions.direct_delete.modal_label_id,
            modalTitle: row.actions.direct_delete.modal_title,
            promptText: row.actions.direct_delete.prompt_text,
            closeLabel: row.actions.direct_delete.close_label,
            confirmLabel: row.actions.direct_delete.confirm_label,
          }
        : undefined,
    },
  }
}

export const toFixityLogTableRow = (row: FixityLogAjaxRow): TableRow => {
  return {
    date: row.date,
    error: row.error,
  }
}
