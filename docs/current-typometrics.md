# How the current typometrics works (as of 2026-08)

Analysis of the live site <https://typometrics.elizia.net/#/> so that grugrutyp can
replace it without losing functionality.

## 1. Deployment topology

```
                  typometrics.elizia.net:443  (nginx)
                  ├── /                    → /home/typometrics/quasartypometrics/dist/spa   (static SPA)
                  ├── /typometricsapp/     → uwsgi_pass 127.0.0.1:7001                      (Django)
                  └── /menzerath           → /home/typometrics/menzerath                    (static html)
```

* nginx vhost: `/etc/nginx/sites-available/typometrics`
* Django is run by the systemd unit `typometrics-uwsgi.service`, config
  `/home/typometrics/djangotypometrics/typometricsdjango.ini`, socket on port 7001.
* Frontend built artefacts are committed under `quasartypometrics/dist/spa`; nginx serves
  them directly. `try_files $uri $uri/ =404` — note there is **no** SPA fallback to
  `index.html`, which is why the app uses hash routing (`/#/`).

## 2. The three code bases

| directory | role | state |
|---|---|---|
| `datapreparation/` | offline: CoNLL-U → `*.tsv` measure tables | Python 3.8-era, multiprocessing, last touched 2020 |
| `djangotypometrics/` | HTTP API over the `.tsv` tables | Django + DRF, pandas in module scope |
| `quasartypometrics/` | SPA: pickers + chart.js scatter plot | Quasar 1 / Vue 2 — end of life |

There is a **fourth**, undocumented source of numbers: several tables in
`*-analysis/` (`flexibility_rel.tsv`, `head_initiality_comb.tsv`, `bak_vs_typo.tsv`,
`abc.languages.*_typometricsformat.tsv`, `boot_*.tsv`) are **not** produced by
`datapreparation/statConll.py`. They were produced by other scripts that are not in
this tree. See `measures-mapping.md` §4.

## 3. Data model: everything is a language × measure matrix

Every measure lives in one TSV whose **rows are languages** (not treebanks — treebanks
of the same language are merged, see `getAllConllFiles(groupByLanguage=True)`) and whose
**columns are the "options"** of that measure.

```
name      appos     cc        comp      comp:obj  ...
Abaza     nan       -5.25     -1.32031  -1.37864
Afrikaans 3.44444   1.89836   1.48943   0.7823
```

The API is a thin pandas wrapper over these:

| endpoint | file | what it does |
|---|---|---|
| `GET  /typometricsapp/types/` | `views.types` | list of measure names = keys of `dict_data` |
| `POST /typometricsapp/typoptions/` | `views.typoptions` | column names of one measure |
| `POST /typometricsapp/typo/` | `views.typo` → `tsv2json.tsv2jsonNew` | the actual data points |
| `POST /typometricsapp/graph/` | `similarGraph.myClosestGraph` | DTW-based "most similar plot" |
| `POST /typometricsapp/graphParam/` | `similarGraph.graphParam` | decode a plot name back to (type, axis) |
| `PUT  /typometricsapp/scheme/` | `views.changeScheme` | flip the global SUD/UD state |

### Measure registry

From `typometricsapp/tsv2json.py`, `version_corpus = '2.12'`:

```python
dict_data_ud = {
  'menzerath':          '/abc.languages.v2.12_{sud|ud}_typometricsformat.tsv',
  'head-initiality':    '/head_initiality_comb.tsv'      (sud) | '/positive-direction.tsv' (ud),
  'head-initiality-cfc':'/direction-cfc_extend.tsv'      (sud) | '/posdircfc.tsv'          (ud),
  'distance':           '/f-dist.tsv',
  'distance-abs':       '/f-dist-abs.tsv',
  'distance-cfc':       '/cfc-dist.tsv',
  'distribution':       '/f.tsv',
  'treeHeight':         '/height.tsv',
  'freq-cfc':           '/distribution-cfc_extend.tsv'   (sud) | '/cfc.tsv'                (ud),
}
# SUD only, additionally:
flex_dict = {
  'flexibility':        '/flexibility_rel.tsv',
  'flexibility-cfc':    '/flexibility_cfc_all.tsv',
  'flex_compare_Bakker':'/bak_vs_typo.tsv',
}
```

`freq-cfc` is loaded but removed from the public type list (`gettypes()`); it is used
internally to derive occurrence counts for the min-occurrence filter.

## 4. What `tsv2jsonNew` actually computes

Signature: `tsv2jsonNew(axtypes, ax, axminocc, dim)`.

1. For each dimension `d`, take the single column `ax[d]` from the frame `dfs[axtypes[d]]`
   and `pd.concat` them side by side. So an (x, y) point for a language is just two cells
   from two (possibly different) measure tables.
2. **Min-occurrence filtering.** The frequency tables carry percentages, not counts, so
   the code reconstructs counts as `f.tsv[col] * f.tsv['total']` (or the cfc equivalent)
   and drops languages below `axminocc`. Menzerath tables carry real `nb_*` columns.
3. Drop rows with NaN in any dimension.
4. Emit one chart.js dataset per language, colour and point style from the language's
   genus via `groupColors` / `groupMarkers` keyed by `languageGroups.tsv`.
5. Return axis min/max rounded to a "nice" divisor.

**Consequence for grugrutyp:** the entire front end contract is
`language → (x, y) + colour + marker`. Anything that can produce a number per language
per query can be dropped straight into the same plot.

## 5. Frontend

* `src/boot/backend-api.js` — axios instance, base URL `https://typometrics.elizia.net/typometricsapp/`,
  `Content-Type: multipart/form-data` (!), 60 s timeout.
* `src/pages/Index.vue` (1230 lines) — the whole app: measure/axis selectors, min-occurrence
  sliders, 1-D vs 2-D toggle, SUD/UD switch, chart.js bubble chart, language-family legend.
* `src/pages/Presentation.vue` (665 lines) — static explanation of each measure, with the
  PNG figures in `src/assets/`. **This text is the only real documentation of what the
  measures mean and must be carried over.**
* `src/Chart.js` — a vendored 16k-line chart.js.

## 6. Known limitations that grugrutyp should fix

1. **`setScheme` mutates a module-global.** `dfs = dfsSUD` is process-wide state flipped by
   a `PUT`. With more than one uwsgi worker, user A's UD switch changes user B's results.
   The scheme must become a per-request parameter.
2. **Treebanks are merged into languages.** You cannot see that
   `SUD_French-GSD` and `SUD_French-ParTUT` disagree. Treebank-level granularity is a
   prerequisite for the "test a new treebank's quality" goal in `ideas.md`.
3. **The measure set is closed.** Adding a measure means writing a new script, a new TSV, and
   a new entry in `dict_data`. This is exactly what the query-pair mechanism removes.
4. **Frozen at UD/SUD 2.12** while 2.18 is current, and no scripted way to move forward.
5. **Vue 2 / Quasar 1 are end of life**; `node_modules` is partly committed
   (`old node_modules/`), the build is not reproducible.
6. **Provenance is lost.** For half the tables nobody can say which script made them.
