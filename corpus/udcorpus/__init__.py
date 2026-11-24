"""udcorpus -- UD/SUD treebank ingestion and language metadata, standard library only.

Modules:

* `config`     -- where the data, the metadata and the release version are
* `conllu`     -- streaming CoNLL-U reader, deprel decomposition, tree properties
* `treebanks`  -- the treebanks of a release, their files, the per-language selection
* `languages`  -- language identity (ISO code first, name second), groupings, colours
* `audit`      -- what a new release did to the language configuration
* `stats`      -- Wilson interval, sample rate
* `measure`    -- a reference measure (head-initiality) computed from the files alone

Start with `corpus/README.md`.
"""

__version__ = "1.0"
