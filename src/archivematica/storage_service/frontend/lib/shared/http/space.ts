import { createHttpClient } from './client'
import type { RequestOptions } from './client'
import type { Base64String } from '@/shared/encoding/base64'

export type SpaceBrowseResponse = {
  entries?: Base64String[]
  directories?: Base64String[]
  properties?: Record<string, Record<string, unknown>>
}

const client = createHttpClient()

export const browseSpaceDirectory = async (
  spaceUuid: string,
  path: string,
  requestOptions: Omit<RequestOptions, 'query'> = {},
): Promise<SpaceBrowseResponse> => {
  return client.getJson<SpaceBrowseResponse>(`/api/v2/space/${spaceUuid}/browse/`, {
    query: path ? { path } : undefined,
    ...requestOptions,
    strictJson: true,
  })
}
