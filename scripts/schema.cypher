// grugrutyp Neo4j schema -- see docs/neo4j-encoding.md section 2.
//
// Property-based encoding (Deworetzki & Ljunglof), with four deviations:
//   1. explicit (:Word)-[:IN_SENTENCE]->(:Sentence)  -- their own section 6.2 optimisation
//   2. Word.idx integer position, so `<<` is an integer comparison not a path traversal
//   3. DEPREL edges carry the decomposed label (rel_1/rel_2/rel_deep), because in SUD a
//      dependency label is a feature structure, not an atom.
//   4. Grew's virtual root node `__0__` is materialised as a Word with idx = 0, and the
//      root dependency is a real DEPREL edge from it. Without it our counts are short by
//      one node and one edge per sentence relative to Grew.

CREATE CONSTRAINT treebank_unique IF NOT EXISTS
  FOR (t:Treebank) REQUIRE (t.name, t.version) IS UNIQUE;

CREATE CONSTRAINT sentence_unique IF NOT EXISTS
  FOR (s:Sentence) REQUIRE (s.treebank, s.sent_id) IS UNIQUE;

CREATE CONSTRAINT word_unique IF NOT EXISTS
  FOR (w:Word) REQUIRE (w.treebank, w.sent_id, w.idx) IS UNIQUE;

// Every query is scoped to one treebank, so treebank is the leading key everywhere.
CREATE INDEX word_treebank IF NOT EXISTS FOR (w:Word) ON (w.treebank);
CREATE INDEX word_tb_upos  IF NOT EXISTS FOR (w:Word) ON (w.treebank, w.upos);
CREATE INDEX word_tb_lemma IF NOT EXISTS FOR (w:Word) ON (w.treebank, w.lemma);
CREATE INDEX word_tb_form  IF NOT EXISTS FOR (w:Word) ON (w.treebank, w.form);
CREATE INDEX sentence_treebank IF NOT EXISTS FOR (s:Sentence) ON (s.treebank);

CREATE INDEX deprel_full IF NOT EXISTS FOR ()-[r:DEPREL]-() ON (r.deprel);
CREATE INDEX deprel_rel1 IF NOT EXISTS FOR ()-[r:DEPREL]-() ON (r.rel_1);
