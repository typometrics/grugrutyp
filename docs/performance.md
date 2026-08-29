# Why a full plot takes minutes, and what actually helps

Answers Kim's question of 2026-08-29: *"it's very slow: 352/352 treebanks · 160 languages
· 675.4s … what could be done about it? moving to execution by language instead of by
treebank? parallel execution, multiple db? approximate results quickly? different
hardware? gpu?"*

Everything below is measured on this box, against the complete 2.18 corpus.

## 1. The finding, in one line

**The database is on 7200 RPM spinning disks and does not fit in RAM.** Nothing else in
the list matters until that does.

```
$ cat /sys/block/sda/queue/rotational   ->  1
$ cat /sys/block/sda/device/model       ->  HGST HUS726020AL     (2 TB, 7200 rpm, RAID1)
$ iostat -x md3
  md3   r/s 160   %util 100.00   aqu-sz 10613
```

100 % utilisation with a queue depth of **ten thousand**, while Neo4j sat at 1.7 % CPU. A
graph database is pointer-chasing: almost every read is random, and a 7200 rpm mirror
serves ~150 random IOPS no matter how many cores or workers you throw at it.

The consequence, measured on one query over `SUD_English-GUM`:

| | time |
|---|---|
| pages resident in RAM | **0.6 – 2.0 s** |
| pages read from disk | **55 s** |

and over a 60-treebank slice, asking a *different* question each time:

| | time |
|---|---|
| first pass (cold) | **17.8 s** |
| later passes (same treebanks, different relation) | **1.1 – 2.4 s** |

Warm performance is unchanged from when the database held 40 treebanks. Nothing regressed.
The corpus simply outgrew the cache.

## 2. Kim's options, assessed

| option | verdict |
|---|---|
| **GPU** | **No.** There is no arithmetic here to offload — it is pointer-chasing and disk seeks. |
| **More parallelism** | **No, it hurts.** Eight workers against a 150-IOPS device is what produced the 10 613-deep queue. |
| **Multiple databases** | **No.** On one box they compete for the same RAM and the same spindles. |
| **By language, not by treebank** | **No.** It scans identical bytes; it merges 352 queries into 193 larger ones and saves only round-trip overhead, which is not the bottleneck. It would also cost the per-treebank cache and the per-treebank detail Phase 5 needs. |
| **Approximate quickly** | **Partly there, and worth extending** — see §4. |
| **Different hardware** | **Yes, and this is the one that matters** — see §3. |

## 3. What the 73 GB actually is

```
38 G  schema/                      <- the indexes
17 G  neostore.propertystore.db
9.8 G neostore.propertystore.db.strings
7.8 G neostore.relationshipstore.db
1.3 G neostore.nodestore.db
```

**Half the database is indexes.** Broken down:

| index | size | needed by a measure query? |
|---|---|---|
| `word_unique` (treebank, sent_id, idx) | **9.3 G** | **no** — an import-time uniqueness constraint |
| `word_tb_form` (treebank, form) | 5.8 G | no — only `[form="x"]` lookups |
| `word_tb_upos` (treebank, upos) | 5.8 G | yes |
| `word_treebank` (treebank) | 5.3 G | yes |
| `word_tb_lemma` (treebank, lemma) | 4.8 G | no — only `[lemma="x"]` lookups |
| `deprel_full` / `deprel_rel1` | 5.7 G | yes |
| `sentence_treebank` + `sent_bucket` + `sentence_unique` | 1.1 G | yes |

The hot set for a measure query — `sentence_treebank`, `word_treebank`, the relationship
store, the node store, and `idx` — is roughly **15 GB**. That *would* fit in the 18 GB page
cache, if the 20 GB of indexes nothing queries were not competing for the same pages.

### Ranked, cheapest first

1. **Drop `word_unique` (9.3 GB, free).** It is a uniqueness constraint, not a query index.
   The importer is delete-then-insert per treebank, so it cannot create duplicates, and
   `tests/test_import.py` verifies node counts against the files independently. Nothing in
   the query path can use a three-column index whose first column is the treebank string.
   ```cypher
   DROP CONSTRAINT word_unique
   ```
2. **Drop `word_tb_form` and `word_tb_lemma` (10.6 GB)** *if* form/lemma lookups are rare.
   They serve `[form="x"]` and `[lemma="x"]` in the search tab. Consider keeping lemma and
   dropping form.
3. **Replace the `treebank` string with a short integer id.** Every one of the 80 M `Word`
   nodes stores `"SUD_English-GUM"` as a string, and every index above repeats it per
   entry. This is most of the 9.8 GB string store *and* much of the index bulk. It is a
   schema change plus a re-import, so it is the biggest job here — but it is also the
   change that would let the whole working set sit in RAM.
4. **An SSD or NVMe for the Neo4j store.** ~100× the random IOPS. If the store cannot be
   made to fit in RAM, this is the answer, and it is cheaper than 128 GB of RAM.
5. **More RAM.** 96–128 GB would cache the store as it stands, no schema work needed.

## 4. What has already been done

* **Page cache 4 GB → 18 GB** (2026-08-29). It was sized when the database was 14 GB and
  never revisited after the full import took it to 73 GB. Heap dropped 8 GB → 6 GB to pay
  for it; this workload returns one row per query and never needed 8 GB of heap.
* **Two queries per axis → one.** `count(CASE WHEN <Q> THEN 1 END)` gets `#(S)` and
  `#(S∧Q)` from a single scope traversal. The scope is the expensive half, so the second
  statement had been re-doing work already done. Verified identical on 10 scope/response
  combinations; warm, 1.19–1.85× faster.
* **Retry on transient failures.** Kim's run reported `1 treebank(s) failed:
  SUD_Arabic-PADT` with no retry — a 66 s query on a saturated disk hitting the
  transaction timeout. The runner now retries 3× with backoff, but only for timeouts,
  unavailability and deadlocks; a syntax error still fails immediately.
* **Smallest treebank first**, so the plot fills in from the first second rather than
  waiting on Czech and German.

## 5. What to do next, given the hardware

The escalation rule is the remaining self-inflicted cost: **71 of Kim's 352 treebanks
escalated to the full corpus**, which undoes the sampling for precisely the expensive
ones. Two changes worth making:

* **Progressive refinement.** Show the sampled value immediately and refine escalated
  treebanks in a second pass, so the plot is complete in seconds and sharpens afterwards.
  This fits the SSE design and needs no new machinery.
* **A precompute pass.** The corpus is static between releases. Running the preset
  measures overnight fills the cache, and every preset plot is then instant. This is the
  honest answer to "approximate results quickly": on this hardware, do not approximate —
  precompute.
