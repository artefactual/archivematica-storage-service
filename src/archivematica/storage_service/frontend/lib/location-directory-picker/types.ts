export type DirectoryNode = {
  id: string
  label: string
  path: string
  children: DirectoryNode[]
  loaded: boolean
  loading: boolean
  loadError: string | null
}

export type DecodedBrowseResponse = {
  entries: string[]
  directories: string[]
}
