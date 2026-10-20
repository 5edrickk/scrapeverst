# Projet 2 – Collecter et exploiter des données Web avec CouchDB

## 1. Membres de l'équipe
| Nom | Matricule |
|---|---|
| Abdoulaye Dembélé | <<À COMPLÉTER>> |
| Sedrick <<À COMPLÉTER : nom complet>> | <<À COMPLÉTER>> |

## 2. Site choisi et outil de collecte
- **Site** : Decathlon Canada, version française — https://www.decathlon.ca/fr
- **Données** : produits de sport (nom, marque, catégorie, prix, ancien prix et rabais, note, nombre d'avis, nombre de couleurs, étiquette, URL, image).
- **Outil** : Python 3 avec `requests` (téléchargement) et `BeautifulSoup` + `lxml` (analyse du HTML). Script : `scraper/collecter_listes.py`.
- **Respect du site** : une seule requête à la fois, en-tête `User-Agent` identifiant le projet avec une adresse de contact, arrêt immédiat sur un code HTTP 403 ou 429, journal de toutes les requêtes (`data/raw/crawl_journal.csv`), reprise possible sans retélécharger (`data/raw/crawl_etat.json`).

### Déroulement de la collecte (et problème rencontré)
1. **Première approche — une page par produit.** Nous avons d'abord récupéré les URL de produits à partir du sitemap, puis visité chaque page produit (`scraper/collecter_urls.py`, `scraper/collecter_produits.py`, délai de 2,5 s entre deux requêtes). Cette approche donnait des fiches très détaillées (description, caractéristiques), mais demandait une requête par produit, soit plus de 2500 requêtes.
2. **Blocage.** Pendant cette collecte détaillée, le serveur a répondu **HTTP 429 (Too Many Requests)**. Le script s'est arrêté immédiatement, comme prévu, et nous n'avons pas tenté de contourner la limite. <<À COMPLÉTER : date/heure et nombre de fiches obtenues avant le 429>>
3. **Deuxième approche — pages de catégories.** Nous sommes passés aux pages de catégories : chaque page liste environ 40 produits (tuiles avec nom, marque, prix, note, nombre d'avis…). Il faut donc beaucoup moins de requêtes pour le même nombre de produits, et nous avons augmenté l'écart à **5 secondes** entre deux requêtes. En contrepartie, nous perdons la description et les caractéristiques détaillées. <<À COMPLÉTER : nombre de requêtes, durée totale, nombre de tuiles>>

## 3. Nettoyage des données — avant / après
Script : `nettoyage/nettoyer.py` (le CSV brut `data/raw/listes_raw.csv` est lu, jamais modifié). Rapport complet : `data/rapport_nettoyage.txt`.

| Mesure | Valeur |
|---|---|
| Lignes brutes (tuiles) | <<À COMPLÉTER>> |
| Modèles distincts après nettoyage | <<À COMPLÉTER>> |
| Doublons retirés | <<À COMPLÉTER>> |
| Modèles dont les variantes ont des prix différents | <<À COMPLÉTER>> |
| Produits sans évaluation (`evaluation` = null) | <<À COMPLÉTER>> |
| Produits sans ancien prix | <<À COMPLÉTER>> |

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
- **dédoublonnage sur `id_modele`** : un même modèle apparaît plusieurs fois (une tuile par couleur, et des catégories qui se recoupent). On garde la première ligne vue, on fusionne toutes les catégories dans `categories` et on compte les variantes dans `nb_variantes_vues` ;
- si deux variantes d'un modèle ont des prix différents, le premier prix est gardé et le cas est listé dans le rapport ;
- avertissement et code de sortie non nul si moins de 2500 modèles.

## 4. Structure des documents
Un document par modèle de produit. Deux exemples (<<À COMPLÉTER : remplacer par deux documents réels de la base `decathlon`>>) :

Produit en rabais, avec évaluation, présent dans deux catégories :
```json
{
  "_id": "decathlon-8735190",
  "nom": "Mitaines de ski chaudes et imperméables 500 adulte",
  "marque": "WEDZE",
  "categorie": "Ski et snowboard",
  "categories": ["Ski et snowboard", "Vêtements d'hiver femme"],
  "prix": { "actuel": 11.99, "ancien": 17.99, "rabais_pct": 33, "devise": "CAD" },
  "evaluation": { "note": 4.7, "nb_avis": 1906 },
  "nb_couleurs": 4,
  "etiquette": null,
  "nb_variantes_vues": 4,
  "url_source": "https://www.decathlon.ca/fr/p/…/8735190/…",
  "id_variante": "m8670487",
  "image_url": "https://contents.mediadecathlon.com/…/picture.jpg",
  "date_extraction": "2026-10-19"
}
```

Nouveau produit sans avis ni ancien prix :
```json
{
  "_id": "decathlon-X8823170",
  "nom": "Bâtons de ski Boost 500 réglables",
  "marque": "WEDZE",
  "categorie": "Ski et snowboard",
  "categories": ["Ski et snowboard"],
  "prix": { "actuel": 24.99, "ancien": null, "rabais_pct": null, "devise": "CAD" },
  "evaluation": null,
  "nb_couleurs": null,
  "etiquette": "Précommande",
  "nb_variantes_vues": 1,
  "url_source": "https://www.decathlon.ca/fr/p/…/X8823170/…",
  "id_variante": "m8379201",
  "image_url": "https://contents.mediadecathlon.com/…/picture.jpg",
  "date_extraction": "2026-10-19"
}
```

Justification :
- **`_id` = `decathlon-<id_modele>`** : identifiant stable venant du site. Réimporter le même produit ne crée pas de doublon (CouchDB refuse un second document avec le même `_id`), et le préfixe indique la source.
- **Un document par modèle, pas par variante** : les variantes de couleur partagent nom, prix et avis ; les garder toutes gonflerait la base de doublons. `nb_variantes_vues` conserve l'information.
- **Sous-objets `prix` et `evaluation`** : regroupent les champs qui vont ensemble et se lisent naturellement dans les requêtes (`prix.actuel`, `evaluation.note`). `evaluation` vaut `null` quand le produit n'a pas encore d'avis : une note de 0 serait fausse et fausserait les moyennes.
- **`categories` (tableau) et `categorie` (chaîne)** : `categorie` garde la catégorie principale (la première vue) pour les filtres simples ; le tableau conserve toutes les catégories, ce qui est naturel dans un modèle document et sert à la vue MapReduce.
- **Types réels** (nombres décimaux, entiers, `null`) : permettent les comparaisons (`$lt`, `$gte`), le tri et les statistiques (`_stats`) directement dans CouchDB.
- **`date_extraction`** : les prix changent souvent ; la date indique à quel moment la donnée était vraie.

## 5. Import dans CouchDB et vérifications
Script : `couchdb/importer.py` — lit les identifiants dans `.env`, crée la base `decathlon` (`--reset` la supprime et la recrée), importe `data/donnees.json` par lots de 500 avec `_bulk_docs`, puis vérifie :

| Vérification | Résultat |
|---|---|
| Nombre de documents en base = nombre dans le JSON | <<À COMPLÉTER>> |
| Aucun doublon d'`_id` (JSON et base) | <<À COMPLÉTER>> |
| `prix.actuel` est un nombre partout | <<À COMPLÉTER>> |
| `evaluation.nb_avis` est un entier partout | <<À COMPLÉTER>> |
| Accents intacts (3 documents relus) | <<À COMPLÉTER>> |

La base peut être recréée entièrement à partir du JSON, sans refaire le scraping (voir README, « Reproduire le travail »).

<<À COMPLÉTER : capture d'écran de Fauxton montrant la base `decathlon` et son nombre de documents>>

## 6. Requêtes
Index et vue versionnés : `couchdb/index_q1_filtre.json`, `couchdb/index_q2_avis.json`, `couchdb/design_stats.json`. Exécution : `python couchdb/lancer_requetes.py --base decathlon`. Résultats complets : `couchdb/resultats/`.

### Q1 — Mango : filtre multicritère
Produits d'une catégorie, sous un prix maximal, avec une note d'au moins 4,5. Index sur `categorie`, `prix.actuel`, `evaluation.note`.
```json
{
  "selector": {
    "categorie": "<<À COMPLÉTER>>",
    "prix.actuel": { "$lt": <<À COMPLÉTER>> },
    "evaluation.note": { "$gte": 4.5 }
  },
  "fields": ["_id", "nom", "marque", "prix.actuel", "evaluation"],
  "use_index": ["idx-q1-filtre", "categorie-prix-note"]
}
```
Extrait du résultat : <<À COMPLÉTER : 3 à 5 lignes de couchdb/resultats/q1_filtre.json>>

Interprétation : <<À COMPLÉTER : nombre de produits trouvés, marques dominantes, ce que cela dit de l'offre bien notée à petit prix>>

### Q2 — Mango : les 10 produits les plus commentés
Tri décroissant sur `evaluation.nb_avis`, limite 10. Le sélecteur ne garde que les documents où `evaluation.nb_avis` existe et est un nombre (condition nécessaire pour que CouchDB utilise l'index trié `idx-q2-avis`).
```json
{
  "selector": { "evaluation.nb_avis": { "$exists": true, "$type": "number" } },
  "fields": ["_id", "nom", "marque", "categorie", "evaluation"],
  "sort": [{ "evaluation.nb_avis": "desc" }],
  "use_index": ["idx-q2-avis", "nb-avis-desc"],
  "limit": 10
}
```
Extrait du résultat : <<À COMPLÉTER>>

Interprétation : <<À COMPLÉTER : quels types de produits attirent le plus d'avis, lien entre popularité et note>>

### Q3 — MapReduce : prix moyen par catégorie
Vue `_design/stats/_view/prix_par_categorie` : la fonction map émet `[catégorie]` → `prix.actuel` pour **chaque** élément du tableau `categories` ; le reducer intégré `_stats` calcule somme, nombre, min et max ; la requête utilise `group_level=1`. La moyenne = `sum / count` (calculée par le script).
```javascript
function (doc) {
  if (doc.prix && typeof doc.prix.actuel === 'number' && Array.isArray(doc.categories)) {
    doc.categories.forEach(function (categorie) { emit([categorie], doc.prix.actuel); });
  }
}
```
Extrait du résultat : <<À COMPLÉTER : tableau catégorie / nombre / moyenne / min / max>>

Interprétation : <<À COMPLÉTER>>. Remarque : un produit présent dans plusieurs catégories est compté dans chacune ; la somme des `count` est donc supérieure au nombre de documents.

## 7. Dépôt et base
- Lien GitHub : https://github.com/5edrickk/scrapeverst
- Nom de la base CouchDB : `decathlon`

## 8. Avis sur les technologies
- **Python (requests + BeautifulSoup)** : <<À COMPLÉTER — ex. simple à mettre en place, mais dépend de la structure HTML du site qui peut changer>>
- **CouchDB** : <<À COMPLÉTER — ex. import JSON direct, Fauxton pratique ; Mango simple pour les filtres mais exige des index adaptés au tri ; MapReduce puissant pour les agrégats mais moins intuitif que SQL>>
- **Limites rencontrées** : limite de requêtes du site (HTTP 429), données moins détaillées sur les pages de catégories, <<À COMPLÉTER>>

## 9. Contribution de chaque membre
| Membre | Tâches | Pourcentage |
|---|---|---|
| Abdoulaye Dembélé | <<À COMPLÉTER>> | <<À COMPLÉTER>> % |
| Sedrick <<À COMPLÉTER>> | <<À COMPLÉTER>> | <<À COMPLÉTER>> % |

## 10. Utilisation de l'IA
Nous avons utilisé un assistant d'IA (Claude, via Claude Code) pour :
- écrire une première version des scripts de collecte, de nettoyage (`nettoyage/nettoyer.py`), d'import (`couchdb/importer.py`) et de requêtes (`couchdb/lancer_requetes.py`) ;
- générer un échantillon **fictif** (`data/echantillon_listes.csv`) imitant le format brut, pour tester la chaîne sans faire de requêtes au site ;
- rédiger la structure de ce rapport et du README.

Vérifications faites par l'équipe :
- exécution de toute la chaîne sur l'échantillon fictif dans une base séparée `decathlon_test` (nettoyage, import, vérifications automatiques, trois requêtes) ;
- contrôle manuel des résultats des requêtes sur l'échantillon (ex. Q1 recalculée à la main) ;
- <<À COMPLÉTER : vérifications sur les vraies données — documents comparés avec le site, relecture du code, ajustements faits>>

Toutes les données du rapport (chiffres, extraits de résultats) proviennent de l'exécution des scripts sur les vraies données, pas de l'IA.
