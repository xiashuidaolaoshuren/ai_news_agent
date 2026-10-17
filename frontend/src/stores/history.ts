import { computed, ref, shallowRef } from 'vue'
import { defineStore } from 'pinia'

import type {
  HistoryItemShowOut,
  HistorySearchResultOut,
} from '@/api/generated/types.gen'
import {
  searchHistoryApiV1HistorySearchGet,
  showHistoryApiV1HistoryHistoricalItemRefGet,
} from '@/api/generated/sdk.gen'
import { setupApiClient } from '@/api/setupClient'
import { useComposerStore } from '@/stores/composer'
import {
  EMPTY_HISTORY_FILTERS,
  toHistoryPanelVm,
  toHistoryQuery,
  toOpenedVm,
  type HistoryFilters,
  type HistoryMatchVm,
  type HistoryPanelVm,
  type HistorySearchQuery,
  type HistoryStatus,
  type OpenedItemVm,
  type OpenedResultInput,
} from '@/vm'

/** Server calls and ambient services the history panel needs, injected for tests. */
export interface HistoryDeps {
  search(query: HistorySearchQuery): Promise<HistorySearchResultOut>
  show(token: string): Promise<HistoryItemShowOut>
  /** "Ask in chat" on an opened entry; the composer owns the wording. */
  prefillFollowUp(title: string): void
  schedule(handler: () => void, ms: number): unknown
  cancel(handle: unknown): void
}

/** How long typing settles before the panel searches. */
export const HISTORY_DEBOUNCE_MS = 250

/** Shown when a failure arrives without a usable message. */
export const SEARCH_FAILED = 'History search failed. Try again.'

/** Shown when opening a historical item fails without a usable message. */
export const OPEN_FAILED = 'Could not open this result.'

/**
 * The server's `detail` for a rejected request. FastAPI puts the safe message
 * there (a 400 uses the message itself), so it can go straight into the panel.
 */
function detailMessage(error: unknown, status: number): string {
  const detail = (error as { detail?: unknown } | undefined)?.detail
  if (typeof detail === 'string' && detail.trim() !== '') {
    return detail
  }
  return `History request failed with status ${status}`
}

/** Production dependencies wired to the generated client and the composer. */
export function defaultHistoryDeps(): HistoryDeps {
  setupApiClient()
  const composer = useComposerStore()
  return {
    async search(query): Promise<HistorySearchResultOut> {
      const result = await searchHistoryApiV1HistorySearchGet({ query })
      if (result.data === undefined) {
        throw new Error(detailMessage(result.error, result.response?.status ?? 0))
      }
      return result.data
    },
    async show(token): Promise<HistoryItemShowOut> {
      const result = await showHistoryApiV1HistoryHistoricalItemRefGet({
        path: { historical_item_ref: token },
      })
      if (result.data === undefined) {
        throw new Error(detailMessage(result.error, result.response?.status ?? 0))
      }
      return result.data
    },
    prefillFollowUp: (title) => {
      composer.prefillFollowUp(title)
    },
    schedule: (handler, ms) => setTimeout(handler, ms),
    cancel: (handle) => {
      clearTimeout(handle as ReturnType<typeof setTimeout>)
    },
  }
}

/** Reactive history panel state: the filter draft, the results, and the opened item. */
export function createHistoryController(deps: HistoryDeps) {
  const filters = ref<HistoryFilters>({ ...EMPTY_HISTORY_FILTERS })
  const status = ref<HistoryStatus>('idle')
  const result = shallowRef<HistorySearchResultOut | null>(null)
  const error = ref<string | null>(null)
  const openedMatch = shallowRef<HistoryMatchVm | null>(null)
  const openedItem = shallowRef<OpenedItemVm | null>(null)
  const openedStatus = ref<HistoryStatus>('idle')
  const openedError = ref<string | null>(null)
  let pending: unknown = null
  /** Bumped for every request, so a slow answer for an old query is dropped. */
  let seq = 0
  /** The same guard for the show call behind an opened result. */
  let openSeq = 0

  /** Drop the scheduled search, if one is waiting. */
  function cancelPending(): void {
    if (pending !== null) {
      deps.cancel(pending)
      pending = null
    }
  }

  async function run(): Promise<void> {
    pending = null
    const query = toHistoryQuery(filters.value)
    if (query === null) {
      return
    }
    seq += 1
    const current = seq
    status.value = 'loading'
    error.value = null
    try {
      const out = await deps.search(query)
      // A slower request for an older query must not overwrite the newer one.
      if (current !== seq) {
        return
      }
      result.value = out
      status.value = 'ready'
    } catch (caught) {
      if (current !== seq) {
        return
      }
      result.value = null
      status.value = 'error'
      error.value =
        caught instanceof Error && caught.message !== '' ? caught.message : SEARCH_FAILED
    }
  }

  /** Search the same filters again after a failure. */
  function retry(): void {
    cancelPending()
    void run()
  }

  /** Merge one filter change in, then search once the typing settles. */
  function setFilters(next: Partial<HistoryFilters>): void {
    filters.value = { ...filters.value, ...next }
    if (toHistoryQuery(filters.value) === null) {
      cancelPending()
      // No criterion means no results: drop the old rows and any answer in flight.
      seq += 1
      result.value = null
      error.value = null
      status.value = 'idle'
      return
    }
    cancelPending()
    status.value = 'loading'
    pending = deps.schedule(() => {
      void run()
    }, HISTORY_DEBOUNCE_MS)
  }

  /** Reset every filter, which returns the panel to its idle prompt. */
  function clearFilters(): void {
    closeResult()
    setFilters({ ...EMPTY_HISTORY_FILTERS })
  }

  /** Fetch one historical item for the opened block. */
  async function loadOpened(token: string): Promise<void> {
    openSeq += 1
    const current = openSeq
    openedStatus.value = 'loading'
    openedError.value = null
    try {
      const out = await deps.show(token)
      if (current !== openSeq) {
        return
      }
      openedItem.value = toOpenedVm(out)
      openedStatus.value = 'ready'
    } catch (caught) {
      if (current !== openSeq) {
        return
      }
      openedItem.value = null
      openedStatus.value = 'error'
      openedError.value =
        caught instanceof Error && caught.message !== '' ? caught.message : OPEN_FAILED
    }
  }

  /**
   * Open one result above the list. Reading history never changes the
   * conversation, so this touches nothing but the panel's own state.
   */
  function open(match: HistoryMatchVm): void {
    openedMatch.value = match
    openedItem.value = null
    void loadOpened(match.token)
  }

  /** Close the opened result, dropping any answer still on its way back. */
  function closeResult(): void {
    openSeq += 1
    openedMatch.value = null
    openedItem.value = null
    openedStatus.value = 'idle'
    openedError.value = null
  }

  /** "Ask in chat" on the opened entry: hand the title to the composer. */
  function askInChat(title: string): void {
    deps.prefillFollowUp(title)
  }

  const openedInput = computed<OpenedResultInput | null>(() => {
    const match = openedMatch.value
    return match === null
      ? null
      : {
          match,
          status: openedStatus.value,
          item: openedItem.value,
          error: openedError.value,
        }
  })

  const vm = computed<HistoryPanelVm>(() =>
    toHistoryPanelVm({
      filters: filters.value,
      status: status.value,
      result: result.value,
      error: error.value,
      opened: openedInput.value,
    }),
  )

  return { vm, setFilters, clearFilters, retry, open, closeResult, askInChat }
}

export type HistoryController = ReturnType<typeof createHistoryController>

export const useHistoryStore = defineStore('history', () =>
  createHistoryController(defaultHistoryDeps()),
)
