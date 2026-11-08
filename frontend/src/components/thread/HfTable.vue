<script setup lang="ts">
import AppIcon from '@/components/ui/AppIcon.vue'
import AvatarTile from '@/components/thread/AvatarTile.vue'
import { riseStyle } from '@/lib/motion'
import type { EntryVm, RefVm } from '@/vm'

const props = defineProps<{
  entries: EntryVm[]
  digestId: number
  /** Set when the table arrived live, so each row reveals in turn. */
  animate?: boolean
  /** Where this table's rows start in the digest-wide stagger count. */
  startIndex?: number
}>()

const emit = defineEmits<{
  deepdive: [ref: RefVm]
  ask: [ref: RefVm]
  'goto-related': [ref: RefVm]
}>()

function rowStyle(index: number): string | undefined {
  return props.animate === true ? riseStyle((props.startIndex ?? 0) + index) : undefined
}

function rowRef(entry: EntryVm): RefVm {
  return {
    digestId: props.digestId,
    rank: entry.rank,
    title: entry.hf?.modelId ?? entry.title,
  }
}

function relatedRef(rank: number): RefVm {
  return {
    digestId: props.digestId,
    rank,
    title: `#${rank}`,
  }
}
</script>

<template>
  <div class="table-wrap">
    <table data-od-id="hf-comparison-table">
      <thead>
        <tr>
          <th scope="col">Rank</th>
          <th scope="col">Model</th>
          <th scope="col">Link</th>
          <th scope="col" class="r">Trending</th>
          <th scope="col" class="r">30-day downloads</th>
          <th scope="col" class="r">Likes</th>
          <th scope="col">Pipeline</th>
          <th scope="col">Variants</th>
          <th scope="col" class="acts">Actions</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="(entry, index) in props.entries"
          :key="entry.key"
          class="hf-row"
          :class="{ rise: props.animate === true }"
          :style="rowStyle(index)"
          :data-ref="`d${props.digestId}-${entry.rank}`"
          :data-od-id="`hf-row-${entry.rank}`"
        >
          <td class="mono muted">#{{ entry.rank }}</td>
          <td class="model">
            <span class="model-cell">
              <AvatarTile :avatar="entry.avatar" />
              <b>{{ entry.hf?.modelId ?? entry.title }}</b>
            </span>
          </td>
          <td>
            <a
              v-if="entry.url"
              class="ext"
              :href="entry.url"
              target="_blank"
              rel="noopener"
              :aria-label="`Open ${entry.hf?.modelId ?? entry.title} on Hugging Face`"
              >hf.co<AppIcon name="ext" /></a
            >
          </td>
          <td class="r num">{{ entry.hf?.trending ?? '—' }}</td>
          <td class="r num">{{ entry.hf?.downloads30d ?? '—' }}</td>
          <td class="r num">{{ entry.hf?.likes ?? '—' }}</td>
          <td>
            <span v-if="entry.hf?.pipeline" class="pill">{{ entry.hf.pipeline }}</span>
            <span v-else>—</span>
          </td>
          <td class="var">
            <template v-if="entry.hf?.baseModel || entry.hf?.variants.length">
              <span v-if="entry.hf?.baseModel" class="pill">{{ entry.hf.baseModel }}</span>
              <span v-for="variant in entry.hf?.variants" :key="variant.sourceId" class="var-item">
                {{ variant.title }}<br /><code>{{ variant.sourceId }}</code>
              </span>
            </template>
            <span v-else aria-label="None reported">—</span>
            <div
              v-if="entry.relatedRanks && entry.relatedRanks.length > 0"
              class="row-related"
            >
              <button
                v-for="relatedRank in entry.relatedRanks"
                :key="`hf-related-${relatedRank}`"
                type="button"
                class="chip rel-chip"
                :data-od-id="`related-${relatedRank}`"
                :aria-label="`Related: entry #${relatedRank} names the same model`"
                @click="emit('goto-related', relatedRef(relatedRank))"
              >
                Related: #{{ relatedRank }}
              </button>
            </div>
          </td>
          <td class="acts">
            <div class="row-acts">
              <button
                type="button"
                class="link-btn"
                :data-od-id="`deepdive-hf-${entry.rank}`"
                :aria-label="`Deep dive: ${rowRef(entry).title}`"
                @click="emit('deepdive', rowRef(entry))"
              >
                <AppIcon name="layers" />Deep dive
              </button>
              <button
                type="button"
                class="link-btn"
                :data-od-id="`followup-hf-${entry.rank}`"
                :aria-label="`Ask about this: ${rowRef(entry).title}`"
                @click="emit('ask', rowRef(entry))"
              >
                <AppIcon name="reply" />Ask about this
              </button>
            </div>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
  <div class="table-note">
    Trending score and downloads from the Hugging Face Hub API. “—” means no base model is
    declared.
  </div>
</template>

