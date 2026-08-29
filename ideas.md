# ideas for grugrutype

* new version of https://typometrics.elizia.net/#/
* techno: backend fastapi, frontend quasar, database maybe neo4j: graph grammar for the storage of the ud/sud treebanks
* analyze how data intake is done in datapreparation/. download new data from here: 
    * sud https://surfacesyntacticud.org/data/ new versions should be taken by script and deployed recent: https://grew.fr/download/sud-treebanks-v2.18.tgz
    * ud https://universaldependencies.org/download.html curl -o "ud-treebanks-v2.18.tgz" "https://lindat.mff.cuni.cz/repository/server/api/core/bitstreams/handle/11234/1-6149/ud-treebanks-v2.18.tgz" -o "ud-documentation-v2.18.tgz" "https://lindat.mff.cuni.cz/repository/server/api/core/bitstreams/handle/11234/1-6149/ud-documentation-v2.18.tgz" -o "ud-tools-v2.18.tgz" "https://lindat.mff.cuni.cz/repository/server/api/core/bitstreams/handle/11234/1-6149/ud-tools-v2.18.tgz"
* understand what https://typometrics.elizia.net/#/ does now:
    * pre-computed queries have values for each treebank
    * values can be plotted simply in a one-dimensional graph or in a 2 dim scatter plot
* goal: 
    * allow the user to make a grew query, and then an additional subquery. the percentage of responses in the subquery will be the value for the language --> 1 dimensional measures on the fly
    * have this twice: for two different pairs of grew queries --> 2 dim scatter plot
    * for the moment don't erase the config of the current typometrics, but build this in a subfolder. replacement only after thorough testing.
* read papers in docs/
    * affichage des arbres individuel avec https://github.com/kirianguiller/reactive-dep-tree
    * Graph Databases for Fast Queries in UD Treebanks, Niklas Deworetzki, Peter Ljunglöf: typometrics/grugrutyp/docs/Graph Databases for Fast Queries in UD Treebanks.pdf
    * the query pair is inspired from https://autogramm.github.io/grex-lrec-coling-2024/ code: https://github.com/FilippoC/grex-lrec-coling-2024 paper: /home/typometrics/grugrutyp/docs/Sparse Logistic Regression with High-order Features for Automatic Grammar Rule Extraction from Treebanks .pdf
    * to understand how grew queries work also look at https://grew.fr/doc/graph/
    * transcribe any understanding of online resources into md files in the docs/ folder.

* make a plan.md and then a detailed plan on how to build that
* make a setup.md on how to setup this process:
    * long time running on this machine, how to connect and get this running?
    * orchestrated by opus 5, but using cheaper models for coding.
    * should i put the api access codes such as for deepseek into an .env file? where? 
    * do the other models need description to help opus decide which model to use for what? how to do that?

* ask many question to specify the goal if not clear
* make a detailed todo.md with all the steps you can imagine that need to be done.
* first intermediate step: build something like https://universal.grew.fr where one can put a grew query and a language in ud or sud, and show graphically the matching trees
* analyze which of the pre-computed measures we have today in typometrics can be reproduced by grew queries. analyze what to do about this.
* one long term application would be that the tool also allows:
    * to test new treebanks on their quality, by comparing them to existing treebanks in the same language, and to existing treebanks in other neighbor languages.
    * to detect lists of phenomena that are strange about a specific language with statistical measures and ideas to report this in a paper on comparative syntax.

# new ideas
* in the search panel, the tree should be scrolled to the first matching token
* the search panel should have the possibility to search over a whole language, or even a manual selection of treebanks. 
* the information page should also have a section/tab that explains technical details and for example the error bars.
* when switching from sud to ud in the typometrics tab, the plot disappears, and then the query is recomputed on UD. that rarely makes sense. we should wait for the user to click. however, it's not clear when clicking actually makes sense.  maybe the plot could have some kind of check mark or simply be grayed out until something in any filed changes that makes it reasonable to recompute?




* build a login system for the site. maybe with google/github login?
    * goal1: admin for updating the database to a new ud version
        *  decide on grouping of new languages, short language names etc. possibly with an LLM
    * goal2 allow for users to find their queries again
    * goal3 allow for some priviledged users to enter their queries in plain text that is translated into 1dmin or 2 dim grew queries
* log user queries, make a view accessible to the admin(s)

# clustering and the typometrics tab (note, 2026-08-29)
The search tab now has grew.fr-style clustering (a key like `X.upos` or `e.label` returns
a count per value, computed in the database). For the typometrics tab this suggests:
* a "facet by" key on an axis would generate a *family* of measures in one stroke — one
  strip per value (e.g. subject direction faceted by governor POS), i.e. small multiples.
  The per-(treebank, value) counts the cluster mode returns are exactly the raw material;
  what is missing is the fan-out/caching plumbing and a small-multiples plot.
* "whether"-clustering on grew.fr is precisely our scope/response pair — the typometrics
  tab *is* the whether-clustering of the corpus, plotted. Nothing to add there.
