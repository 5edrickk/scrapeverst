"""Étape B : visite des pages produits de l'échantillon et extraction des valeurs brutes.

Écrit data/raw/produits_raw.csv ligne par ligne et peut reprendre là où il s'est arrêté.
Les pages en erreur sont journalisées dans data/raw/erreurs.csv.
"""

import argparse
import csv
import sys
from datetime import date, datetime

from bs4 import BeautifulSoup

from commun import DELAI_SECONDES, DOSSIER_DATA, DOSSIER_RAW, BlocageServeur, ClientPoli, ErreurPage

FICHIER_URLS = DOSSIER_DATA / "urls_echantillon.csv"
FICHIER_PRODUITS = DOSSIER_RAW / "produits_raw.csv"
FICHIER_ERREURS = DOSSIER_RAW / "erreurs.csv"

COLONNES = [
    "id_modele", "id_variante", "nb_variantes", "nom", "marque", "categories",
    "prix_brut", "note_brut", "nb_avis_brut", "description", "couleur",
    "empreinte_co2_brut", "caracteristiques_brut", "image_url", "url_source",
    "date_extraction",
]
COLONNES_ERREURS = ["date_heure", "id_modele", "url_source", "erreur"]

# Blocs de la section Spécifications qui ne décrivent pas le produit
BLOCS_SPECIFICATIONS_IGNORES = ("Contact UE sur la sécurité des produits",)


def texte(element):
    """Texte visible d'un élément, sans le texte réservé aux lecteurs d'écran."""
    if element is None:
        return ""
    for cache in element.select(".sr-only"):
        cache.decompose()
    return element.get_text(" ", strip=True)


def extraire_caracteristiques(soupe):
    section = soupe.select_one(".specifications")
    if section is None:
        return ""
    paires = []
    for titre in section.select(".specifications__block-title"):
        if titre.get_text(strip=True) in BLOCS_SPECIFICATIONS_IGNORES:
            continue
        for element in titre.find_next_siblings():
            if "specifications__block-title" in (element.get("class") or []):
                break
            for nom in element.select("dt.specifications__item-name") or (
                [element] if element.name == "dt" else []
            ):
                valeur = nom.find_next_sibling("dd")
                paires.append(f"{texte(nom)}: {texte(valeur)}")
            for ligne in element.select("p.specifications__item") or (
                [element] if element.name == "p" and "specifications__item" in (element.get("class") or []) else []
            ):
                paires.append(texte(ligne))
    return " | ".join(paires)


def extraire_empreinte_co2(soupe):
    compteur = soupe.select_one(".environmental-impact-carbon-counter")
    if compteur is None:
        return ""
    valeur = texte(compteur.select_one(".vp-title-xl"))
    unite = texte(compteur.select_one(".vp-overline"))
    return f"{valeur} {unite}".strip() if valeur else ""


def extraire_produit(html):
    """Extrait les champs bruts d'une page produit. Champ absent = chaîne vide."""
    soupe = BeautifulSoup(html, "lxml")
    bloc = soupe.select_one("section.product-view__buy-box")
    if bloc is None or bloc.find("h1") is None:
        return None

    couleur = ""
    for entete in bloc.select(".variant-selector-headline__text"):
        if texte(entete.select_one(".variant-selector-headline__label")) == "Couleur":
            couleur = texte(entete.select_one(".variant-selector-headline__value"))
            break

    return {
        "nom": texte(bloc.find("h1")),
        "marque": texte(bloc.select_one(".product-info__brand")),
        "categories": " > ".join(texte(e) for e in soupe.select("nav.breadcrumbs span.vp-body-s")),
        "prix_brut": texte(bloc.select_one(".buy-box__section--price .vp-price-amount")),
        "note_brut": texte(bloc.select_one(".review__fullstars__score")),
        "nb_avis_brut": texte(bloc.select_one(".review__fullstars__votes")),
        "description": texte(bloc.select_one(".product-info__description")),
        "couleur": couleur,
        "empreinte_co2_brut": extraire_empreinte_co2(soupe),
        "caracteristiques_brut": extraire_caracteristiques(soupe),
    }


