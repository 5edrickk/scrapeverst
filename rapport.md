# Projet 2 – Collecter et exploiter des données Web avec CouchDB

## 1. Membres de l'équipe
| Nom | Matricule |
|---|---|
| Abdoulaye Dembélé | <<À COMPLÉTER PAR L'ÉQUIPE : matricule>> |
| Sedrick <<À COMPLÉTER PAR L'ÉQUIPE : nom de famille>> | <<À COMPLÉTER PAR L'ÉQUIPE : matricule>> |

## 2. Site choisi et outil de collecte
- **Site** : Decathlon Canada, version française — https://www.decathlon.ca/fr
- **Données** : produits de sport (nom, marque, catégorie, prix, ancien prix et rabais, note, nombre d'avis, nombre de couleurs, étiquette, URL, image).
- **Outil** : Python 3 avec `requests` (téléchargement) et `BeautifulSoup` + `lxml` (analyse du HTML). Script principal : `scraper/collecter_listes.py`.
- **Respect du site** : une seule requête à la fois, en-tête `User-Agent` identifiant le projet avec une adresse de contact, arrêt immédiat sur un code HTTP 403 ou 429, journal de toutes les requêtes (`data/raw/crawl_journal.csv`), reprise possible sans retélécharger.

### Déroulement de la collecte (et problème rencontré)
1. **Première approche : une page par produit.** Nous avons d'abord récupéré les URL de produits à partir du sitemap (`scraper/collecter_urls.py`, échantillon de 3500 URL dans `data/urls_echantillon.csv`), puis visité chaque page produit (`scraper/collecter_produits.py`, 2,5 s entre deux requêtes). Les fiches obtenues sont très détaillées (description, couleur, caractéristiques, empreinte CO2), mais cette méthode demande une requête par produit, soit plus de 2500 requêtes.
2. **Blocage HTTP 429.** Pendant cette collecte détaillée, le 19 octobre 2026, le serveur a répondu **HTTP 429 (Too Many Requests)**. Le script s'est arrêté immédiatement, comme prévu, et nous n'avons pas tenté de contourner la limite. Les **40 fiches** déjà obtenues sont conservées comme second CSV brut : `data/raw/produits_raw.csv`.
3. **Deuxième approche : pages de catégories.** Chaque page de catégorie liste jusqu'à 40 produits (tuiles avec nom, marque, prix, note, nombre d'avis…). Il faut donc environ 40 fois moins de requêtes, et nous avons doublé l'écart entre deux requêtes : **5 secondes**. Le 19 octobre 2026, de 23 h 22 à 23 h 58 (environ 35 minutes) :
   - **400 requêtes, toutes en HTTP 200** (2 sitemaps, 2 pages de rubrique sans tuiles, 396 pages de catégories) ;
   - **396 pages de catégories** ont fourni des tuiles ;
   - **6009 tuiles** enregistrées dans `data/raw/listes_raw.csv`.

   En contrepartie, les pages de catégories ne donnent pas la description ni les caractéristiques détaillées.

## 3. Nettoyage des données — avant / après
Script : `nettoyage/nettoyer.py` (le CSV brut `data/raw/listes_raw.csv` est lu, jamais modifié). Rapport complet : `data/rapport_nettoyage.txt`.

