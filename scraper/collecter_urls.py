"""Étape A : collecte des URLs de produits (/fr/) depuis les sitemaps Decathlon.

Produit data/urls_echantillon.csv : un échantillon aléatoire reproductible de modèles.
"""

import csv
import random
import re
import sys

from bs4 import BeautifulSoup

from commun import DOSSIER_DATA, BlocageServeur, ClientPoli, ErreurPage

INDEX_SITEMAPS = "https://www.decathlon.ca/decathlon-products-index.xml"
TAILLE_ECHANTILLON = 3500
GRAINE = 42
FICHIER_SORTIE = DOSSIER_DATA / "urls_echantillon.csv"
COLONNES = ["id_modele", "id_variante", "nb_variantes", "url_source", "image_url"]

# .../fr/p/<slug>/<id_modele>/<codes couleur/taille éventuels>m<chiffres>
MOTIF_URL_PRODUIT = re.compile(r"/fr/p/[^/]+/(X?\d+)/[a-z0-9]*?(m\d+)$")


def lister_sitemaps(client):
    reponse = client.get(INDEX_SITEMAPS)
    soupe = BeautifulSoup(reponse.content, "xml")
    return [loc.get_text(strip=True) for loc in soupe.select("sitemap > loc")]


def lire_entrees(client, url_sitemap):
    """Renvoie (url, id_modele, id_variante, images) pour chaque produit /fr/p/ du sitemap."""
    reponse = client.get(url_sitemap)
    soupe = BeautifulSoup(reponse.content, "xml")
    entrees = []
    ignorees = 0
    for bloc in soupe.find_all("url"):
        loc = bloc.find("loc", recursive=False)
        url = loc.get_text(strip=True) if loc else ""
        if "/fr/p/" not in url:
            continue
        correspondance = MOTIF_URL_PRODUIT.search(url)
        if not correspondance:
            ignorees += 1
            continue
        images = [img.get_text(strip=True) for img in bloc.find_all("image:loc")]
        entrees.append((url, correspondance.group(1), correspondance.group(2), images))
    if ignorees:
        print(f"  {ignorees} URL /fr/p/ ignorée(s) (format non reconnu)")
    return entrees


def main():
    client = ClientPoli()
    try:
        sitemaps = lister_sitemaps(client)
        print(f"Index : {len(sitemaps)} fichier(s) sitemap")
        modeles = {}  # id_modele -> infos de la première URL rencontrée
        for url_sitemap in sitemaps:
            print(f"Lecture de {url_sitemap}")
            entrees = lire_entrees(client, url_sitemap)
            print(f"  {len(entrees)} URL /fr/p/ retenues")
            for url, id_modele, id_variante, images in entrees:
                if id_modele in modeles:
                    modeles[id_modele]["nb_variantes"] += 1
                else:
                    modeles[id_modele] = {
                        "id_modele": id_modele,
                        "id_variante": id_variante,
                        "nb_variantes": 1,
                        "url_source": url,
                        "image_url": " | ".join(images),
                    }
    except BlocageServeur as erreur:
        sys.exit(f"ARRÊT : le site bloque les requêtes ({erreur}).")
    except ErreurPage as erreur:
        sys.exit(f"ARRÊT : sitemap inaccessible ({erreur}).")

    print(f"Modèles distincts au total : {len(modeles)}")

    random.seed(GRAINE)
    taille = min(TAILLE_ECHANTILLON, len(modeles))
    echantillon = random.sample(list(modeles.values()), taille)

    with open(FICHIER_SORTIE, "w", encoding="utf-8", newline="") as fichier:
        ecrivain = csv.DictWriter(fichier, fieldnames=COLONNES)
        ecrivain.writeheader()
        ecrivain.writerows(echantillon)
    print(f"Échantillon de {taille} modèles écrit dans {FICHIER_SORTIE}")


if __name__ == "__main__":
    main()
