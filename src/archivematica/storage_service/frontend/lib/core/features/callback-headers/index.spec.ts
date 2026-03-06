import { beforeEach, describe, expect, it } from 'vitest'
import { init } from './index'

const getHeaderRows = (): HTMLParagraphElement[] => {
  const rows = document.querySelectorAll('.callback > form p')
  return Array.from(rows).filter((row): row is HTMLParagraphElement => {
    return row instanceof HTMLParagraphElement
      && row.querySelectorAll('input[name^="header_"]').length >= 2
  })
}

const setFixture = (): void => {
  document.body.innerHTML = `
    <div class="callback">
      <form>
        <p id="header-row-0">
          <label for="id_header_0_0">Headers (key/value):</label>
          <input id="id_header_0_0" name="header_0_0" value="Header-Key">
          <input id="id_header_0_1" name="header_0_1" value="Header-Value">
        </p>
        <p>
          <label for="id_body">Body:</label>
          <textarea id="id_body" name="body"></textarea>
        </p>
      </form>
    </div>
  `
}

describe('core callback-headers feature', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
    setFixture()
  })

  it('initializes delete links and add-header action', () => {
    init()

    expect(document.querySelectorAll('.callback > form a.delete_header')).toHaveLength(1)
    expect(document.querySelector('.callback > form a.add_header')).not.toBeNull()
  })

  it('adds a new empty header row with incremented field names', () => {
    init()
    const addLink = document.querySelector<HTMLAnchorElement>('.callback > form a.add_header')
    if (!addLink) {
      throw new Error('Missing add-header link')
    }

    addLink.click()

    const rows = getHeaderRows()
    expect(rows).toHaveLength(2)
    expect(rows[1].querySelector('label')).toBeNull()

    const newInputs = rows[1].querySelectorAll<HTMLInputElement>('input[name^="header_"]')
    expect(newInputs).toHaveLength(2)
    expect(newInputs[0].name).toBe('header_1_0')
    expect(newInputs[0].value).toBe('')
    expect(newInputs[1].name).toBe('header_1_1')
    expect(newInputs[1].value).toBe('')
  })

  it('deletes a header row and renumbers following rows', () => {
    init()
    const addLink = document.querySelector<HTMLAnchorElement>('.callback > form a.add_header')
    if (!addLink) {
      throw new Error('Missing add-header link')
    }
    addLink.click()

    const rowsBeforeDelete = getHeaderRows()
    const secondRowInputs = rowsBeforeDelete[1].querySelectorAll<HTMLInputElement>('input[name^="header_"]')
    secondRowInputs[0].value = 'Renumbered-Key'
    secondRowInputs[1].value = 'Renumbered-Value'

    const firstDeleteLink = rowsBeforeDelete[0].querySelector<HTMLAnchorElement>('a.delete_header')
    if (!firstDeleteLink) {
      throw new Error('Missing delete-header link')
    }
    firstDeleteLink.click()

    const rowsAfterDelete = getHeaderRows()
    expect(rowsAfterDelete).toHaveLength(1)
    const inputs = rowsAfterDelete[0].querySelectorAll<HTMLInputElement>('input[name^="header_"]')
    expect(inputs[0].name).toBe('header_0_0')
    expect(inputs[0].value).toBe('Renumbered-Key')
    expect(inputs[1].name).toBe('header_0_1')
    expect(inputs[1].value).toBe('Renumbered-Value')
    expect(rowsAfterDelete[0].querySelector('label')).not.toBeNull()
  })

  it('clears the only header row instead of removing it', () => {
    init()

    const deleteLink = document.querySelector<HTMLAnchorElement>('.callback > form a.delete_header')
    if (!deleteLink) {
      throw new Error('Missing delete-header link')
    }
    deleteLink.click()

    const rows = getHeaderRows()
    expect(rows).toHaveLength(1)
    const inputs = rows[0].querySelectorAll<HTMLInputElement>('input[name^="header_"]')
    expect(inputs[0].value).toBe('')
    expect(inputs[1].value).toBe('')
  })
})
