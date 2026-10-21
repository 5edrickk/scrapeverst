# Projet 2 – Collecter et exploiter des données Web avec CouchDB

Ce projet collecte des données de produits de sport sur le site de **Decathlon Canada** (https://www.decathlon.ca/fr) à l'aide de Python (`requests` + `BeautifulSoup`).
Les données passent par une chaîne complète : **CSV brut → nettoyage → JSON → base CouchDB → 3 requêtes** (deux requêtes Mango et une vue MapReduce).
Tout le dépôt est conçu pour qu'on puisse recréer la base et reproduire les résultats **sans refaire le scraping**.

Cours : Exploration de nouvelles technologies — Cégep de Sherbrooke.

## Équipe

| Membre | Matricule |
|---|---|
| Abdoulaye Dembélé | 202452396 |
| Sedrick <<À COMPLÉTER PAR L'ÉQUIPE : nom de famille>> | <<À COMPLÉTER PAR L'ÉQUIPE : matricule>> |
| Catherine Guiléne Ngo Ebga | 206343124 |

Dépôt GitHub : https://github.com/5edrickk/scrapeverst

## Structure du dépôt

```text
scrapeverst/
├── README.md                     ce fichier : installation et reproduction
├── rapport.md                    rapport du projet (méthode, nettoyage, requêtes, avis)
├── requirements.txt              dépendances Python, versions figées
├── .env.example                  modèle du fichier .env (aucun mot de passe)
├── .gitignore                    exclut .venv/, .env, __pycache__/, remise.zip
├── creer_zip.py                  construit remise.zip et vérifie qu'aucun mot de passe n'y figure
├── images/                       captures d'écran de Fauxton utilisées dans rapport.md
├── scraper/                      collecte (à ne pas relancer sans raison, voir plus bas)
│   ├── commun.py                 client HTTP « poli » partagé (délai, User-Agent, arrêt sur 403/429)
│   ├── collecter_listes.py       pages de catégories -> data/raw/listes_raw.csv (méthode retenue)
│   ├── collecter_urls.py         sitemap produits -> data/urls_echantillon.csv
│   ├── collecter_produits.py     fiches produits détaillées -> data/raw/produits_raw.csv
│   └── test_sitemap.py           test d'accès au sitemap (première étape du projet)
├── nettoyage/
│   └── nettoyer.py               CSV brut -> data/donnees.json + data/rapport_nettoyage.txt
├── couchdb/
│   ├── importer.py               data/donnees.json -> base CouchDB (+ vérifications automatiques)
│   ├── lancer_requetes.py        crée les index et la vue, exécute Q1, Q2, Q3
│   ├── index_q1_filtre.json      index Mango de Q1 (categorie, prix.actuel, evaluation.note)
│   ├── index_q2_avis.json        index Mango de Q2 (evaluation.nb_avis décroissant)
│   ├── design_stats.json         design document _design/stats (vue MapReduce de Q3)
│   └── resultats/                résultats de Q1, Q2, Q3 (requête envoyée + réponse de CouchDB)
└── data/
    ├── raw/
    │   ├── listes_raw.csv        CSV brut principal (pages de catégories)
    │   ├── produits_raw.csv      second CSV brut (fiches produits détaillées)
    │   └── crawl_journal.csv     journal des 400 requêtes de la collecte
    ├── urls_echantillon.csv      échantillon d'URL de produits (entrée de collecter_produits.py)
    ├── donnees.json              données nettoyées, prêtes pour CouchDB
    ├── rapport_nettoyage.txt     rapport chiffré du nettoyage
    └── echantillon_listes.csv    petit échantillon FICTIF au format brut, pour les tests
```

## Prérequis

- **Python 3.14** (version utilisée : 3.14.2) — vérifier avec `python --version`
- **Git**
- **Docker Desktop** (CouchDB tourne dans un conteneur ; version utilisée : CouchDB 3.5.3, image `couchdb:3`)

Toutes les commandes ci-dessous sont pour **PowerShell (Windows)** et se lancent **depuis la racine du dépôt**.

## Installation

```powershell
git clone https://github.com/5edrickk/scrapeverst.git
cd scrapeverst

python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Si PowerShell refuse d'exécuter `Activate.ps1` (« l'exécution de scripts est désactivée sur ce système »), autorisez les scripts **pour la fenêtre PowerShell en cours seulement**, puis réactivez :

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

Une fois l'environnement activé, l'invite commence par `(.venv)`.

## Configuration

```powershell
Copy-Item .env.example .env
notepad .env
```

| Variable | Rôle |
|---|---|
| `COUCHDB_URL` | adresse de CouchDB, par défaut `http://localhost:5984` |
| `COUCHDB_USER` | utilisateur administrateur de CouchDB (`admin` dans le modèle) |
| `COUCHDB_PASSWORD` | mot de passe de cet utilisateur : choisissez-le vous-même, il doit être **identique** à celui donné au conteneur Docker (section suivante) |
| `SCRAPER_CONTACT` | adresse courriel placée dans le `User-Agent` des scripts de collecte ; inutile pour recréer la base |

Le fichier `.env` est ignoré par Git (`.gitignore`) : il n'est **jamais commité**. Aucun mot de passe ne figure dans le dépôt : `.env.example` contient seulement les noms des variables.

## Démarrer CouchDB avec Docker

**Option simple** : `docker compose up -d` à la racine (lit `COUCHDB_USER` et `COUCHDB_PASSWORD` dans `.env`, données conservées dans un volume). Sinon, la méthode manuelle ci-dessous.

**Première fois** : créer le conteneur. Le mot de passe est saisi au clavier et placé dans une variable d'environnement de la session PowerShell ; l'option `-e COUCHDB_PASSWORD` (sans valeur) demande à Docker de le lire dans cette variable. Il n'apparaît donc ni dans la commande ni dans l'historique.

```powershell
$env:COUCHDB_PASSWORD = Read-Host "Mot de passe CouchDB (le même que dans .env)"
docker run -d --name couchdb -p 5984:5984 -e COUCHDB_USER=admin -e COUCHDB_PASSWORD couchdb:3
```

**Les fois suivantes** (après un redémarrage du PC, par exemple), le conteneur existe déjà : il suffit de le redémarrer.

```powershell
docker start couchdb
```

**Vérifier** que CouchDB répond :

```powershell
Invoke-RestMethod http://localhost:5984/
```

La réponse contient `couchdb : Welcome`. L'interface d'administration **Fauxton** est accessible à http://localhost:5984/_utils (connexion avec l'utilisateur et le mot de passe du `.env`).

## Recréer la base sans refaire le scraping

C'est la section principale : elle recrée la base `decathlon` à partir de `data/donnees.json`, fourni dans le dépôt.

```powershell
python couchdb/importer.py --entree data/donnees.json --base decathlon --reset
```

- `--entree` : le fichier JSON à importer (`data/donnees.json` est aussi la valeur par défaut) ;
- `--base` : le nom de la base (`decathlon` par défaut) ;
- `--reset` : supprime la base si elle existe, puis la recrée. Sans cette option, l'import dans une base déjà remplie échoue (voir *Dépannage*).

Le script envoie les documents par lots de 500, puis fait ses propres vérifications. Résultat attendu :

```text
Import de 2578 documents par lots de 500 :
...
2578 documents importés, 0 refusés
Vérifications :
  [OK] aucun doublon d'_id dans le JSON : 2578 _id, 2578 distincts
  [OK] nombre de documents = nombre du JSON : 2578 en base, 2578 dans le JSON
  [OK] aucun doublon d'_id en base
  [OK] mêmes _id dans la base et le JSON
  [OK] prix.actuel est un nombre
  [OK] evaluation.nb_avis est un entier : ...
  [OK] accents intacts sur ...
Base « decathlon » prête.
```

**Vérifier** le nombre de documents (le script lit les identifiants dans `.env`) :

```powershell
python -c "import sys; sys.path.insert(0, 'couchdb'); from importer import connexion; s, u = connexion(); print(s.get(u + '/decathlon').json()['doc_count'])"
```

Juste après l'import, la commande affiche **2578** (un document par modèle de produit). Après la section suivante, elle affiche **2581**, et Fauxton aussi : les requêtes ajoutent **3 design documents** (`_design/idx-q1-filtre`, `_design/idx-q2-avis` et `_design/stats`), qui ne sont pas des produits.

## Reproduire les requêtes

```powershell
python couchdb/lancer_requetes.py --base decathlon
```

Le script :
1. crée les deux index Mango à partir de `couchdb/index_q1_filtre.json` et `couchdb/index_q2_avis.json` ;
2. enregistre le design document de la vue à partir de `couchdb/design_stats.json` (il le met à jour s'il existe déjà) ;
3. exécute les trois requêtes, affiche les résultats et les écrit dans `couchdb/resultats/` :

| Requête | Type | Fichier de résultat | Ce qu'elle fait |
|---|---|---|---|
| **Q1** | Mango | `q1_filtre.json` | filtre multicritère : les produits de la catégorie « Polaires de randonnée » à moins de 30 $ et notés au moins 4,5/5 |
| **Q2** | Mango | `q2_plus_commentes.json` | les 10 produits qui ont le plus d'avis, triés par nombre d'avis décroissant |
| **Q3** | MapReduce | `q3_prix_par_categorie.json` | nombre de produits, prix moyen, minimum et maximum par catégorie (vue `_design/stats`, réducteur `_stats`) |

Chaque fichier contient la requête envoyée et la réponse complète de CouchDB. Les paramètres de Q1 et Q2 sont des constantes en haut de `couchdb/lancer_requetes.py`.

Les fichiers de `couchdb/resultats/` sont versionnés et sont réécrits à chaque exécution. Après une exécution sur la base `decathlon` recréée comme ci-dessus, `q1_filtre.json` et `q2_plus_commentes.json` sont **identiques** à la version du dépôt (15 produits pour Q1, 10 pour Q2). Pour Q3, les comptes, minimums, maximums et moyennes des 396 catégories sont identiques, mais `git status` peut signaler `q3_prix_par_categorie.json` comme modifié : les champs internes `sum` et `sumsqr` peuvent différer au dernier chiffre (ex. `812.77` contre `812.7700000000001`), car CouchDB additionne les prix dans un ordre qui dépend de l'organisation interne de la base. Pour revenir à la version du dépôt : `git restore couchdb/resultats`.

## Refaire le nettoyage depuis les CSV bruts

Facultatif : `data/donnees.json` est déjà fourni. Pour le régénérer depuis le CSV brut (qui n'est jamais modifié) :

```powershell
python nettoyage/nettoyer.py --entree data/raw/listes_raw.csv
```

Fichiers produits (valeurs par défaut, modifiables avec `--sortie` et `--rapport`) :
- `data/donnees.json` : un document JSON par modèle de produit ;
- `data/rapport_nettoyage.txt` : le rapport chiffré du nettoyage.

Chiffres attendus dans le rapport :

| Mesure | Valeur |
|---|---|
| Lignes avant nettoyage | 6009 |
| Lignes écartées (services d'atelier, sans marque ni image) | 2 |
| Doublons retirés (même modèle vu plusieurs fois) | 3429 |
| Modèles distincts après nettoyage | 2578 |

Le script se termine avec le code de sortie 1 s'il obtient moins de 2500 modèles (option `--minimum`).

## Refaire l'extraction (facultatif, déconseillé)

**Il n'est pas nécessaire de relancer la collecte** : les CSV bruts sont dans `data/raw/`. La relancer sollicite inutilement le site et ne redonnera pas exactement les mêmes données (prix, avis et produits changent). Les scripts sont décrits ici pour comprendre comment les données ont été obtenues.

Règles communes : une seule requête à la fois, `User-Agent` identifiant le projet avec l'adresse `SCRAPER_CONTACT` du `.env`, respect du `robots.txt` du site (aucune URL `/api/`, aucune page de filtre ou de tri), aucune redirection suivie automatiquement, et **arrêt immédiat sur un HTTP 403 ou 429, sans nouvelle tentative**. Aucun mécanisme de protection du site ne doit être contourné.

- **`scraper/collecter_listes.py`** (méthode retenue) : lit le sitemap des catégories (`sitemap-index.xml`), puis visite les pages de catégories `/fr/...` et leurs pages suivantes (`?from=<n>&size=40`, lues dans le lien « page suivante »). Il écrit une ligne brute par tuile produit dans `data/raw/listes_raw.csv` et note chaque requête dans `data/raw/crawl_journal.csv`. Il attend **5 secondes** entre deux requêtes et s'arrête à 3000 modèles distincts, quand la file est vide, ou après 400 requêtes. Sur un 403 ou 429, il note le code et l'en-tête `Retry-After` dans le journal, puis s'arrête (code de sortie 2). Il peut **reprendre** là où il s'est arrêté grâce à `data/raw/crawl_etat.json` (fichier de travail non versionné).
- **`scraper/collecter_produits.py`** (première méthode) : visite les fiches produits de `data/urls_echantillon.csv` (produit par `scraper/collecter_urls.py`) et extrait des données plus détaillées (description, couleur, caractéristiques, empreinte CO2) dans `data/raw/produits_raw.csv`. Après 40 fiches, le site a répondu **HTTP 429 (Too Many Requests)** : le script s'est arrêté comme prévu, et la collecte est passée aux pages de catégories, qui demandent environ 40 fois moins de requêtes.

## Données fournies

| Fichier | Contenu |
|---|---|
| `data/raw/listes_raw.csv` | CSV brut principal : 6009 tuiles produits issues de 396 pages de catégories (2580 modèles), valeurs telles qu'affichées sur le site |
| `data/raw/produits_raw.csv` | second CSV brut : 40 fiches produits détaillées, collectées avant le HTTP 429 |
| `data/urls_echantillon.csv` | échantillon de 3500 URL de produits tiré du sitemap ; entrée de `collecter_produits.py` |
| `data/donnees.json` | données nettoyées : 2578 documents JSON, un par modèle, prêts pour CouchDB |
| `data/rapport_nettoyage.txt` | rapport du nettoyage : lignes écartées, doublons, valeurs manquantes par champ |

## Utilisation de l'IA

Nous avons utilisé Claude et Claude Code pour écrire et tester les scripts de collecte, de nettoyage, d'import et de requêtes, ainsi qu'une première version du rapport et de ce README. Les résultats ont été vérifiés : tests sur un échantillon fictif dans une base séparée, vérifications automatiques de l'import, relecture du code et comparaison de valeurs avec le site. Le détail est dans la section « Utilisation de l'IA » de `rapport.md`.

Vérifications faites par l'équipe :
- **Abdoulaye Dembélé** : lancement et suivi du scraper ; validation du test sur 20 pages produit et des taux de champs vides ; arrêt de la collecte (après le HTTP 429 sur les pages produit, puis à 400 requêtes et 2580 modèles bruts sur les pages de catégories) ; vérification que CouchDB répond et que la base `decathlon` est bien importée.
- **Catherine Guiléne Ngo Ebga** : relecture de `nettoyage/nettoyer.py` et exécution complète du nettoyage (6009 lignes brutes → 2578 modèles) ; comparaison manuelle de 12 documents avec leur page Decathlon, qui a confirmé les prix et les notes.

## Dépannage

**Docker n'est pas démarré** — `docker` affiche `failed to connect to the docker API ... dockerDesktopLinuxEngine`. Lancez Docker Desktop, attendez « Engine running », puis relancez la commande.

**Le conteneur existe déjà** — `docker run` affiche `Conflict. The container name "/couchdb" is already in use`. Utilisez `docker start couchdb` au lieu de `docker run`. Le mot de passe est celui choisi lors de la **création** du conteneur ; s'il est perdu, supprimez le conteneur avec `docker rm -f couchdb` (cela supprime aussi ses bases), puis recréez-le et réimportez les données.

**Le port 5984 est déjà utilisé** — un autre CouchDB tourne déjà. Arrêtez-le, ou utilisez-le directement en mettant ses identifiants dans `.env`.

**PowerShell bloque `Activate.ps1`** — lancez `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`, puis réactivez l'environnement. Ce réglage ne vaut que pour la fenêtre en cours.

**`COUCHDB_USER et COUCHDB_PASSWORD doivent être définis dans .env`** — le fichier `.env` manque ou le mot de passe est vide : voir *Configuration*.

**Erreur 401 (`Unauthorized`)** — le mot de passe du `.env` ne correspond pas à celui du conteneur.

**Conflit d'`_id` à l'import** — sans `--reset`, importer dans une base qui contient déjà les documents produit des erreurs `conflict (Document update conflict.)`, puis `0 documents importés, 2578 refusés (base existante : relancer avec --reset)`, et le script s'arrête avec le code de sortie 1. Relancez avec `--reset`.

**Base `decathlon_test`** — c'est la base de test utilisée pendant le développement avec l'échantillon **fictif** `data/echantillon_listes.csv`. Elle ne contient pas les vraies données et ne sert pas à la remise ; on peut la supprimer dans Fauxton. Pour retester la chaîne sur l'échantillon fictif **sans écraser les vrais fichiers** :

```powershell
python nettoyage/nettoyer.py --entree data/echantillon_listes.csv --sortie $env:TEMP\echantillon.json --rapport $env:TEMP\echantillon_rapport.txt --minimum 0
python couchdb/importer.py --entree $env:TEMP\echantillon.json --base decathlon_test --reset
python couchdb/lancer_requetes.py --base decathlon_test
git restore couchdb/resultats
```

La dernière ligne est nécessaire : `lancer_requetes.py` écrit toujours dans `couchdb/resultats/`, quelle que soit la base ; `git restore` remet les résultats des vraies données.
