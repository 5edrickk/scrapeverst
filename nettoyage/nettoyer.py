"""Nettoie le CSV brut des pages de catégories et produit un document JSON par modèle.

Le CSV d'entrée n'est jamais modifié. Sorties : le tableau JSON (--sortie) et un
rapport texte (--rapport). Code de sortie 1 si le nombre de modèles est sous --minimum.

Exemples :
    python nettoyage/nettoyer.py --entree data/echantillon_listes.csv --minimum 0
    python nettoyage/nettoyer.py --entree data/raw/listes_raw.csv
"""

import argparse
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
ENTREE_DEFAUT = RACINE / "data" / "raw" / "listes_raw.csv"
SORTIE_DEFAUT = RACINE / "data" / "donnees.json"
RAPPORT_DEFAUT = RACINE / "data" / "rapport_nettoyage.txt"
MINIMUM_DEFAUT = 2500

CHAMPS_SUIVIS = [
    "nom", "marque", "categorie", "prix.actuel", "prix.ancien", "prix.rabais_pct",
    "evaluation", "nb_couleurs", "etiquette", "url_source", "id_variante",
    "image_url", "date_extraction",
]


def texte(valeur):
    """Remplace les espaces insécables, réduit les espaces multiples ; '' -> None."""
    if valeur is None:
        return None
    propre = re.sub(r"\s+", " ", valeur.replace("\xa0", " ").replace(" ", " ")).strip()
    return propre or None


def decimal(valeur):
    """« 11,99 $ » -> 11.99 ; « 1 299,00 $ » -> 1299.0 ; « 4.7 » -> 4.7."""
    propre = texte(valeur)
    if propre is None:
        return None
    chiffres = re.sub(r"[^\d,.]", "", propre).replace(",", ".")
    try:
        return float(chiffres)
    except ValueError:
        return None


def entier(valeur):
    """« (1 906) » -> 1906 ; « 4 couleurs » -> 4 ; « 33% de réduction » -> 33."""
    propre = texte(valeur)
    if propre is None:
        return None
    trouve = re.search(r"\d[\d ]*", propre)
    return int(trouve.group().replace(" ", "")) if trouve else None


def nom_sans_marque(nom_complet, marque):
    if nom_complet and marque and nom_complet.casefold().startswith(marque.casefold() + " "):
        return nom_complet[len(marque):].strip()
    return nom_complet


def construire_document(ligne):
    marque = texte(ligne["marque_brut"])
    note = decimal(ligne["note_brut"])
    nb_avis = entier(ligne["nb_avis_brut"])
    categorie = texte(ligne["categorie_page"])
    return {
        "_id": f"decathlon-{texte(ligne['id_modele'])}",
        "nom": nom_sans_marque(texte(ligne["nom_complet_brut"]), marque),
        "marque": marque,
        "categorie": categorie,
        "categories": [categorie] if categorie else [],
        "prix": {
            "actuel": decimal(ligne["prix_actuel_brut"]),
            "ancien": decimal(ligne["ancien_prix_brut"]),
            "rabais_pct": entier(ligne["rabais_brut"]),
            "devise": "CAD",
        },
        # Sans note, on ne garde pas d'évaluation : un nb_avis seul n'a pas de sens.
        "evaluation": {"note": note, "nb_avis": nb_avis} if note is not None else None,
        "nb_couleurs": entier(ligne["nb_couleurs_brut"]),
        "etiquette": texte(ligne["etiquette_brut"]),
        "nb_variantes_vues": 1,
        "url_source": texte(ligne["url_source"]),
        "id_variante": texte(ligne["id_variante"]),
        "image_url": texte(ligne["image_url"]),
        "date_extraction": texte(ligne["date_extraction"]),
    }


def valeur_champ(doc, champ):
    valeur = doc
    for morceau in champ.split("."):
        valeur = valeur.get(morceau) if isinstance(valeur, dict) else None
    return valeur


