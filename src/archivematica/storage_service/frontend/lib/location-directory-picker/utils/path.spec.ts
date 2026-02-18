import { describe, expect, it } from 'vitest'
import { toAbsolutePath, toRelativePath } from '@/location-directory-picker/utils/path'

describe('toAbsolutePath', () => {
  it('returns empty string for empty relative path', () => {
    expect(toAbsolutePath('/root', '')).toBe('')
    expect(toAbsolutePath('/root', '   ')).toBe('')
  })

  it('returns absolute path unchanged', () => {
    expect(toAbsolutePath('/root', '/already/absolute')).toBe('/already/absolute')
  })

  it('joins root and relative path', () => {
    expect(toAbsolutePath('/root', 'child/path')).toBe('/root/child/path')
    expect(toAbsolutePath('/root/', 'child/path')).toBe('/root/child/path')
  })

  it('joins from root slash', () => {
    expect(toAbsolutePath('/', 'child/path')).toBe('/child/path')
    expect(toAbsolutePath('', 'child/path')).toBe('/child/path')
  })

  it('treats paths starting with slash as already absolute', () => {
    expect(toAbsolutePath('/root', '///child/path')).toBe('///child/path')
  })
})

describe('toRelativePath', () => {
  it('returns empty string for empty selected path', () => {
    expect(toRelativePath('/root', '')).toBe('')
    expect(toRelativePath('/root', '   ')).toBe('')
  })

  it('returns path relative to root when selected path is under root', () => {
    expect(toRelativePath('/root', '/root/child/path')).toBe('child/path')
    expect(toRelativePath('/root/', '/root/child/path')).toBe('child/path')
  })

  it('returns empty string when selected path equals root', () => {
    expect(toRelativePath('/root', '/root')).toBe('')
    expect(toRelativePath('/root/', '/root')).toBe('')
  })

  it('normalizes fallback path by stripping leading slashes', () => {
    expect(toRelativePath('/root', '/other/place')).toBe('other/place')
  })

  it('handles root slash as base path', () => {
    expect(toRelativePath('/', '/home/archivematica')).toBe('home/archivematica')
  })
})
