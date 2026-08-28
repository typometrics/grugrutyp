<template>
  <div class="dep-tree-wrapper">
    <reactive-dep-tree
      :key="shownFeatures"
      :conll="highlighted"
      :shown-features="effectiveShownFeatures"
      interactive="false"
    />
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  conllu: { type: String, required: true },
  // 1-based word positions that the Grew request matched.
  matched: { type: Array, default: () => [] },
  // Comma-separated CoNLL-U columns to draw, e.g. "FORM,LEMMA,UPOS,DEPREL".
  // Empty string means "show everything".
  shownFeatures: { type: String, default: 'FORM,LEMMA,UPOS,DEPREL' },
})

const HIGHLIGHT = 'highlight=red'

/**
 * `MISC.highlight` has to stay in the shown-features list or the renderer will not colour
 * the matched words -- but it is only a marker, never something to read, so it is
 * appended silently rather than offered as a choice.
 */
const effectiveShownFeatures = computed(() =>
  props.shownFeatures ? `${props.shownFeatures},MISC.highlight` : '',
)

/**
 * reactive-dep-tree colours a node when its MISC column contains `highlight=red`, so
 * marking the matched words is a matter of rewriting MISC on those lines.
 *
 * Index 0 is Grew's virtual root node `__0__`, which has no CoNLL-U line -- it is
 * dropped rather than shifted onto word 0, which does not exist.
 */
const highlighted = computed(() => {
  const wanted = new Set(props.matched.filter((i) => i > 0))
  if (wanted.size === 0) return props.conllu

  return props.conllu
    .split('\n')
    .map((line) => {
      if (line.startsWith('#') || !line.trim()) return line
      const cols = line.split('\t')
      if (cols.length !== 10) return line
      // Skip multiword-token and empty-node lines: they carry no position we match on.
      if (!/^\d+$/.test(cols[0])) return line
      if (!wanted.has(Number(cols[0]))) return line
      cols[9] = cols[9] === '_' || !cols[9] ? HIGHLIGHT : `${cols[9]}|${HIGHLIGHT}`
      return cols.join('\t')
    })
    .join('\n')
})
</script>

<style scoped>
/* Trees are as wide as the sentence is long; scroll inside the card rather than making
   the page scroll sideways. */
.dep-tree-wrapper {
  width: 100%;
  overflow-x: auto;
  padding: 4px 8px 8px;
}
</style>
