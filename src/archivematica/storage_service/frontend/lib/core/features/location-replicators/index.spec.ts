import { beforeEach, describe, expect, it } from 'vitest'
import { init } from './index'

const PURPOSE_FIELD_ID = 'id_purpose'
const REPLICATORS_FIELD_ID = 'id_replicators'

type Fixture = {
  purposeField: HTMLSelectElement
  replicatorsRow: HTMLParagraphElement
}

const setFixture = (purpose = 'DS'): Fixture => {
  document.body.innerHTML = `
    <form>
      <p>
        <label for="${PURPOSE_FIELD_ID}">Purpose:</label>
        <select id="${PURPOSE_FIELD_ID}">
          <option value="DS">DIP Storage</option>
          <option value="AS">AIP Storage</option>
        </select>
      </p>
      <p id="replicators-row">
        <label for="${REPLICATORS_FIELD_ID}">Replicators:</label>
        <select id="${REPLICATORS_FIELD_ID}"></select>
      </p>
    </form>
  `

  const purposeField = document.getElementById(PURPOSE_FIELD_ID)
  const replicatorsRow = document.getElementById('replicators-row')
  if (!(purposeField instanceof HTMLSelectElement) || !(replicatorsRow instanceof HTMLParagraphElement)) {
    throw new Error('Failed to build location replicators fixture')
  }

  purposeField.value = purpose
  return { purposeField, replicatorsRow }
}

describe('core location-replicators feature', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
  })

  it('hides replicators when purpose is not AIP storage', () => {
    const { replicatorsRow } = setFixture('DS')

    init()

    expect(replicatorsRow.style.display).toBe('none')
  })

  it('shows replicators when purpose is AIP storage and keeps it in sync', () => {
    const { purposeField, replicatorsRow } = setFixture('AS')

    init()
    expect(replicatorsRow.style.display).toBe('')

    purposeField.value = 'DS'
    purposeField.dispatchEvent(new Event('change', { bubbles: true }))
    expect(replicatorsRow.style.display).toBe('none')

    purposeField.value = 'AS'
    purposeField.dispatchEvent(new Event('change', { bubbles: true }))
    expect(replicatorsRow.style.display).toBe('')
  })

  it('does nothing when expected fields are missing', () => {
    document.body.innerHTML = '<form></form>'

    expect(() => init()).not.toThrow()
  })
})
