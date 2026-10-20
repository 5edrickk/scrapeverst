"""Crée les index et la vue, exécute les trois requêtes et sauvegarde leurs résultats.

Q1 (Mango) : filtre multicritère catégorie + prix maximal + note minimale.
Q2 (Mango) : les produits les plus commentés (tri décroissant sur evaluation.nb_avis).
Q3 (MapReduce) : prix moyen par catégorie (vue _design/stats, reducer _stats).

Résultats : couchdb/resultats/q1_filtre.json, q2_plus_commentes.json, q3_prix_par_categorie.json
(chaque fichier contient la requête envoyée et la réponse de CouchDB).

Exemple :
    python couchdb/lancer_requetes.py --base decathlon_test
"""

import argparse
import json
import sys
from pathlib import Path

from importer import BASE_DEFAUT, connexion

# Paramètres à ajuster quand les vraies données seront là.
Q1_CATEGORIE = "Polaires de randonnée"
Q1_PRIX_MAX = 30.0
Q1_NOTE_MIN = 4.5
Q2_LIMITE = 10

DOSSIER = Path(__file__).resolve().parent
DOSSIER_RESULTATS = DOSSIER / "resultats"
FICHIERS_INDEX = ["index_q1_filtre.json", "index_q2_avis.json"]
FICHIER_DESIGN = "design_stats.json"


def lire_json(nom):
    with open(DOSSIER / nom, encoding="utf-8") as f:
        return json.load(f)


def installer_index_et_vue(session, url_base):
    for nom in FICHIERS_INDEX:
        reponse = session.post(f"{url_base}/_index", json=lire_json(nom))
        reponse.raise_for_status()
        print(f"Index {nom} : {reponse.json()['result']}")
    design = lire_json(FICHIER_DESIGN)
    existant = session.get(f"{url_base}/{design['_id']}")
    if existant.status_code == 200:
        design["_rev"] = existant.json()["_rev"]
    reponse = session.put(f"{url_base}/{design['_id']}", json=design)
    reponse.raise_for_status()
    print(f"Design document {design['_id']} : enregistré")


def requete_q1():
    return {
        "selector": {
            "categorie": Q1_CATEGORIE,
            "prix.actuel": {"$lt": Q1_PRIX_MAX},
            "evaluation.note": {"$gte": Q1_NOTE_MIN},
        },
        "fields": ["_id", "nom", "marque", "prix.actuel", "evaluation"],
        "use_index": ["idx-q1-filtre", "categorie-prix-note"],
        "limit": 200,
    }


def requete_q2():
    return {
        "selector": {"evaluation.nb_avis": {"$exists": True, "$type": "number"}},
        "fields": ["_id", "nom", "marque", "categorie", "evaluation"],
        "sort": [{"evaluation.nb_avis": "desc"}],
        "use_index": ["idx-q2-avis", "nb-avis-desc"],
        "limit": Q2_LIMITE,
    }


def executer_mango(session, url_base, corps):
    reponse = session.post(f"{url_base}/_find", json=corps)
    reponse.raise_for_status()
    resultat = reponse.json()
    if "warning" in resultat:
        print(f"  AVERTISSEMENT CouchDB : {resultat['warning']}")
    return resultat


def executer_q3(session, url_base):
    parametres = {"group_level": 1}
    reponse = session.get(f"{url_base}/_design/stats/_view/prix_par_categorie", params=parametres)
    reponse.raise_for_status()
    resultat = reponse.json()
    for ligne in resultat["rows"]:
        stats = ligne["value"]
        stats["moyenne"] = round(stats["sum"] / stats["count"], 2)
    return {"vue": "_design/stats/_view/prix_par_categorie", "parametres": parametres}, resultat


def sauvegarder(nom, requete, resultat):
    DOSSIER_RESULTATS.mkdir(exist_ok=True)
    chemin = DOSSIER_RESULTATS / nom
    with open(chemin, "w", encoding="utf-8") as f:
        json.dump({"requete": requete, "resultat": resultat}, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return chemin


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base", default=BASE_DEFAUT, help="nom de la base CouchDB")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    session, url = connexion()
    url_base = f"{url}/{args.base}"
    installer_index_et_vue(session, url_base)

    print(f"\nQ1 : catégorie « {Q1_CATEGORIE} », prix < {Q1_PRIX_MAX} $, note >= {Q1_NOTE_MIN}")
    corps = requete_q1()
    resultat = executer_mango(session, url_base, corps)
    for doc in resultat["docs"]:
        print(f"  {doc['prix']['actuel']:>8.2f} $  {doc['evaluation']['note']}/5  {doc['marque']} – {doc['nom']}")
    print(f"  {len(resultat['docs'])} produits -> {sauvegarder('q1_filtre.json', corps, resultat)}")

    print(f"\nQ2 : les {Q2_LIMITE} produits les plus commentés")
    corps = requete_q2()
    resultat = executer_mango(session, url_base, corps)
    for doc in resultat["docs"]:
        print(f"  {doc['evaluation']['nb_avis']:>7} avis  {doc['evaluation']['note']}/5  {doc['marque']} – {doc['nom']}")
    print(f"  -> {sauvegarder('q2_plus_commentes.json', corps, resultat)}")

    print("\nQ3 : prix moyen par catégorie (MapReduce, _stats, group_level=1)")
    requete, resultat = executer_q3(session, url_base)
    for ligne in resultat["rows"]:
        s = ligne["value"]
        print(f"  {ligne['key'][0]:<35} {s['count']:>5} produits  moyenne {s['moyenne']:>8.2f} $  "
              f"(min {s['min']:.2f}, max {s['max']:.2f})")
    print(f"  -> {sauvegarder('q3_prix_par_categorie.json', requete, resultat)}")


if __name__ == "__main__":
    main()
