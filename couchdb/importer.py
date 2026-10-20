"""Importe data/donnees.json dans CouchDB puis vérifie le résultat.

Permet de recréer toute la base à partir du JSON, sans refaire le scraping.
Identifiants lus dans .env : COUCHDB_URL, COUCHDB_USER, COUCHDB_PASSWORD.

Exemples :
    python couchdb/importer.py --reset
    python couchdb/importer.py --base decathlon_test --reset
"""

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.parse import quote

import requests
from dotenv import load_dotenv

RACINE = Path(__file__).resolve().parent.parent
ENTREE_DEFAUT = RACINE / "data" / "donnees.json"
BASE_DEFAUT = "decathlon"
TAILLE_LOT = 500


def connexion():
    load_dotenv(RACINE / ".env")
    url = os.environ.get("COUCHDB_URL", "http://localhost:5984").rstrip("/")
    utilisateur = os.environ.get("COUCHDB_USER")
    mot_de_passe = os.environ.get("COUCHDB_PASSWORD")
    if not utilisateur or not mot_de_passe:
        sys.exit("COUCHDB_USER et COUCHDB_PASSWORD doivent être définis dans .env (voir .env.example).")
    session = requests.Session()
    session.auth = (utilisateur, mot_de_passe)
    return session, url


def preparer_base(session, url_base, reset):
    if reset:
        reponse = session.delete(url_base)
        if reponse.status_code not in (200, 404):
            reponse.raise_for_status()
        print(f"Base supprimée (--reset) : {url_base}")
    reponse = session.put(url_base)
    if reponse.status_code == 412:
        print(f"Base déjà existante : {url_base}")
    else:
        reponse.raise_for_status()
        print(f"Base créée : {url_base}")


def importer(session, url_base, documents):
    erreurs = []
    for debut in range(0, len(documents), TAILLE_LOT):
        lot = documents[debut:debut + TAILLE_LOT]
        reponse = session.post(f"{url_base}/_bulk_docs", json={"docs": lot})
        reponse.raise_for_status()
        erreurs += [r for r in reponse.json() if "error" in r]
        print(f"  lot {debut // TAILLE_LOT + 1} : {len(lot)} documents envoyés")
    for erreur in erreurs[:10]:
        print(f"  ERREUR {erreur['id']} : {erreur['error']} ({erreur.get('reason', '')})")
    return erreurs


def tous_les_documents(session, url_base):
    reponse = session.get(f"{url_base}/_all_docs", params={"include_docs": "true"})
    reponse.raise_for_status()
    return [ligne["doc"] for ligne in reponse.json()["rows"] if not ligne["id"].startswith("_design/")]


def verifier(session, url_base, documents):
    """Affiche chaque vérification ; retourne True si toutes passent."""
    resultats = []

    def controle(nom, ok, detail=""):
        resultats.append(ok)
        print(f"  [{'OK' if ok else 'ÉCHEC'}] {nom}{' : ' + detail if detail else ''}")

    ids_json = [doc["_id"] for doc in documents]
    controle("aucun doublon d'_id dans le JSON", len(ids_json) == len(set(ids_json)),
             f"{len(ids_json)} _id, {len(set(ids_json))} distincts")

    en_base = tous_les_documents(session, url_base)
    ids_base = [doc["_id"] for doc in en_base]
    controle("nombre de documents = nombre du JSON", len(en_base) == len(documents),
             f"{len(en_base)} en base, {len(documents)} dans le JSON")
    controle("aucun doublon d'_id en base", len(ids_base) == len(set(ids_base)))
    controle("mêmes _id dans la base et le JSON", set(ids_base) == set(ids_json))

    mauvais_prix = [d["_id"] for d in en_base
                    if not isinstance(d["prix"]["actuel"], (int, float)) or isinstance(d["prix"]["actuel"], bool)]
    controle("prix.actuel est un nombre", not mauvais_prix, ", ".join(mauvais_prix[:5]))
    mauvais_avis = [d["_id"] for d in en_base if d.get("evaluation") is not None
                    and d["evaluation"].get("nb_avis") is not None
                    and not (isinstance(d["evaluation"]["nb_avis"], int) and not isinstance(d["evaluation"]["nb_avis"], bool))]
    avec_avis = sum(1 for d in en_base if (d.get("evaluation") or {}).get("nb_avis") is not None)
    controle("evaluation.nb_avis est un entier", not mauvais_avis,
             f"{avec_avis} documents avec nb_avis" + (f" ; fautifs : {', '.join(mauvais_avis[:5])}" if mauvais_avis else ""))

    # Accents : on relit un par un 3 documents dont le nom contient un caractère non ASCII.
    par_id = {doc["_id"]: doc for doc in documents}
    accentues = [doc["_id"] for doc in documents if any(ord(c) > 127 for c in (doc["nom"] or ""))][:3]
    for _id in accentues:
        relu = session.get(f"{url_base}/{quote(_id, safe='')}").json()
        controle(f"accents intacts sur {_id}", relu["nom"] == par_id[_id]["nom"], relu["nom"])
    if not accentues:
        controle("accents intacts", False, "aucun nom accentué trouvé dans le JSON")
    return all(resultats)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--entree", type=Path, default=ENTREE_DEFAUT, help="tableau JSON à importer")
    parser.add_argument("--base", default=BASE_DEFAUT, help="nom de la base CouchDB")
    parser.add_argument("--reset", action="store_true", help="supprime et recrée la base avant l'import")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    with open(args.entree, encoding="utf-8") as f:
        documents = json.load(f)
    session, url = connexion()
    url_base = f"{url}/{args.base}"

    preparer_base(session, url_base, args.reset)
    print(f"Import de {len(documents)} documents par lots de {TAILLE_LOT} :")
    erreurs = importer(session, url_base, documents)
    print(f"{len(documents) - len(erreurs)} documents importés, {len(erreurs)} refusés"
          + (" (base existante : relancer avec --reset)" if erreurs else ""))
    print("Vérifications :")
    if not verifier(session, url_base, documents) or erreurs:
        sys.exit(1)
    print(f"Base « {args.base} » prête.")


if __name__ == "__main__":
    main()
