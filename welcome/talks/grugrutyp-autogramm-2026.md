<script>document.documentElement.setAttribute("data-theme","light")</script>
<style>
/* Light mode always (Kim, 2026-11-24): the builder darkens on prefers-color-scheme unless
   <html data-theme="light">; the inlined hero SVG carries its own dark rules, overridden here. */
/* Pure white page (Kim, 2026-11-24), so the stock photos' white backgrounds have no visible frame. */
:root,:root[data-theme="light"]{--paper:#FFFFFF}
.sparkle{position:relative;display:inline-block;background:linear-gradient(110deg,#B0413E 0%,#B0413E 38%,#F7D35C 47%,#FFF6C8 50%,#F7D35C 53%,#B0413E 62%,#B0413E 100%);background-size:260% 100%;-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent;color:transparent;animation:shine 2.8s linear infinite}
.sparkle.teal{background-image:linear-gradient(110deg,#0F4E5C 0%,#0F4E5C 38%,#E0B23A 47%,#FFF1B8 50%,#E0B23A 53%,#0F4E5C 62%,#0F4E5C 100%)}
.sparkle{filter:drop-shadow(0 0 .12em rgba(242,194,48,.55));padding:.06em .04em .26em;line-height:1.15}
.sparkle i{position:absolute;font-style:normal;color:#F2C230;-webkit-text-fill-color:#F2C230;font-size:.5em;line-height:1;animation:twinkle 1.6s ease-in-out infinite;pointer-events:none}
.sparkle i:nth-child(1){top:-.55em;left:-.55em}
.sparkle i:nth-child(2){top:-.5em;right:-.6em;animation-delay:.4s;font-size:.42em}
.sparkle i:nth-child(3){bottom:-.35em;right:18%;animation-delay:.8s;font-size:.36em}
.sparkle i:nth-child(4){top:-.25em;left:42%;animation-delay:1.2s;font-size:.3em}
.sparkle i:nth-child(5){bottom:-.2em;left:6%;animation-delay:.2s;font-size:.34em}
@keyframes shine{from{background-position:100% 0}to{background-position:-160% 0}}
@keyframes twinkle{0%,100%{opacity:0;transform:scale(.3) rotate(0deg)}50%{opacity:1;transform:scale(1.15) rotate(90deg)}}
@media print{.sparkle{animation:none}.sparkle i{display:none}}
.slide.propre .pic{position:absolute;right:7vw;bottom:-14vh;margin:0;z-index:0}
.slide.propre .pic img{max-height:none;height:100vh;width:auto;border-radius:0}
.slide img[alt^="Une femme aux cheveux longs"]{transform:scaleX(-1)}
.notice{column-count:2;column-gap:2.2em;font-family:"IBM Plex Sans",system-ui,sans-serif;font-size:.72em;line-height:1.38;border:1px solid var(--line);border-top:6px solid var(--teal);border-radius:4px;padding:.7em 1.2em .5em;background:var(--panel)}
.notice .nhead{column-span:all;font-size:1.05em;margin:0 0 .5em;padding-bottom:.4em;border-bottom:1px solid var(--line);color:var(--muted)}
.notice h3{font-size:1em;margin:.55em 0 .15em;color:var(--teal-ink);text-transform:uppercase;letter-spacing:.05em;break-after:avoid}
.notice p{margin:.15em 0;font-size:1em}.notice ul{margin:.1em 0 .2em;padding-left:1.1em}.notice li{margin:.1em 0}
.slide.dur .svgfig svg{max-height:44vh;width:auto;max-width:100%;margin:.2em auto .5em}
.svgfig svg .frame{stroke:#c9ccd1}.svgfig svg .grid{stroke:#e6e8eb}.svgfig svg .tick{fill:#5b6168}
.svgfig svg .axis{fill:#30353b}.svgfig svg .corner{fill:#5b6168}.svgfig svg .pt{stroke:#fff}
.svgfig svg .lab{fill:#30353b;stroke:#fff}.svgfig svg .pt[style$=":black"]{fill:black}
.svgfig svg .pt.hist{stroke:var(--c);stroke-width:1.4}
.svgfig svg .pt.hist[style$=":black"]{fill:black;stroke:black}
</style>
<style>
.slide.tt h1{font-size:1.85em}
.slide.tt .titlegrid{grid-template-columns:minmax(0,1fr) minmax(0,1.45fr);gap:1.6em}
.slide.tt h2{max-width:30ch}
.tagline{font-family:"IBM Plex Sans",system-ui,sans-serif;font-size:.62em;letter-spacing:.08em;text-transform:uppercase;color:var(--red);margin:0 0 .5em}
.pic img{display:block;max-height:68vh;width:auto;max-width:100%;margin:0 auto;border-radius:10px}
.signpic{position:relative;display:inline-block;line-height:0}
.signpic img{display:block;height:74vh;width:auto;max-width:none;border-radius:10px}
.signpic.wide{display:block}
.signpic.wide img{height:auto;width:100%}
.signpic p{margin:0;height:auto}
.titlegrid .photo{display:flex;align-items:center;padding-right:2vw}
.titlegrid .photo .signpic img{height:auto;width:100%;object-fit:contain}
.signtxt{position:absolute;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;line-height:1.08;font-family:"Gentium Book Plus","Gentium Plus",Georgia,serif;font-weight:700;color:#B0413E}
.signtxt small{display:block;font-family:"IBM Plex Sans",system-ui,sans-serif;font-size:.42em;font-weight:600;color:#1C2622;margin-top:.5em;line-height:1.3}
.burst{display:inline-flex;align-items:center;justify-content:center;width:4.6em;height:4.6em;background:#F2C230;color:#B0413E;font-family:"IBM Plex Sans",system-ui,sans-serif;font-weight:700;text-align:center;line-height:1.02;transform:rotate(-12deg);clip-path:polygon(50% 0%,61% 12%,75% 6%,78% 21%,93% 22%,88% 37%,100% 46%,89% 56%,96% 71%,80% 74%,79% 90%,64% 85%,55% 100%,45% 87%,30% 95%,26% 79%,10% 80%,14% 64%,0% 54%,11% 44%,4% 29%,20% 25%,21% 10%,37% 14%)}
.burstpos{position:absolute;top:6vh;right:5vw;font-size:.9em;z-index:2}
.lang .petit,.petit{font-family:"IBM Plex Sans",system-ui,sans-serif;font-size:.48em;color:var(--muted);line-height:1.35;margin-top:.9em}
.promises{display:grid;grid-template-columns:1fr 1fr;gap:.7em;margin:.5em 0 .3em}
.promises div{background:var(--panel);border:1px solid var(--line);border-top:5px solid var(--ochre);border-radius:8px;padding:.45em .65em;font-size:.74em}
.promises b{display:block;font-size:1.2em;color:var(--teal-ink);margin-bottom:.15em}
.testi{display:grid;grid-template-columns:repeat(3,1fr);gap:1.3em}
.testi img{display:block;width:100%;height:auto;aspect-ratio:1.1;object-fit:cover;object-position:50% 18%;border-radius:10px}
.bubblepic{position:relative;margin-top:.36em}
.bubblepic img{object-position:50% 0%}
.bubbletxt{position:absolute;left:14%;width:65%;top:14%;height:34%;display:flex;align-items:center;justify-content:center;text-align:center;font-style:italic;font-size:.74em;line-height:1.2;color:#1C2622}
.testi p{margin:.45em 0 0;font-style:italic;font-size:.8em}
.testi .who{font-style:normal;font-family:"IBM Plex Sans",system-ui,sans-serif;font-size:.58em;color:var(--muted);margin-top:.25em}
.shot img{display:block;max-height:54vh;width:auto;max-width:100%;margin:0 auto;border-radius:8px;border:1px solid var(--line);box-shadow:0 6px 22px rgba(0,0,0,.14)}
.boxes{display:grid;grid-template-columns:1fr 1fr;gap:.35em;margin:.3em 0 .6em}
.boxes div{border:2px solid var(--muted);border-radius:6px;padding:.5em .3em;text-align:center;font-family:"IBM Plex Sans",system-ui,sans-serif;font-size:.68em;color:var(--muted)}
.lang .punch{font-size:1.75em;margin:.2em 0 .3em}
.lang .big,.big{font-family:"Gentium Book Plus","Gentium Plus",Georgia,serif;font-size:2.6em;font-weight:700;color:#B0413E;line-height:1;margin:.1em 0 .2em}
.logo-corner{position:absolute;right:3vw;bottom:5vh;width:11vw;z-index:2}
.logo-corner img{width:100%;border-radius:6px}
.steps{counter-reset:s;list-style:none;padding:0}
.steps li{counter-increment:s;margin:.45em 0;padding-left:2em;position:relative}
.steps li::before{content:counter(s);position:absolute;left:0;top:.05em;width:1.4em;height:1.4em;border-radius:50%;background:var(--teal);color:#fff;font-family:"IBM Plex Sans",system-ui,sans-serif;font-size:.8em;display:flex;align-items:center;justify-content:center}
</style>

<div class="titlegrid" markdown="1">
<div markdown="1">

<p class="tagline">Une émission de téléachat · Autogramm</p>

# Vers une base de données typologique dynamique basée sur des corpus annotés

## grugrutyp®, l'explorateur typométrique

<ul class="authors">
<li><b>Kim Gerdes</b>, LISN (CNRS), Université Paris-Saclay</li>
<li>avec Sylvain Kahane, Xinying Chen, Ziqian Peng</li>
</ul>

Réunion Autogramm · 24 novembre 2026

<p class="small">À essayer tout de suite : <a href="https://typometrics.elizia.net/">typometrics.elizia.net</a></p>

</div>
<div class="photo" markdown="1">

<div class="signpic wide">

![Une foule enthousiaste brandit une banderole](img_grugrutyp/foule_banderole.jpg)

<div class="signtxt" style="left:17%;right:12%;top:58%;bottom:2%;font-size:3.1em"><span class="sparkle">grugrutyp® !<i>✦</i><i>✦</i><i>✦</i><i>✧</i><i>✦</i></span></div>
</div>

</div>
</div>

<!-- class: titlephoto tt -->
<!-- Notes : ton téléachat assumé, mais tout ce qui est affiché est vrai et vérifiable en direct. 15 minutes. Le titre officiel est sérieux : c'est bien le programme, une base de données typologique qui se recalcule à partir des corpus. -->

---

# Vous en avez assez ?

<div class="lang" markdown="1">
<div markdown="1">

- de remplir des **questionnaires typologiques** à la main ?
- de devoir choisir **une case par langue** : OV ou VO, préposition ou postposition ?
- d'**atlas figés** à la date d'impression ?
- de **chiffres** dont personne ne retrouve les phrases ?

</div>
<div class="pic" markdown="1">

![Un homme déçu, pouce baissé](img_grugrutyp/pouce_bas.jpg)

</div>
</div>

<!-- Notes : la typologie classique code chaque langue dans une case, à la main, d'après les grammaires. C'est précieux, mais c'est binaire, figé et invérifiable dans le détail. -->

---

# Il existe une solution !

<div class="lang" markdown="1">
<div markdown="1">

<p class="punch"><span class="sparkle teal">grugrutyp®<i>✦</i><i>✦</i><i>✦</i><i>✧</i><i>✦</i></span></p>

La typologie qui **se recompte toute seule**, à partir des treebanks de Universal Dependencies.

<div class="promises" markdown="1">
<div><b>Plus fine</b>des proportions, pas des cases</div>
<div><b>Plus propre</b>chaque chiffre a ses phrases</div>
<div><b>Moins chère</b>0 €, 0 questionnaire</div>
<div><b>Plus durable</b>recomptée à chaque release</div>
</div>

</div>
<div class="pic" markdown="1">

![Un homme souriant fait le signe OK](img_grugrutyp/ok.jpg)

</div>
</div>

<!-- Notes : les quatre promesses, qui structurent la suite. grugrutyp succède au site typometrics (Gerdes, Kahane & Chen 2021) : là où l'ancien site offrait cinq familles de mesures précalculées, ici toute mesure est une requête. -->

---

# Démonstration : avant / après

<div class="lang" markdown="1">
<div markdown="1">

**Avant** : une case par langue.

<div class="boxes"><div>OV + postpositions</div><div>VO + prépositions</div><div>OV + prépositions</div><div>VO + postpositions</div></div>

**Après** : chaque langue est un point. Sur **88** langues qui placent surtout l'objet après le verbe, **82** ont surtout des prépositions ; sur **53** langues OV, **41** ont des postpositions. Greenberg (1963), mesuré et non codé, **exceptions comprises** : persan, finnois.

<p class="petit">SUD 2.19, 159 langues ayant au moins 30 objets et 30 adpositions. Objets nominaux : tête NOUN, PROPN ou ADP (を, को, a…).</p>

</div>
<div markdown="1">

![Graphique](img_grugrutyp/hero-plot.svg)

</div>
</div>

<!-- Notes : chaque point est une langue ; l'axe horizontal, la part des objets nominaux après le verbe ; l'axe vertical, la part des adpositions avant leur nom. Deux coins pleins, un coin presque vide (VO avec postpositions : finnois, estonien, sami). Les points creux sont des langues anciennes. Ce graphique est sur la page d'accueil, et s'ouvre tel quel dans grugrutyp. -->

---

# Comment ça marche ? Deux requêtes, c'est tout.

Une mesure, c'est une **portée** (ce qu'on compte) et une **réponse** (ce qui, parmi cela, nous intéresse), en Grew :

```
portée  : pattern { V -[1=subj]-> S }
réponse : with { V << S }
```

Chaque langue reçoit **100 × #(portée ∧ réponse) / #(portée)**, ici : la part des sujets placés après leur tête.

- **803 treebanks** (402 UD, 401 SUD) dans une base de graphes Neo4j : le résultat en **quelques secondes\***
- un **clic** sur un point montre les arbres qui ont été comptés
- tout graphique se **partage** par un lien, s'exporte en SVG, PNG ou TSV

<p class="petit">* À chaud. À froid, 55 secondes : nos disques tournent à 7 200 tours par minute, et la base ne tient pas en mémoire.</p>

<!-- Notes : le langage est celui de Grew-match, donc une requête copiée de Grew-match donne les mêmes comptes ici. Les deux requêtes de la paire viennent de grex (Herrera, Le Corro & Kahane 2024). Le passage par Neo4j suit Deworetzki & Ljunglöf (2025). -->

---

# Plus fine !

<div class="shot" markdown="1">

![grugrutyp® : objets pronominaux contre objets nominaux après le verbe](img_grugrutyp/grugrutyp_plot.png)

</div>

Des **proportions** au lieu de cases, un **intervalle de confiance** pour chaque langue, et une langue = la **somme** de ses treebanks, jamais la moyenne de leurs pourcentages.

<!-- Notes : le triangle de l'article de 2021 : les objets nominaux suivent le verbe au moins aussi souvent que les objets pronominaux, une moitié du graphique reste vide. Sauf le bedja, en bas à droite : 80 % de ses objets pronominaux sont postverbaux. Les intervalles sont de Wilson, parce que la typologie vit aux bords (0 sur 5 000). -->

---

# Plus propre !

<div class="lang" markdown="1">
<div markdown="1">

Pour des données **soyeuses et traçables** :

- chaque chiffre **renvoie à ses phrases** (onglet Search)
- **132 tests** comparent nos comptes à ceux de Grew lui-même
- les corpus d'apprenants, les doublons et les copies retokenisées sont **écartés des mesures**
- chaque requête est **validée** avant de partir, et chaque graphique se refait à l'identique depuis son lien

</div>
<div class="pic" markdown="1">

![Une femme aux cheveux longs et brillants, comme dans une publicité pour shampoing](img_grugrutyp/shampoing.jpg)

</div>
</div>

<!-- Notes : « propre » au sens fort : un compte faux ne ressemble pas à une erreur, il ressemble à une découverte typologique. D'où les tests différentiels contre Grew. -->

<!-- class: propre -->
---

# Mais ce n'est pas tout !

<div class="lang" markdown="1">
<div markdown="1">

Les **Findings** : des universaux quantitatifs trouvés par une **fouille systématique** des relations, catégories et directions, puis triés à la main.

- les sujets précèdent les objets, **partout sauf en tagalog\***
- plus l'objet est lourd, plus il va à droite
- l'universel des adpositions, **retrouvé par la machine**
- le bedja, **l'anti-français**

Chaque résultat s'ouvre comme un graphique vivant, et modifiable.

<p class="petit">* Résultats observés sur UD 2.18. Les résultats peuvent varier selon la release.</p>

</div>
<div class="shot" markdown="1">

![L'onglet Findings de grugrutyp®](img_grugrutyp/grugrutyp_findings.png)

</div>
</div>

<!-- Notes : ce sont des hypothèses, pas des résultats publiés : elles ont survécu aux tests de permutation et de lignée. Avec la 2.19, le résultat sur le poids de l'objet est en cours de revérification (en 2.18, les compléments d'adposition étaient comptés comme objets). -->

---

# Notice : comment sont fabriqués les Findings

<div class="notice" markdown="1">
<p class="nhead">NOTICE : INFORMATION DE L'UTILISATEUR · <b>Findings grugrutyp®</b>, universaux quantitatifs · fouille sur SUD 2.18</p>

### 1. Qu'est-ce que c'est

Des **hypothèses** d'universaux quantitatifs : des formes du nuage de langues (coin vide, triangle, amande) trouvées par une **fouille systématique**, puis triées par Claude (Claude Code, en session avec Kim, septembre 2026) : pas de prompt figé, les critères sont dans `docs/pattern-mining.md`. 10 sont dans l'onglet Findings. Ce ne sont pas encore des résultats publiés.

### 2. Composition

- une matrice **langue × mesure** : 193 langues × 204 mesures : direction (des relations et des triplets catégorie–fonction–catégorie), fréquence, distance, part des catégories, et 10 écrites à la main en Grew
- un seul **passage exact** par treebank, sans échantillonnage
- chaque case garde ses comptes et son **intervalle de Wilson**

### 3. Mode d'action

- les **133** mesures à large couverture, croisées deux à deux : 8 778 paires, dont **8 757** partagent au moins 40 langues, passées à une batterie de formes : coin vide (quadrants), cellules vides d'une grille, inégalité (triangle X ≥ Y)
- **surprise** = vide au-delà du hasard × survie au rééchantillonnage des lignées

### 4. Contre-indications (filtres de trivialité)

- **couplage arithmétique** : deux mesures qui se recouvrent (`det` / DET) : éliminé
- **hasard** : 1 000 permutations des langues ; seul l'excès compte
- **généalogie** : une langue par genre, rééchantillonnée ; une paire typique, c'est 80 langues mais 25 lignées
- **puissance** : seule une langue à intervalle étroit peut témoigner d'un vide

### 5. Effets indésirables

Redécouverte de Greenberg (l'universel des adpositions, retrouvé à l'aveugle) ; abondance d'harmonies « légales mais ennuyeuses » ; le bedja.

### 6. Conservation

Re-tester à chaque release : en 2.19, `comp:obj` → `comp` modifie deux recettes, revérification en cours. Tenir hors de portée des p-values : avec 8 757 paires et 25 lignées, elles sont décoratives.

</div>

<p class="petit" style="margin-top:.6em">Méthode, chiffres et pourquoi les p-values sont décoratives : <a href="https://typometrics.elizia.net/autofindings/">typometrics.elizia.net/autofindings</a></p>

<!-- Notes : docs/pattern-mining.md. La machine propose, les filtres éliminent, l'humain trie ; la confirmation, c'est la release suivante et les phrases (onglet Search) pour chaque exception. -->

---

# Ils l'ont essayé

<div class="testi" markdown="1">
<div markdown="1">

![Un homme souriant](img_grugrutyp/temoin1.jpg)

<p>« 37 % d'objets après le verbe. Enfin quelqu'un qui ne me force pas à choisir ! »</p>
<p class="who">L'allemand, 37,5 % VO</p>

</div>
<div markdown="1">

<div class="bubblepic">

![Une femme pensive, une bulle au-dessus de la tête](img_grugrutyp/temoin2.jpg)

<div class="bubbletxt">Seule exception à l'universel 1 sur 160 langues. Je me sens unique.</div>
</div>

<p class="who">Le tagalog, 26 % sujet avant objet*</p>

</div>
<div markdown="1">

![Un couple heureux](img_grugrutyp/temoin3.jpg)

<p>« Ma postposition est la tête de mes objets. Avant, personne ne les comptait. Maintenant, si ! »</p>
<p class="who">Le japonais, 100 % d'objets marqués par を</p>

</div>
</div>

<p class="petit">Témoignages authentiques, chiffres réels (UD 2.19 ; * tagalog : 2.18). Les langues n'ont pas été rémunérées.</p>

<!-- Notes : le japonais est un vrai cas : en SUD, を est la tête de l'objet, et une requête « objet nominal » qui exige un NOUN sous le verbe perd tous les objets japonais. Question envoyée à Sylvain et Bruno : que compter comme objet nominal quand l'adposition est tête ? -->

---

# Moins chère !

<div class="lang" markdown="1">
<div markdown="1">

Combien payeriez-vous pour 226 langues recomptées à la demande ?

<p class="big">0 €</p>

- ni questionnaire, ni abonnement, ni installation
- code ouvert : [github.com/typometrics/grugrutyp](https://github.com/typometrics/grugrutyp)
- seule l'**option LLM** coûte quelque chose… à Kim

</div>
<div markdown="1">

<div class="signpic wide">

![Un homme en costume montre une pancarte](img_grugrutyp/pancarte_homme.jpg)

<div class="signtxt" style="left:61%;right:3%;top:42%;bottom:8%;font-size:2.4em">0 €<small>frais de port offerts</small></div>
</div>

</div>
</div>

<!-- class: dense -->
<!-- Notes : vraiment gratuit ; le serveur tourne déjà. L'option LLM appelle un modèle payant à chaque requête, d'où le quota et l'activation à la main. -->

---

# Plus durable !

<p class="punch">À consommer avant : jamais.</p>

![Les langues de UD 2.19 ; en rouge, les 33 nouvelles](img_grugrutyp/map_ud219.svg)

- **cette nuit** : de UD 2.18 à **2.19**, 226 langues dont **33 nouvelles** (en rouge), 803 treebanks
- les conventions changent ? Nous aussi : en SUD 2.19, `comp:obj` → `comp` sous les adpositions : **détecté, mesuré, corrigé**

<p class="petit">Offre valable jusqu'à la prochaine release (mai 2027), puis renouvelée automatiquement. Carte : Natural Earth, coordonnées des langues d'après UD.</p>

<!-- class: dense dur -->
<!-- Notes : la 2.19 est sortie le 15 novembre ; importée dans une base séparée, bascule en changeant deux lignes. Les cercles ocre : basaá, chikunda, tai lü, les langues de la Scierie, pas encore dans UD. -->
---

# Nouveau : l'option LLM !

<div class="lang" markdown="1">
<div markdown="1">

Vous ne parlez pas encore Grew ? **Décrivez votre mesure en français.**

- grugrutyp® **écrit la requête** Grew, la valide comme une requête tapée à la main, et vous la propose
- il **commente votre graphique**, intervalles de confiance compris
- il **discute** avec vous dans un panneau latéral

C'est toujours vous qui appuyez sur « Plot ».

</div>
<div markdown="1">

<div class="signpic wide">

![Un homme pensif, une bulle au-dessus de la tête](img_grugrutyp/bulle.jpg)

<div class="signtxt" style="left:59%;width:33%;top:9%;height:20%;font-size:.78em;color:#1C2622">« Mes sujets, ils sont avant ou après&nbsp;? »</div>
</div>

</div>
</div>

<!-- Notes : trois fonctions : traduction français → paire de requêtes, commentaire d'un graphique calculé, conversation. Quota de 50 requêtes par jour et par compte. -->

---

# Demandez conseil à votre administrateur

<div class="lang" markdown="1">
<div markdown="1">

**grugrutyp®** est un outil de recherche. Lire attentivement la notice.

- **Un corpus n'est pas une langue** : genres, tailles et conventions d'annotation varient.
- Ne pas confondre **absence de données** et universel (mais on y travaille, voir la [*Scierie syntaxique*](https://elizia.net/sawmill/scierie_autogramm.html)).
- Les étiquettes peuvent **changer de sens** d'une release à l'autre.
- En cas de résultat surprenant, **consultez les phrases**.
- L'**option LLM** est délivrée **sur demande** : créez votre compte, puis **demandez conseil à votre administrateur** (Kim).

<p class="petit">Effets indésirables possibles : découverte d'universaux, perte de foi dans les tableaux codés à la main, envie irrépressible d'écrire du Grew à deux heures du matin.</p>

</div>
<div class="pic" markdown="1">

![Une médecin en blouse, stéthoscope autour du cou](img_grugrutyp/medecin.jpg)

</div>
</div>

<!-- class: dense -->
<!-- Notes : la diapo honnête : les limites sont réelles, et le LLM n'est activé qu'à la main, compte par compte. -->

---

# Appelez vite !

<div class="lang" markdown="1">
<div markdown="1">

<ol class="steps">
<li>Allez sur <a href="https://typometrics.elizia.net/grugrutyp/"><b>typometrics.elizia.net/grugrutyp</b></a></li>
<li><b>Créez votre compte</b> : Google, GitHub ou ORCID (sign in, en haut à droite)</li>
<li>Écrivez à Kim pour <b>activer l'option LLM</b></li>
</ol>

<p class="punch">Satisfait ou recompté !</p>

Rejoignez les **milliers\*** d'utilisateurs de grugrutyp®.

<p class="petit">* 15 visiteurs-jours ces deux dernières semaines. Les serveurs sont en ligne 24 h/24. Questions, bugs, envies de mesures : <a href="https://gerdes.fr">gerdes.fr</a></p>

</div>
<div markdown="1">

<div class="signpic">

![Une femme souriante montre une grande pancarte](img_grugrutyp/pancarte_femme.jpg)

<div class="signtxt" style="left:47%;right:4%;top:22%;bottom:30%;font-size:1.25em">Essayez<br><span class="sparkle">grugrutyp®<i>✦</i><i>✦</i><i>✦</i><i>✧</i><i>✦</i></span><small>typometrics.elizia.net/grugrutyp</small></div>
</div>

</div>
</div>

<div class="logo-corner">

![Logo Autogramm](img_grugrutyp/logo_autogramm.jpg)

</div>

<!-- Notes : appel à l'action : le compte se crée en un clic ; l'option LLM, je l'active à la main sur demande. Merci ! -->
