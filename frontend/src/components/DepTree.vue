<template>
  <div ref="wrapper" class="dep-tree-wrapper">
    <reactive-dep-tree
      ref="tree"
      :key="shownFeatures"
      :conll="highlighted"
      :shown-features="effectiveShownFeatures"
      interactive="false"
    />
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useQuasar } from 'quasar'

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
const tree = ref(null)
const $q = useQuasar()

// ------------------------------------------------------------------- dark-mode trees
//
// The renderer is a web component with an OPEN shadow root, so no page CSS -- scoped,
// :deep(), or global -- ever reaches its SVG. (An earlier attempt styled it from
// outside; the rules sat dead in the stylesheet while dark mode showed the light
// palette's black-and-purple on a dark card.) The one door a shadow root leaves open is
// a <style> element injected INSIDE it, which is what this does, gated on the theme.
// The colours are the library's own dark stylesheet (dependencytreejs' DARK theme),
// which reactive-dep-tree 1.0.1 ships but hard-selects LIGHT at load.
const DARK_TREE_CSS = `
  .FORM, .LEMMA { fill: #e6e2e2; }
  .UPOS, .DEPREL, .DEPRELenhanced { fill: #ea6ff4; }
  .FEATS, .MISC, .XPOS { fill: #a47da3; }
  .arrowhead { stroke: #e6e2e2; fill: none; }
  .curve { stroke: #e6e2e2; }
  .glossy { fill: #e6e2e2; }
`

function applyTreeTheme() {
  const root = tree.value?.shadowRoot
  if (!root) return
  let sheet = root.querySelector('style[data-grugrutyp-dark]')
  if ($q.dark.isActive) {
    if (!sheet) {
      sheet = document.createElement('style')
      sheet.setAttribute('data-grugrutyp-dark', '')
      root.appendChild(sheet)
    }
    sheet.textContent = DARK_TREE_CSS
  } else if (sheet) {
    sheet.remove()
  }
}

// Re-applied when the theme flips and when :key replaces the element (a new element is a
// new shadow root, without the injected sheet). nextTick so the replacement exists.
watch(
  () => [$q.dark.isActive, props.shownFeatures, props.conllu],
  () => nextTick(applyTreeTheme),
)

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
// then twice more as the SVG grows. Triggered when the tree scrolls INTO VIEW rather
// than at mount: for a hit further down the page the SVG often was not laid out yet at
// mount time, so the early attempts measured a zero-overflow wrapper and gave up --
// which is why the scroll appeared not to work at all.
const scrollSoon = () => {
  requestAnimationFrame(() => requestAnimationFrame(scrollToMatch))
  setTimeout(scrollToMatch, 400)
  setTimeout(scrollToMatch, 1200)
}
let visibility = null
onMounted(() => {
  applyTreeTheme()
  // The custom element may upgrade a beat after Vue inserts it, in which case the first
  // call found no shadowRoot yet. One late retry costs nothing and closes that window.
  setTimeout(applyTreeTheme, 300)
  if (typeof IntersectionObserver === 'undefined' || !wrapper.value) {
    scrollSoon()
    return
  }
  visibility = new IntersectionObserver((entries) => {
    if (entries.some((entry) => entry.isIntersecting)) {
      scrollSoon()
      visibility.disconnect()
      visibility = null
    }
  })
  visibility.observe(wrapper.value)
})
onBeforeUnmount(() => visibility && visibility.disconnect())
watch(() => [props.conllu, props.shownFeatures], scrollSoon)
</script>

<style scoped>
/* Trees are as wide as the sentence is long; scroll inside the card rather than making
   the page scroll sideways. */
.dep-tree-wrapper {
  width: 100%;
  overflow-x: auto;
  padding: 4px 8px 8px;
  background: #fff;
  /* Pinned in BOTH themes: the library's popup menu (Export SVG…) draws a light
     panel but inherits the page text colour, so it must stay dark. The SVG below
     is unaffected -- its text uses fill, not color. */
  color: #1d1d1d;
}

/* The SVG's own dark colours are injected into the component's shadow root from the
   script above -- page CSS, :deep() included, cannot cross a shadow boundary. Only the
   wrapper (a normal element) is themed here. */
.body--dark .dep-tree-wrapper {
  background: #1e1e1e;
}
</style>
