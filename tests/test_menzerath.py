"""The Menzerath features (docs/menzerath.md): computed once, written by both the
importer and the backfill, so one hand-checked tree pins the definition down."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from grugrutyp.conllu import menzerath_features, sentence_from_conllu

#   the(1) -> dog(3), big(2) -> dog(3), dog(3) -> barked(4), barked(4) = root,
#   loudly(5) -> barked(4), .(6) -> barked(4)
CONLLU = """# sent_id = test-1
# text = the big dog barked loudly .
1\tthe\tthe\tDET\t_\t_\t3\tdet\t_\t_
2\tbig\tbig\tADJ\t_\t_\t3\tamod\t_\t_
3\tdog\tdog\tNOUN\t_\t_\t4\tnsubj\t_\t_
4\tbarked\tbark\tVERB\t_\t_\t0\troot\t_\t_
5\tloudly\tloudly\tADV\t_\t_\t4\tadvmod\t_\t_
6\t.\t.\tPUNCT\t_\t_\t4\tpunct\t_\t_
"""


def test_menzerath_features_on_a_hand_checked_tree():
    sentence = sentence_from_conllu(CONLLU)
    feats = menzerath_features(sentence)

    assert feats[1] == {"subtree_size": 1, "n_children": 0, "n_left": 0, "n_right": 0}
    assert feats[3] == {"subtree_size": 3, "n_children": 2, "n_left": 2, "n_right": 0}
    # the root verb's projection is the whole sentence; one dependent left, two right
    assert feats[4] == {"subtree_size": 6, "n_children": 3, "n_left": 1, "n_right": 2}
    assert feats[6] == {"subtree_size": 1, "n_children": 0, "n_left": 0, "n_right": 0}


def test_a_cycle_does_not_hang_or_explode():
    # 1 and 2 point at each other -- malformed, but present in real treebanks.
    broken = "# sent_id = cyc\n1\ta\ta\tX\t_\t_\t2\tdep\t_\t_\n2\tb\tb\tX\t_\t_\t1\tdep\t_\t_\n"
    feats = menzerath_features(sentence_from_conllu(broken))
    assert set(feats) == {1, 2}
    assert all(values["subtree_size"] >= 1 for values in feats.values())
