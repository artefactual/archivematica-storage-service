const PURPOSE_FIELD_SELECTOR = 'select#id_purpose'
const REPLICATORS_FIELD_SELECTOR = 'select#id_replicators'
const AIP_STORAGE_PURPOSE = 'AS'

const setReplicatorsVisibility = (
  purposeField: HTMLSelectElement,
  replicatorsField: HTMLSelectElement,
): void => {
  const replicatorsRow = replicatorsField.closest('p')
  if (!replicatorsRow) {
    return
  }

  const showReplicators = purposeField.value === AIP_STORAGE_PURPOSE
  replicatorsRow.style.display = showReplicators ? '' : 'none'
}

export const init = (): void => {
  const purposeField = document.querySelector<HTMLSelectElement>(PURPOSE_FIELD_SELECTOR)
  const replicatorsField = document.querySelector<HTMLSelectElement>(REPLICATORS_FIELD_SELECTOR)
  if (!purposeField || !replicatorsField) {
    return
  }

  const syncVisibility = (): void => {
    setReplicatorsVisibility(purposeField, replicatorsField)
  }

  purposeField.addEventListener('change', syncVisibility)
  syncVisibility()
}