def nettoyer(lignes):
    documents = {}
    variantes = {}
    ecarts_prix = []
    sans_id = 0
    for ligne in lignes:
        id_modele = texte(ligne["id_modele"])
        if id_modele is None:
            sans_id += 1
            continue
        nouveau = construire_document(ligne)
        doc = documents.get(id_modele)
        if doc is None:
            documents[id_modele] = nouveau
            variantes[id_modele] = {nouveau["id_variante"]}
            continue
        # Doublon : on garde la première ligne, on fusionne catégories et variantes.
        for categorie in nouveau["categories"]:
            if categorie not in doc["categories"]:
                doc["categories"].append(categorie)
        variantes[id_modele].add(nouveau["id_variante"])
        doc["nb_variantes_vues"] = len(variantes[id_modele])
        if nouveau["prix"]["actuel"] != doc["prix"]["actuel"]:
            ecarts_prix.append((doc["_id"], doc["prix"]["actuel"], nouveau["prix"]["actuel"], nouveau["id_variante"]))
    return list(documents.values()), ecarts_prix, sans_id


def ecrire_rapport(chemin, entree, nb_lignes, documents, ecarts_prix, sans_id, minimum):
    manquants = Counter()
    for doc in documents:
        for champ in CHAMPS_SUIVIS:
            if valeur_champ(doc, champ) is None:
                manquants[champ] += 1
    nb_docs = len(documents)
    lignes = [
        "Rapport de nettoyage",
        f"Fichier d'entrée : {entree}",
        "",
        f"Lignes avant nettoyage         : {nb_lignes}",
        f"Lignes sans id_modele ignorées : {sans_id}",
        f"Modèles distincts après        : {nb_docs}",
        f"Doublons retirés               : {nb_lignes - sans_id - nb_docs}",
        "",
        "Valeurs manquantes (null) par champ, sur les documents finaux :",
    ]
    for champ in CHAMPS_SUIVIS:
        pct = 100 * manquants[champ] / nb_docs if nb_docs else 0
        lignes.append(f"  {champ:<18} {manquants[champ]:>6}  ({pct:.1f} %)")
    lignes += ["", f"Modèles dont les variantes ont des prix différents (premier prix gardé) : {len(ecarts_prix)}"]
    for _id, garde, autre, variante in ecarts_prix:
        lignes.append(f"  {_id} : gardé {garde} $, vu aussi {autre} $ (variante {variante})")
    lignes.append("")
    if nb_docs < minimum:
        lignes.append(f"AVERTISSEMENT : {nb_docs} modèles après nettoyage, sous le minimum exigé de {minimum}.")
    else:
        lignes.append(f"OK : {nb_docs} modèles (minimum exigé : {minimum}).")
    chemin.write_text("\n".join(lignes) + "\n", encoding="utf-8")
    return "\n".join(lignes)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--entree", type=Path, default=ENTREE_DEFAUT, help="CSV brut (lu seulement)")
    parser.add_argument("--sortie", type=Path, default=SORTIE_DEFAUT, help="tableau JSON produit")
    parser.add_argument("--rapport", type=Path, default=RAPPORT_DEFAUT, help="rapport texte produit")
    parser.add_argument("--minimum", type=int, default=MINIMUM_DEFAUT, help="nombre minimal de modèles attendu")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    with open(args.entree, encoding="utf-8", newline="") as f:
        lignes = list(csv.DictReader(f))
    documents, ecarts_prix, sans_id = nettoyer(lignes)

    args.sortie.parent.mkdir(parents=True, exist_ok=True)
    with open(args.sortie, "w", encoding="utf-8") as f:
        json.dump(documents, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(ecrire_rapport(args.rapport, args.entree, len(lignes), documents, ecarts_prix, sans_id, args.minimum))
    print(f"\n-> {args.sortie}\n-> {args.rapport}")
    if len(documents) < args.minimum:
        sys.exit(1)


if __name__ == "__main__":
    main()
