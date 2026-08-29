<template>
  <div ref="wrapper" class="dep-tree-wrapper">
    <reactive-dep-tree
      :key="shownFeatures"
      :conll="highlighted"
      :shown-features="effectiveShownFeatures"
      interactive="false"
    />
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'

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

const wrapper = ref(null)

/**
 * Long sentences scroll horizontally, and a match at word 40 of 60 was off-screen until
 * the reader went looking for it. The renderer is a web component, so instead of groping
 * through its shadow DOM for the red word, scroll proportionally: words are roughly
 * evenly spaced, so first-match-position over sentence-length is close enough to centre
 * the highlight.
 */
function scrollToMatch() {
  const el = wrapper.value
  const first = Math.min(...props.matched.filter((i) => i > 0))
  if (!el || !Number.isFinite(first)) return
  const words = props.conllu
    .split('\n')
    .filter((line) => /^\d+\t/.test(line)).length
  if (!words) return
  const overflow = el.scrollWidth - el.clientWidth
  if (overflow <= 0) return
  const target = ((first - 0.5) / words) * el.scrollWidth - el.clientWidth / 2
  el.scrollLeft = Math.max(0, Math.min(overflow, target))
}

// The component renders asynchronously; measure after it has had a frame to lay out,
// and once more a beat later in case the SVG was still growing at the first attempt.
const scrollSoon = () => {
  requestAnimationFrame(() => requestAnimationFrame(scrollToMatch))
  setTimeout(scrollToMatch, 300)
}
onMounted(scrollSoon)
watch(() => [props.conllu, props.shownFeatures], scrollSoon)
</script>

<style scoped>
/* Trees are as wide as the sentence is long; scroll inside the card rather than making
   the page scroll sideways. */
.dep-tree-wrapper {
  width: 100%;
  overflow-x: auto;
  padding: 4px 8px 8px;
  /* The tree renderer draws dark text; keep its panel light in dark mode too --
     trees are figures, like the plot. */
  background: #fff;
}
</style>
