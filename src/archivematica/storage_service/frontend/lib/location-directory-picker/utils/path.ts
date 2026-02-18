export const toAbsolutePath = (rootPath: string, relativePath: string): string => {
  const trimmedRelativePath = relativePath.trim()
  if (!trimmedRelativePath) {
    return ''
  }

  if (trimmedRelativePath.startsWith('/')) {
    return trimmedRelativePath
  }

  const normalizedRootPath = rootPath.trim() || '/'
  const normalizedRelativePath = trimmedRelativePath.replace(/^\/+/, '')
  if (normalizedRootPath === '/') {
    return `/${normalizedRelativePath}`
  }
  return `${normalizedRootPath.replace(/\/$/, '')}/${normalizedRelativePath}`
}

export const toRelativePath = (rootPath: string, selectedPath: string): string => {
  const trimmedPath = selectedPath.trim()
  if (!trimmedPath) {
    return ''
  }

  const normalizedRootPath = (rootPath.trim() || '/').replace(/\/$/, '')
  if (normalizedRootPath && normalizedRootPath !== '/' && trimmedPath.startsWith(`${normalizedRootPath}/`)) {
    return trimmedPath.slice(normalizedRootPath.length + 1)
  }

  if (trimmedPath === normalizedRootPath) {
    return ''
  }

  return trimmedPath.replace(/^\/+/, '')
}
