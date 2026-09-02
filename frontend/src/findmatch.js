// The find-language matcher, shared by the toolbar find box, the plot's rings and
// labels, and the chat's clickable names: case-insensitive substring over the language
// name (underscores read as spaces, so "ancient greek" finds Ancient_Greek) OR over its
// group label — "Slavic" rings every Slavic language even though no language name
// contains it.
export function matchesFind(language, label, query) {
  const needle = (query || '').trim().toLowerCase().replace(/_/g, ' ')
  if (!needle) return false
  return (
    (language || '').toLowerCase().replace(/_/g, ' ').includes(needle) ||
    (label || '').toLowerCase().includes(needle)
  )
}
