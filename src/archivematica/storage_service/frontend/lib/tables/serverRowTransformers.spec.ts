import { describe, expect, it } from 'vitest'
import { toFixityLogTableRow, toPackageTableRow, type PackageAjaxRow } from './serverRowTransformers'

describe('serverRowTransformers', () => {
  it('maps package ajax rows to table rows with actions', () => {
    const source: PackageAjaxRow = {
      uuid: 'pkg-1',
      origin_pipeline: { text: 'Pipeline A', href: '/pipelines/1/' },
      current_location: { text: '/var/aip', href: '/download/pkg-1/' },
      size: '1 KB',
      package_type: 'AIP',
      replica_of: '',
      status: { text: 'Stored', update_href: '/package/pkg-1/status/?next=/packages/' },
      stored: '2026-03-05',
      fixity_date: '2026-03-05',
      fixity_status: { text: 'Success', href: '/fixity/pkg-1/' },
      actions: {
        pointer_file_href: '/pointer/pkg-1/',
        download_href: '/download/pkg-1/',
        reingest_href: '/reingest/pkg-1/',
        request_delete: {
          package_type: 'AIP',
          package_uuid: 'pkg-1',
          pipeline_uuid: 'pipeline-1',
        },
        direct_delete: {
          action_url: '/package/pkg-1/delete/',
          csrf_token: 'csrf-token',
          modal_id: 'confirm-delete-pkg-1',
          modal_label_id: 'confirm-delete-title-pkg-1',
          modal_title: 'Delete package',
          prompt_text: 'Confirm delete',
          close_label: 'Close',
          confirm_label: 'Delete',
        },
      },
    }

    const result = toPackageTableRow(source)

    expect(result.uuid).toBe('pkg-1')
    expect(result.origin_pipeline).toEqual({
      kind: 'link',
      text: 'Pipeline A',
      href: '/pipelines/1/',
    })
    expect(result.status).toEqual({
      kind: 'status-with-link',
      text: 'Stored',
      link: {
        text: 'Update Status',
        href: '/package/pkg-1/status/?next=/packages/',
      },
    })
    expect(result.actions).toEqual({
      kind: 'package-actions',
      links: [
        { label: 'Pointer File', href: '/pointer/pkg-1/' },
        { label: 'Download', href: '/download/pkg-1/' },
        { label: 'Re-ingest', href: '/reingest/pkg-1/' },
      ],
      requestDelete: {
        packageType: 'AIP',
        packageUuid: 'pkg-1',
        pipelineUuid: 'pipeline-1',
      },
      directDelete: {
        actionUrl: '/package/pkg-1/delete/',
        csrfToken: 'csrf-token',
        modalId: 'confirm-delete-pkg-1',
        modalLabelId: 'confirm-delete-title-pkg-1',
        modalTitle: 'Delete package',
        promptText: 'Confirm delete',
        closeLabel: 'Close',
        confirmLabel: 'Delete',
      },
    })
  })

  it('maps fixity rows to plain table rows', () => {
    expect(toFixityLogTableRow({ date: '2026-03-05', error: 'none' })).toEqual({
      date: '2026-03-05',
      error: 'none',
    })
  })
})
