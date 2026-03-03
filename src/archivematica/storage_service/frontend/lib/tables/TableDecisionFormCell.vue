<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { DecisionFormCell } from './types'

const props = defineProps<{
  cell: DecisionFormCell
}>()

const reasonInputId = computed(() => `ss-table-status-reason-${props.cell.eventId}`)
const reasonErrors = computed(() => props.cell.reasonErrors ?? [])
const reason = ref(props.cell.reasonValue || '')

watch(
  () => props.cell.reasonValue,
  (value) => {
    reason.value = value || ''
  },
)
</script>

<template>
  <form
    :action="cell.action"
    :method="cell.method || 'post'"
    class="ss-table-decision-form"
  >
    <input
      type="hidden"
      name="csrfmiddlewaretoken"
      :value="cell.csrfToken"
    >
    <input
      type="hidden"
      :name="cell.eventIdName"
      :value="cell.eventId"
    >

    <p class="ss-table-decision-form__field">
      <label
        :for="reasonInputId"
        class="ss-table-decision-form__label"
      >
        {{ cell.reasonLabel }}
      </label>
      <textarea
        :id="reasonInputId"
        v-model="reason"
        :name="cell.reasonName"
        class="ss-table-decision-form__reason"
        cols="40"
        rows="10"
        required
      />
    </p>

    <ul
      v-if="reasonErrors.length > 0"
      class="errorlist"
    >
      <li
        v-for="(error, index) in reasonErrors"
        :key="`${error}-${index}`"
      >
        {{ error }}
      </li>
    </ul>

    <div class="ss-table-decision-form__buttons">
      <button
        type="submit"
        :name="cell.decisionName"
        :value="cell.approveValue"
        class="ss-table-decision-form__button ss-table-decision-form__button--approve"
      >
        {{ cell.approveLabel }}
      </button>
      <button
        type="submit"
        :name="cell.decisionName"
        :value="cell.rejectValue"
        class="ss-table-decision-form__button ss-table-decision-form__button--reject"
      >
        {{ cell.rejectLabel }}
      </button>
    </div>
  </form>
</template>

<style scoped>
.ss-table-decision-form {
  margin: 0 0 20px;
}

.ss-table-decision-form__field {
  margin: 0 0 10px;
}

.ss-table-decision-form__label {
  display: block;
  margin-bottom: 5px;
  font-weight: 400;
}

.ss-table-decision-form__reason {
  display: block;
  min-height: 80px;
  padding: 4px 6px;
  margin: 0;
  font-size: 14px;
  line-height: 20px;
  color: #333;
  border: 1px solid #ccc;
  border-radius: 0;
  box-sizing: border-box;
  margin: 0 0 10px;
  resize: both;
}

.ss-table-decision-form .errorlist {
  margin: 6px 0 4px;
}

.ss-table-decision-form__buttons {
  display: block;
  margin-top: 0;
}

.ss-table-decision-form__button {
  display: inline-block;
  padding: 4px 12px;
  margin: 0;
  color: #333;
  text-align: center;
  text-shadow: 0 1px 1px rgba(255, 255, 255, 0.75);
  font-size: 14px;
  line-height: 20px;
  white-space: pre;
  cursor: pointer;
  border: 1px solid #bbb;
  border-bottom-color: #a2a2a2;
  border-radius: 4px;
  background-color: #f5f5f5;
  background-image: linear-gradient(to bottom, #fff, #e6e6e6);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.2);
}

.ss-table-decision-form__button:hover {
  background-image: linear-gradient(to bottom, #f8f8f8, #d9d9d9);
}

.ss-table-decision-form__button:focus {
  outline: 1px dotted #333;
  outline-offset: 2px;
}

.ss-table-decision-form__button--reject {
  color: #fff;
  text-shadow: 0 -1px 0 rgba(0, 0, 0, 0.25);
  border-color: #0044cc #0044cc #002a80;
  background-color: #006dcc;
  background-image: linear-gradient(to bottom, #08c, #04c);
}

.ss-table-decision-form__button--reject:hover {
  background-image: linear-gradient(to bottom, #07b, #03b);
}
</style>