| Mesure | Valeur |
|---|---|
| Lignes brutes (tuiles) | 6009 |
| Lignes écartées (services d'atelier sans marque ni image) | 2 |
| Doublons retirés | 3429 |
| **Modèles distincts après nettoyage** | **2578** |
| Modèles présents dans plusieurs catégories | 1032 (jusqu'à 12 catégories pour un même modèle) |
| Modèles dont les variantes ont des prix différents | 181 (465 lignes à un autre prix) |
| Marques distinctes | 68 |

Les 2 lignes écartées sont des services d'atelier, pas des produits : « WORKSHOP CHANGEMENT DU CABLE MECANIQUE INFERIEUR » et « WORKSHOP CHANGEMENT DE COURROIE DU VELO MAGNETIQUE ». Les identifiants qui commencent par X **n'ont pas** été filtrés : 112 modèles en X sont de vrais produits (barres XACT NUTRITION, raquette de pickleball…).

Valeurs manquantes (`null`) sur les 2578 documents finaux :
| Champ | Manquants | % | Explication |
|---|---|---|---|
| `nom`, `marque`, `categorie`, `prix.actuel`, `url_source`, `id_variante`, `image_url`, `date_extraction` | 0 | 0,0 % | toujours présents |
| `prix.ancien` | 2167 | 84,1 % | la plupart des produits ne sont pas en rabais |
| `prix.rabais_pct` | 2200 | 85,3 % | idem (33 produits ont un ancien prix sans pourcentage affiché) |
| `evaluation` | 91 | 3,5 % | produits sans avis, souvent récents (24 ont l'étiquette « Nouveau ») |
| `nb_couleurs` | 1907 | 74,0 % | le site n'affiche ce nombre que s'il y a plusieurs couleurs |
| `etiquette` | 1852 | 71,8 % | la plupart des tuiles n'ont pas d'étiquette |

Transformations appliquées :
| Champ brut | Exemple avant | Après |
|---|---|---|
| `prix_actuel_brut` | `11,99 $` (espace insécable) | `11.99` (nombre) |
| `nb_avis_brut` | `(1 906)` | `1906` (entier) |
| `nb_couleurs_brut` | `4 couleurs` | `4` |
| `rabais_brut` | `33% de réduction` | `33` |
| `note_brut` | `4.7` / vide | `4.7` / `evaluation: null` |
| `nom_complet_brut` | `WEDZE Mitaines de ski…` | `nom: "Mitaines de ski…"`, `marque: "WEDZE"` |
| cellule vide | `` | `null` (jamais 0 ni chaîne vide) |

Autres règles :
- espaces insécables et espaces multiples remplacés par une seule espace ;
- **dédoublonnage sur `id_modele`** : un même modèle apparaît plusieurs fois (une tuile par couleur, et des catégories qui se recoupent). On garde la première ligne vue, on fusionne toutes les catégories dans `categories` et on compte les variantes distinctes dans `nb_variantes_vues` ;
- **prix différents selon la variante (181 modèles)** : on garde le prix de la première ligne vue et chaque cas est listé dans le rapport. Exemple : le maillot dermoprotecteur de surf OLAIAN (`decathlon-326429`) est à 4,00 $ (ancien prix 12,00 $) dans une couleur en liquidation, mais à 11,99 $ dans les autres. Le premier prix vu (4,00 $) est conservé. Ces écarts viennent presque tous de couleurs en liquidation ; le prix stocké est donc parfois celui de la couleur la moins chère et non celui du modèle « normal ». Nous avons préféré cette règle simple et documentée à une moyenne qui ne correspondrait à aucun prix réel ;
- avertissement et code de sortie non nul si moins de 2500 modèles (ici : 2578, OK).

## 4. Structure des documents
Un document par modèle de produit. Deux documents réels de la base `decathlon` :

Produit en rabais, avec évaluation, étiquette et deux catégories :
```json
{
  "_id": "decathlon-343975",
  "nom": "Bas de maillot de bain culotte texturée natation femme - Lila simy terracotta",
  "marque": "NABAIJI",
  "categorie": "Bas de maillots de bain pour femmes",
  "categories": [
    "Bas de maillots de bain pour femmes",
    "Maillots de bain 2 pièces pour femmes"
  ],
  "prix": { "actuel": 6.0, "ancien": 18.0, "rabais_pct": 66, "devise": "CAD" },
  "evaluation": { "note": 4.6, "nb_avis": 169 },
  "nb_couleurs": 2,
  "etiquette": "Dernières quantités",
  "nb_variantes_vues": 2,
  "url_source": "https://www.decathlon.ca/fr/p/bas-de-maillot-de-bain-culotte-texturee-natation-femme-lila-simy-terracotta/343975/c324m8920639",
  "id_variante": "m8920639",
  "image_url": "https://contents.mediadecathlon.com/p2778472/k$844d693ef2f732afd70ae45acf54e2cf/picture.jpg?format=auto&f=3000x0",
  "date_extraction": "2026-10-19"
}
```

Produit sans avis (`evaluation: null`), présent dans trois catégories :
```json
{
  "_id": "decathlon-386668",
  "nom": "Barre énergétique d’endurance, amandes et dattes 40 g",
  "marque": "XACT NUTRITION",
  "categorie": "Nutrition et hydratation course à pied",
  "categories": [
    "Nutrition et hydratation course à pied",
    "Barres énergétiques",
    "Nutrition sportive"
  ],
  "prix": { "actuel": 4.1, "ancien": null, "rabais_pct": null, "devise": "CAD" },
  "evaluation": null,
  "nb_couleurs": null,
  "etiquette": null,
  "nb_variantes_vues": 1,
  "url_source": "https://www.decathlon.ca/fr/p/barre-energetique-dendurance-amandes-et-dattes-40-g/386668/g492m9030309",
  "id_variante": "m9030309",
  "image_url": "https://contents.mediadecathlon.com/p3135617/k$ed3dbf39ee804bba3be719f2adb9999d/picture.jpg?format=auto&f=3000x0",
  "date_extraction": "2026-10-19"
}
```

Justification :
- **`_id` = `decathlon-<id_modele>`** : identifiant stable venant du site. Réimporter le même produit ne crée pas de doublon (CouchDB refuse un second document avec le même `_id`), et le préfixe indique la source.
- **Un document par modèle, pas par variante** : les variantes de couleur partagent nom, note et avis ; les garder toutes aurait plus que doublé la base (6009 lignes pour 2578 modèles). `nb_variantes_vues` conserve l'information.
- **Sous-objets `prix` et `evaluation`** : regroupent les champs qui vont ensemble et se lisent naturellement dans les requêtes (`prix.actuel`, `evaluation.note`). `evaluation` vaut `null` quand le produit n'a pas encore d'avis : une note de 0 serait fausse et ferait baisser les moyennes.
- **`categories` (tableau) et `categorie` (chaîne)** : `categorie` garde la catégorie de la première page où le produit a été vu, pour les filtres simples ; le tableau conserve toutes les catégories (1032 produits en ont plusieurs), ce qui est naturel dans un modèle document et sert à la vue MapReduce.
- **Types réels** (nombres décimaux, entiers, `null`) : permettent les comparaisons (`$lt`, `$gte`), le tri et les statistiques (`_stats`) directement dans CouchDB.
- **`date_extraction`** : les prix changent souvent ; la date indique à quel moment la donnée était vraie.

## 5. Import dans CouchDB et vérifications
Script : `couchdb/importer.py`. Méthode :
1. lecture de l'URL et des identifiants dans `.env` (jamais écrits dans le code) ;
2. `--reset` : suppression puis recréation de la base `decathlon` ;
3. import de `data/donnees.json` avec `POST /decathlon/_bulk_docs` par lots de 500 (6 lots : 5 × 500 + 78) ;
4. relecture de toute la base (`_all_docs?include_docs=true`) et vérifications automatiques.

| Vérification | Résultat |
|---|---|
| Documents refusés pendant l'import | 0 |
| Nombre de documents en base = nombre dans le JSON | OK : 2578 = 2578 |
| Aucun doublon d'`_id` (JSON et base) | OK : 2578 `_id` distincts, mêmes `_id` des deux côtés |
| `prix.actuel` est un nombre partout | OK |
| `evaluation.nb_avis` est un entier partout | OK (2487 documents ont un `nb_avis`) |
| Accents intacts (3 documents relus un par un) | OK : « Gaufrette protéinée, Noix de coco », « Barre énergétique, Cassis », « Barre énergétique, Érable » |

La base peut être recréée entièrement à partir du JSON, sans refaire le scraping (voir README, « Reproduire le travail »).

<<À COMPLÉTER PAR L'ÉQUIPE : capture d'écran de Fauxton (http://localhost:5984/_utils) montrant la base `decathlon` avec ses 2578 documents (2581 avec les 3 design documents des index et de la vue)>>

## 6. Requêtes
Index et vue versionnés : `couchdb/index_q1_filtre.json`, `couchdb/index_q2_avis.json`, `couchdb/design_stats.json`. Exécution : `python couchdb/lancer_requetes.py --base decathlon`. Résultats complets : `couchdb/resultats/`.

### Q1 — Mango : filtre multicritère
Polaires de randonnée à moins de 30 $ avec une note d'au moins 4,5. Index sur `categorie`, `prix.actuel`, `evaluation.note`.
```json
{
  "selector": {
    "categorie": "Polaires de randonnée",
    "prix.actuel": { "$lt": 30.0 },
    "evaluation.note": { "$gte": 4.5 }
  },
  "fields": ["_id", "nom", "marque", "prix.actuel", "evaluation"],
  "use_index": ["idx-q1-filtre", "categorie-prix-note"],
  "limit": 200
}
```
Résultat : **15 produits** (extrait) :
| Prix | Note | Produit |
|---|---|---|
| 9,99 $ | 4,9 | QUECHUA – Chandail de randonnée en polaire enfant, MH 100 |
| 14,99 $ | 4,7 | QUECHUA – Chandail de randonnée en polaire femme – MH 100 |
| 14,99 $ | 4,8 | QUECHUA – Chandail de randonnée en polaire homme, MH 100 |
| 19,99 $ | 4,8 | QUECHUA – Veste de randonnée en polaire femme – MH 120 |
| 24,99 $ | 5,0 | QUECHUA – Polaire moutonné à demi-zip enfant, NH 500 Âge 7-15 ans |
| 29,99 $ | 4,9 | QUECHUA – Veste de randonnée en polaire moutonné enfant, NH 500 Âge 2-6 ans |

Interprétation : les 15 polaires trouvées (sur 24 bien notées dans cette catégorie) sont toutes de la marque maison QUECHUA, et 7 sont pour enfants. Les modèles d'entrée de gamme (MH 100, MH 120) sont à la fois les moins chers et parmi les mieux notés : chez Decathlon, prix bas ne veut pas dire mauvaise évaluation.

### Q2 — Mango : les 10 produits les plus commentés
Tri décroissant sur `evaluation.nb_avis`, limite 10. Le sélecteur ne garde que les documents où `evaluation.nb_avis` existe et est un nombre : c'est nécessaire pour que CouchDB utilise l'index trié `idx-q2-avis` (un index Mango ne contient que les documents qui ont le champ).
```json
{
  "selector": { "evaluation.nb_avis": { "$exists": true, "$type": "number" } },
  "fields": ["_id", "nom", "marque", "categorie", "prix.actuel", "evaluation"],
  "sort": [{ "evaluation.nb_avis": "desc" }],
  "use_index": ["idx-q2-avis", "nb-avis-desc"],
  "limit": 10
}
```
| Avis | Note | Prix | Produit |
|---|---|---|---|
| 27 102 | 4,8 | 11,99 $ | NABAIJI – Serviette de bain en microfibre taille G 80 cm x 130 cm |
| 26 961 | 4,7 | 5,99 $ | KIPRUN – Chaussettes de course mi hautes x3 RUN100 |
| 25 328 | 4,7 | 8,99 $ | KALENJI – T-shirt de course à pied respirant homme – Dry 100 |
| 23 889 | 4,8 | 4,99 $ | QUECHUA – Sac à dos de randonnée 10 L, Arpenaz 50 |
| 23 186 | 4,8 | 6,00 $ | DECATHLON – Bas de tennis courts lot de 3 paires, RS 160 |
| 21 675 | 4,8 | 9,99 $ | QUECHUA – Sac à dos de randonnée 10 L, Arpenaz 100 |
| 21 363 | 4,8 | 14,99 $ | QUECHUA – Chandail de randonnée en polaire homme, MH 100 |
| 19 951 | 4,8 | 7,99 $ | DECATHLON – Chaussettes de tennis mi-hautes x3 - Artengo RS 160 |
| 18 055 | 4,8 | 7,99 $ | DECATHLON – Chaussettes de tennis x3 - RS 160 |
| 17 847 | 4,7 | 10,99 $ | DECATHLON – Chaussettes de tennis hautes x3 paires, RS 500 |

Interprétation : les 10 produits les plus commentés coûtent tous **moins de 15 $** (de 4,99 $ à 14,99 $, alors que le prix médian de la base est de 24,99 $). Ce sont des articles de base achetés en très grand nombre (chaussettes, serviette, t-shirt, petit sac à dos), pas de l'équipement technique. Malgré près de 18 000 à 27 000 avis chacun, leur note reste très haute (4,7 à 4,8). Le nombre d'avis mesure donc surtout le volume de ventes.

### Q3 — MapReduce : prix moyen par catégorie
Vue `_design/stats/_view/prix_par_categorie` : la fonction map émet `[catégorie]` → `prix.actuel` pour **chaque** élément du tableau `categories`. Le reducer intégré `_stats` calcule somme, nombre, min et max, et la requête utilise `group_level=1`. La moyenne = `sum / count` (calculée par le script).
```javascript
function (doc) {
  if (doc.prix && typeof doc.prix.actuel === 'number' && Array.isArray(doc.categories)) {
    doc.categories.forEach(function (categorie) { emit([categorie], doc.prix.actuel); });
  }
}
```
La vue renvoie 396 catégories. Extrait limité aux **263 catégories d'au moins 5 produits** :

| Catégorie | Produits | Moyenne | Min | Max |
|---|---|---|---|---|
| Vélos de triathlon | 20 | 4265,99 $ | 389,99 $ | 13 699,00 $ |
| Vélos de ville | 8 | 1042,49 $ | 449,99 $ | 2699,99 $ |
| Nouveautés pour hommes | 14 | 661,56 $ | 6,99 $ | 7199,99 $ |
| Nouveautés pour femmes | 17 | 594,52 $ | 6,99 $ | 7199,99 $ |
| Skis femmes | 8 | 562,49 $ | 349,99 $ | 1089,99 $ |
| Bottes de ski | 10 | 331,99 $ | 109,99 $ | 649,99 $ |
| … | | | | |
| Nutrition sportive | 29 | 7,27 $ | 2,50 $ | 22,99 $ |
| Nutrition et hydratation course à pied | 23 | 6,02 $ | 2,50 $ | 39,99 $ |
| Hameçons et émerillons | 18 | 5,91 $ | 1,00 $ | 34,99 $ |
| Barres énergétiques | 17 | 3,58 $ | 3,10 $ | 4,10 $ |

Interprétation : le vélo (surtout le triathlon) et le ski sont de loin les rayons les plus chers ; la nutrition sportive et les petites pièces de pêche ou de réparation sont les moins chers. Trois précautions :
- **Petites catégories** : une moyenne sur 1 à 4 produits n'est pas représentative (par exemple « Tentes de toit » : 1 seul produit à 1550 $). C'est pourquoi l'extrait ne garde que les catégories d'au moins 5 produits.
- **Catégories de mise en marché** : « Nouveautés pour hommes » (moyenne 661,56 $) mélange des articles à 6,99 $ et un vélo à 7199,99 $ ; « Liquidation golf » ou « Liquidation soccer » regroupent des prix déjà réduits. Ces moyennes décrivent une sélection marketing, pas un type de produit, et une seule valeur extrême les fait grimper. Une médiane serait plus fiable, mais `_stats` ne la calcule pas.
- **Un produit compte dans chacune de ses catégories** : la somme des comptes de la vue est de 4359 pour 2578 documents, car 1032 produits sont dans plusieurs catégories. Les catégories ne sont donc pas disjointes et on ne peut pas additionner leurs effectifs.

## 7. Dépôt et base
- Lien GitHub : https://github.com/5edrickk/scrapeverst
- Nom de la base CouchDB : `decathlon`

## 8. Avis sur les technologies
- **requests + BeautifulSoup** : très simples à prendre en main ; en quelques lignes on télécharge une page et on extrait des éléments par sélecteur CSS. Mais le script dépend entièrement du HTML du site : un changement de classe CSS casse l'extraction (il a fallu corriger la détection de l'ancien prix et des étiquettes). Ils n'exécutent pas le JavaScript : cela a fonctionné ici parce que les pages de catégories de Decathlon sont rendues côté serveur. Enfin, il faut gérer soi-même la politesse (délai, arrêt sur 429), ce que le blocage reçu nous a rappelé.
- **CouchDB** : l'import de JSON est direct (`_bulk_docs`) et Fauxton permet de vérifier rapidement les documents. **Mango** est facile à lire pour des filtres, mais un tri n'est possible qu'avec un index adapté, et le sélecteur doit être compatible avec cet index (d'où le `$exists` de Q2). **MapReduce** est puissant pour les agrégats (le `forEach` sur le tableau `categories` serait plus compliqué en SQL), mais moins intuitif qu'un `GROUP BY`, et `_stats` ne donne ni médiane ni écart-type.
- **Claude Code** : très utile pour produire rapidement des scripts complets (nettoyage, import, requêtes) et un échantillon fictif pour tester sans solliciter le site. Il faut cependant lui donner des consignes précises (ne pas toucher au scraper, aucune requête vers le site, fichiers à committer) et vérifier ses résultats : par exemple, un libellé du rapport de nettoyage comptait 465 « modèles » au lieu de 181 et a dû être corrigé.
- **Limites rencontrées** : limite de requêtes du site (HTTP 429) sur les pages produits, données moins détaillées sur les pages de catégories, prix différents selon la couleur pour 181 modèles.

## 9. Contribution de chaque membre
<<À COMPLÉTER PAR L'ÉQUIPE : pour chaque membre, les tâches réalisées (collecte, nettoyage, CouchDB, requêtes, rapport…) et un pourcentage ; le total doit faire 100 %.>>

| Membre | Tâches | Pourcentage |
|---|---|---|
| Abdoulaye Dembélé | <<À COMPLÉTER PAR L'ÉQUIPE>> | <<À COMPLÉTER PAR L'ÉQUIPE>> % |
| Sedrick <<À COMPLÉTER PAR L'ÉQUIPE : nom de famille>> | <<À COMPLÉTER PAR L'ÉQUIPE>> | <<À COMPLÉTER PAR L'ÉQUIPE>> % |

## 10. Utilisation de l'IA
Nous avons utilisé un assistant d'IA (Claude, via Claude Code) pour :
- écrire une première version des scripts de collecte, de nettoyage (`nettoyage/nettoyer.py`), d'import (`couchdb/importer.py`) et de requêtes (`couchdb/lancer_requetes.py`) ;
- générer un échantillon **fictif** (`data/echantillon_listes.csv`) imitant le format brut, pour tester la chaîne sans faire de requêtes au site ;
- choisir la catégorie et le seuil de Q1 à partir des données réelles ;
- rédiger la structure et une première version de ce rapport et du README.

Vérifications effectuées :
- exécution de toute la chaîne sur l'échantillon fictif dans une base séparée `decathlon_test` (nettoyage, import, vérifications automatiques, trois requêtes), puis contrôle à la main des résultats de Q1 et des comptes de Q3 sur cet échantillon ;
- sur les vraies données : vérifications automatiques de l'import (section 5), contrôle dans le CSV brut que les prix inhabituels (ex. 4,00 $, 6,00 $) sont de vrais prix de liquidation et non des erreurs de lecture, contrôle que les 2 lignes écartées sont bien des services d'atelier ;
- <<À COMPLÉTER PAR L'ÉQUIPE : vérifications faites par vous-mêmes — par exemple quelques documents comparés avec le site, relecture du code et du rapport, ajustements demandés à l'IA>>

Tous les chiffres et extraits de ce rapport proviennent de l'exécution des scripts sur les données collectées (`data/rapport_nettoyage.txt`, `couchdb/resultats/`), pas d'une invention de l'IA.