def ressemble_a_un_blocage(html):
    """Page anti-robot (Incapsula, captcha) : on ne tente pas de la contourner."""
    debut = html[:20000].lower()
    return "_incapsula_resource" in debut or "captcha" in debut


def ids_deja_collectes():
    if not FICHIER_PRODUITS.exists():
        return set()
    with open(FICHIER_PRODUITS, encoding="utf-8", newline="") as fichier:
        return {ligne["id_modele"] for ligne in csv.DictReader(fichier)}


def ouvrir_en_ajout(chemin, colonnes):
    nouveau = not chemin.exists() or chemin.stat().st_size == 0
    fichier = open(chemin, "a", encoding="utf-8", newline="")
    ecrivain = csv.DictWriter(fichier, fieldnames=colonnes)
    if nouveau:
        ecrivain.writeheader()
        fichier.flush()
    return fichier, ecrivain


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limite", type=int, help="nombre maximal de pages à visiter")
    parser.add_argument("--delai", type=float, default=DELAI_SECONDES, help="secondes entre deux requêtes")
    args = parser.parse_args()

    with open(FICHIER_URLS, encoding="utf-8", newline="") as fichier:
        echantillon = list(csv.DictReader(fichier))

    deja_faits = ids_deja_collectes()
    a_faire = [ligne for ligne in echantillon if ligne["id_modele"] not in deja_faits]
    if args.limite is not None:
        a_faire = a_faire[: args.limite]
    print(f"{len(echantillon)} modèles dans l'échantillon, {len(deja_faits)} déjà collectés, "
          f"{len(a_faire)} à visiter (délai {args.delai} s)")

    client = ClientPoli(delai=args.delai)
    fichier_produits, ecrivain_produits = ouvrir_en_ajout(FICHIER_PRODUITS, COLONNES)
    fichier_erreurs, ecrivain_erreurs = ouvrir_en_ajout(FICHIER_ERREURS, COLONNES_ERREURS)
    reussis = echecs = 0

    def journaliser_erreur(ligne, message):
        ecrivain_erreurs.writerow({
            "date_heure": datetime.now().isoformat(timespec="seconds"),
            "id_modele": ligne["id_modele"],
            "url_source": ligne["url_source"],
            "erreur": message,
        })
        fichier_erreurs.flush()

    try:
        for numero, ligne in enumerate(a_faire, start=1):
            url = ligne["url_source"]
            try:
                html = client.get(url).text
            except ErreurPage as erreur:
                journaliser_erreur(ligne, str(erreur))
                echecs += 1
                print(f"[{numero}/{len(a_faire)}] ERREUR {ligne['id_modele']} : {erreur}")
                continue

            produit = extraire_produit(html)
            if produit is None:
                if ressemble_a_un_blocage(html):
                    raise BlocageServeur(f"page anti-robot reçue pour {url}")
                journaliser_erreur(ligne, "structure de page non reconnue (bloc produit ou h1 absent)")
                echecs += 1
                print(f"[{numero}/{len(a_faire)}] ERREUR {ligne['id_modele']} : structure non reconnue")
                continue

            produit.update({
                "id_modele": ligne["id_modele"],
                "id_variante": ligne["id_variante"],
                "nb_variantes": ligne["nb_variantes"],
                "image_url": ligne["image_url"].split(" | ")[0],
                "url_source": url,
                "date_extraction": date.today().isoformat(),
            })
            ecrivain_produits.writerow(produit)
            fichier_produits.flush()
            reussis += 1
            print(f"[{numero}/{len(a_faire)}] OK {ligne['id_modele']} {produit['nom'][:60]}")
    except BlocageServeur as erreur:
        print(f"ARRÊT : le site bloque les requêtes ({erreur}). Aucune nouvelle tentative.")
        sys.exit(2)
    except KeyboardInterrupt:
        print("Interrompu : relancez le script pour reprendre.")
    finally:
        fichier_produits.close()
        fichier_erreurs.close()
        print(f"Bilan : {reussis} produit(s) écrit(s), {echecs} erreur(s)")


if __name__ == "__main__":
    main()
