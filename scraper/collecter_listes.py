"""Collecte des tuiles produits sur les pages de catégories de https://www.decathlon.ca/fr.

Une ligne par tuile dans data/raw/listes_raw.csv (valeurs brutes). Le parcours est
repris depuis data/raw/crawl_etat.json et chaque requête est notée dans
data/raw/crawl_journal.csv. Arrêt immédiat (code 2) sur un HTTP 403 ou 429.

Exemples :
    python scraper/collecter_listes.py --html-test page.html --url-page <url de la page>
    python scraper/collecter_listes.py --une-page <url> --sauver page.html
    python scraper/collecter_listes.py
"""

import argparse
import csv
import json
import re
import sys
from collections import deque
from datetime import date, datetime
from urllib.parse import parse_qsl, urldefrag, urljoin, urlsplit

from bs4 import BeautifulSoup

from commun import DOSSIER_RAW, BlocageServeur, ClientPoli, ErreurPage

DELAI_SECONDES = 5
MAX_MODELES = 3000
MAX_REQUETES = 400
TAILLE_PAGE = "40"

SITE = "https://www.decathlon.ca"
INDEX_SITEMAPS = f"{SITE}/sitemap-index.xml"
POINTS_DE_DEPART = [
    f"{SITE}/fr/sports",
    f"{SITE}/fr/femmes",
    f"{SITE}/fr/hommes",
    f"{SITE}/fr/enfants",
    f"{SITE}/fr/equipements-loisirs",
    f"{SITE}/fr/nutrition-sante",
]
# Dans le parcours en largeur, on ne suit que les liens sous ces rubriques de catégories
# (pas le pied de page : magasins, aide, cartes-cadeaux, etc.).
PREFIXES_CATEGORIES = tuple(urlsplit(url).path for url in POINTS_DE_DEPART)

FICHIER_LISTES = DOSSIER_RAW / "listes_raw.csv"
FICHIER_ETAT = DOSSIER_RAW / "crawl_etat.json"
FICHIER_JOURNAL = DOSSIER_RAW / "crawl_journal.csv"

COLONNES = [
    "url_page_liste", "categorie_page", "position_dans_page", "nom_complet_brut",
    "marque_brut", "prix_actuel_brut", "ancien_prix_brut", "rabais_brut", "note_brut",
    "nb_avis_brut", "nb_couleurs_brut", "etiquette_brut", "url_source", "id_modele",
    "id_variante", "image_url", "date_extraction",
]
COLONNES_JOURNAL = ["url", "code_http", "nb_tuiles", "date", "retry_after"]

MORCEAUX_INTERDITS = ("/p/", "/api/", "/checkout", "/account", "/login", "/search", "/f-")
PARAMETRES_INTERDITS = re.compile(
    r"(?:^|[?&])(?:sort|direction|notes|Ndrc|offer|No|Nrpp|Ns)=", re.IGNORECASE
)

MOTIF_URL_PRODUIT = re.compile(r"/fr/p/(?:[^/?#]+/)+?(X?\d+)/[a-z0-9]*?(m\d+)(?:[?#]|$)")
MOTIF_RABAIS = re.compile(r"\d+\s*%.*réduction|^-\s*\d+\s*%$", re.IGNORECASE)
MOTIF_NB_AVIS = re.compile(r"^\(\s*\d[\d\s  ]*\)$")
MOTIF_NB_COULEURS = re.compile(r"^\d+\s+couleurs?$", re.IGNORECASE)
MOTIF_NOTE = re.compile(r"^\d(?:[.,]\d+)?$")
MOTS_ANCIEN_PRIX = ("barred", "previous", "old", "strike", "crossed", "initial")
TEXTES_ANCIEN_PRIX = ("précédent", "ancien", "initial", "avant", "barré")


# --- Règles d'URL -----------------------------------------------------------

def url_liste_autorisee(url):
    """URL de page de liste visitable : /fr/ sans paramètre, sauf ?from=<n>&size=40."""
    morceaux = urlsplit(url)
    if morceaux.scheme != "https" or morceaux.netloc != "www.decathlon.ca" or morceaux.fragment:
        return False
    if not (morceaux.path == "/fr" or morceaux.path.startswith("/fr/")):
        return False
    if any(interdit in morceaux.path for interdit in MORCEAUX_INTERDITS):
        return False
    if not morceaux.query:
        return True
    if PARAMETRES_INTERDITS.search("?" + morceaux.query):
        return False
    parametres = parse_qsl(morceaux.query, keep_blank_values=True)
    noms = [nom for nom, _ in parametres]
    valeurs = dict(parametres)
    return (
        sorted(noms) == ["from", "size"]
        and valeurs["from"].isdigit()
        and valeurs["size"] == TAILLE_PAGE
    )


def url_sitemap_autorisee(url):
    morceaux = urlsplit(url)
    return (
        morceaux.scheme == "https"
        and morceaux.netloc == "www.decathlon.ca"
        and morceaux.path.endswith(".xml")
        and not morceaux.query
        and not morceaux.fragment
    )


def url_autorisee(url):
    return url_liste_autorisee(url) or url_sitemap_autorisee(url)


# --- Analyse d'une page de liste ---------------------------------------------

def texte(element):
    """Texte visible d'un élément (sans le texte pour lecteurs d'écran), espaces conservés."""
    if element is None:
        return ""
    copie = BeautifulSoup(str(element), "lxml")
    for cache in copie.select(".sr-only"):
        cache.decompose()
    return " ".join(morceau.strip() for morceau in copie.find_all(string=True) if morceau.strip())


def textes_feuilles(tuile):
    """Petits morceaux de texte visibles de la tuile, dans l'ordre."""
    resultats = []
    for morceau in tuile.find_all(string=True):
        if morceau.parent.name in ("script", "style"):
            continue
        if morceau.find_parent(class_="sr-only"):
            continue
        valeur = morceau.strip()
        if valeur:
            resultats.append(valeur)
    return resultats


def lien_produit(tuile):
    for lien in tuile.find_all("a", href=True):
        if MOTIF_URL_PRODUIT.search(lien["href"]):
            return lien
    return None


def trouver_tuiles(soupe):
    """Plus grand ancêtre de chaque lien produit qui ne contient qu'un seul produit."""
    tuiles = []
    vues = set()
    for lien in soupe.find_all("a", href=MOTIF_URL_PRODUIT):
        if lien.find_parent(["header", "footer", "nav"]):
            continue
        tuile = lien
        for parent in lien.parents:
            if parent.name in ("ul", "ol", "body", "main", "[document]"):
                break
            hrefs = {
                MOTIF_URL_PRODUIT.search(a["href"]).group(0)
                for a in parent.find_all("a", href=MOTIF_URL_PRODUIT)
            }
            if len(hrefs) > 1:
                break
            tuile = parent
        if id(tuile) not in vues and tuile.select_one(".vp-price-amount, [class*=price]"):
            vues.add(id(tuile))
            tuiles.append(tuile)
    return tuiles


def extraire_prix(tuile):
    actuel = ancien = ""
    for montant in tuile.select(".vp-price-amount, .vp-price-barred-amount"):
        classes = " ".join(montant.get("class") or []).lower()
        etiquette = (montant.select_one(".sr-only").get_text(" ", strip=True).lower()
                     if montant.select_one(".sr-only") else "")
        est_ancien = (
            any(mot in classes for mot in MOTS_ANCIEN_PRIX)
            or any(mot in etiquette for mot in TEXTES_ANCIEN_PRIX)
            or montant.find_parent(["s", "del"]) is not None
        )
        if est_ancien and not ancien:
            ancien = texte(montant)
        elif not est_ancien and not actuel:
            actuel = texte(montant)
    return actuel, ancien


def extraire_tuile(tuile, url_page):
    lien = lien_produit(tuile)
    url_source = urljoin(url_page, lien["href"]) if lien else ""
    correspondance = MOTIF_URL_PRODUIT.search(url_source)

    titre = tuile.select_one("h2, h3, h4, [class*=title]")
    nom = texte(titre) if titre else texte(lien)

    image = tuile.find("img")
    marque = ""
    image_url = ""
    if image is not None:
        marque = re.sub(r"\bpicture\b", "", image.get("alt", ""), flags=re.IGNORECASE).strip()
        image_url = image.get("src") or image.get("data-src") or ""
        if not image_url and image.get("srcset"):
            image_url = image["srcset"].split(",")[0].split()[0]
        image_url = urljoin(url_page, image_url) if image_url else ""

    prix_actuel, ancien_prix = extraire_prix(tuile)

    rabais = note = nb_avis = nb_couleurs = ""
    for valeur in textes_feuilles(tuile):
        if not rabais and MOTIF_RABAIS.search(valeur):
            rabais = valeur
        elif not nb_avis and MOTIF_NB_AVIS.match(valeur):
            nb_avis = valeur
        elif not nb_couleurs and MOTIF_NB_COULEURS.match(valeur):
            nb_couleurs = valeur
        elif not note and MOTIF_NOTE.match(valeur):
            note = valeur

    etiquettes = []
    # Le même autocollant est répété pour chaque taille d'écran : on garde chaque texte une fois.
    for pastille in tuile.select(".vp-sticker"):
        valeur = texte(pastille)
        if valeur and not MOTIF_RABAIS.search(valeur) and valeur not in etiquettes:
            etiquettes.append(valeur)

    return {
        "nom_complet_brut": nom,
        "marque_brut": marque,
        "prix_actuel_brut": prix_actuel,
        "ancien_prix_brut": ancien_prix,
        "rabais_brut": rabais,
        "note_brut": note,
        "nb_avis_brut": nb_avis,
        "nb_couleurs_brut": nb_couleurs,
        "etiquette_brut": " | ".join(etiquettes),
        "url_source": url_source,
        "id_modele": correspondance.group(1) if correspondance else "",
        "id_variante": correspondance.group(2) if correspondance else "",
        "image_url": image_url,
    }


def categorie_de_la_page(soupe):
    titre = soupe.find("h1")
    if titre is not None and texte(titre):
        return texte(titre)
    return " > ".join(texte(e) for e in soupe.select("nav.breadcrumbs span.vp-body-s"))


def lien_page_suivante(soupe, url_page):
    """Lien « page suivante » fourni par la page (jamais fabriqué)."""
    candidats = soupe.select("a[rel~=next]")
    for lien in soupe.find_all("a", href=True):
        libelle = f"{lien.get('aria-label', '')} {lien.get('title', '')} {lien.get_text(' ', strip=True)}"
        if "suivant" in libelle.lower():
            candidats.append(lien)
    for lien in candidats:
        if lien.get("href"):
            url = urldefrag(urljoin(url_page, lien["href"])).url
            if "?" in url and url_liste_autorisee(url) and url != url_page:
                return url
    return ""


def liens_categories(soupe, url_page):
    liens = []
    for lien in soupe.find_all("a", href=True):
        url = urldefrag(urljoin(url_page, lien["href"])).url.rstrip("/")
        chemin = urlsplit(url).path
        if (
            "?" not in url
            and url_liste_autorisee(url)
            and chemin.startswith(PREFIXES_CATEGORIES)
            and url not in liens
        ):
            liens.append(url)
    return liens


def analyser_page(html, url_page):
    """Renvoie (lignes CSV, lien page suivante, liens de sous-catégories)."""
    soupe = BeautifulSoup(html, "lxml")
    categorie = categorie_de_la_page(soupe)
    aujourd_hui = date.today().isoformat()
    lignes = []
    for position, tuile in enumerate(trouver_tuiles(soupe), start=1):
        ligne = {"url_page_liste": url_page, "categorie_page": categorie, "position_dans_page": position}
        ligne.update(extraire_tuile(tuile, url_page))
        ligne["date_extraction"] = aujourd_hui
        lignes.append(ligne)
    return lignes, lien_page_suivante(soupe, url_page), liens_categories(soupe, url_page)


def afficher_analyse(html, url_page, nb_lignes=5):
    lignes, suivante, categories = analyser_page(html, url_page)
    for ligne in lignes[:nb_lignes]:
        print(f"===== tuile {ligne['position_dans_page']}")
        for colonne in COLONNES:
            print(f"  {colonne:20} {ligne[colonne]!r}")
    print(f"\nTuiles : {len(lignes)}")
    print(f"Modèles distincts : {len({l['id_modele'] for l in lignes if l['id_modele']})}")
    print(f"Page suivante : {suivante or '(aucune)'}")
    print(f"Liens de catégories trouvés : {len(categories)}")
    for url in categories[:15]:
        print(f"  {url}")
    if len(categories) > 15:
        print(f"  … et {len(categories) - 15} autres")
    print("\nChamps vides :")
    for colonne in COLONNES:
        vides = sum(1 for ligne in lignes if ligne[colonne] in ("", None))
        print(f"  {colonne:20} {vides}/{len(lignes)}")


# --- Découverte des catégories via les sitemaps -----------------------------

def categories_depuis_sitemaps(client, journal):
    """URLs de catégories /fr/ trouvées dans un sitemap de catégories, ou liste vide."""
    reponse = client.get(INDEX_SITEMAPS)
    journal(INDEX_SITEMAPS, reponse.status_code, "")
    soupe = BeautifulSoup(reponse.content, "xml")
    sitemaps = [loc.get_text(strip=True) for loc in soupe.select("sitemap > loc")]
    print(f"sitemap-index.xml : {len(sitemaps)} sitemap(s)")
    for url in sitemaps:
        print(f"  {url}")
    sitemaps_categories = [url for url in sitemaps if re.search(r"categor|plp|taxonom", url, re.I)]
    if not sitemaps_categories:
        return []

    urls = []
    for url_sitemap in sitemaps_categories:
        if not url_sitemap_autorisee(url_sitemap):
            continue
        reponse = client.get(url_sitemap)
        journal(url_sitemap, reponse.status_code, "")
        for loc in BeautifulSoup(reponse.content, "xml").select("url > loc"):
            url = loc.get_text(strip=True).rstrip("/")
            if "?" not in url and url_liste_autorisee(url) and url not in urls:
                urls.append(url)
    return urls


# --- Parcours ----------------------------------------------------------------

def charger_etat():
    if FICHIER_ETAT.exists():
        with open(FICHIER_ETAT, encoding="utf-8") as fichier:
            return json.load(fichier)
    etat = {"mode": None, "visitees": [], "file": [], "requetes_total": 0}
    # Pages déjà présentes dans le CSV : leurs produits sont collectés, inutile de les refaire.
    if FICHIER_LISTES.exists():
        with open(FICHIER_LISTES, encoding="utf-8", newline="") as fichier:
            etat["visitees"] = sorted({ligne["url_page_liste"] for ligne in csv.DictReader(fichier)})
    return etat


def sauver_etat(etat):
    temporaire = FICHIER_ETAT.with_suffix(".tmp")
    with open(temporaire, "w", encoding="utf-8") as fichier:
        json.dump(etat, fichier, ensure_ascii=False, indent=1)
    temporaire.replace(FICHIER_ETAT)


def modeles_deja_collectes():
    if not FICHIER_LISTES.exists():
        return set()
    with open(FICHIER_LISTES, encoding="utf-8", newline="") as fichier:
        return {ligne["id_modele"] for ligne in csv.DictReader(fichier) if ligne["id_modele"]}


def ouvrir_en_ajout(chemin, colonnes):
    nouveau = not chemin.exists() or chemin.stat().st_size == 0
    fichier = open(chemin, "a", encoding="utf-8", newline="")
    ecrivain = csv.DictWriter(fichier, fieldnames=colonnes)
    if nouveau:
        ecrivain.writeheader()
        fichier.flush()
    return fichier, ecrivain


def parcourir(args):
    etat = charger_etat()
    visitees = set(etat["visitees"])
    file = deque(url for url in etat["file"] if url not in visitees)
    connues = visitees | set(file)
    modeles = modeles_deja_collectes()
    client = ClientPoli(delai=args.delai, url_autorisee=url_autorisee)

    fichier_listes, ecrivain_listes = ouvrir_en_ajout(FICHIER_LISTES, COLONNES)
    fichier_journal, ecrivain_journal = ouvrir_en_ajout(FICHIER_JOURNAL, COLONNES_JOURNAL)
    requetes = 0

    def journal(url, code, nb_tuiles, retry_after=""):
        nonlocal requetes
        requetes += 1
        etat["requetes_total"] += 1
        ecrivain_journal.writerow({
            "url": url, "code_http": code, "nb_tuiles": nb_tuiles,
            "date": datetime.now().isoformat(timespec="seconds"), "retry_after": retry_after or "",
        })
        fichier_journal.flush()

    def ajouter(url):
        if url not in connues:
            connues.add(url)
            file.append(url)

    def enregistrer():
        etat["visitees"] = sorted(visitees)
        etat["file"] = list(file)
        sauver_etat(etat)

    try:
        if etat["mode"] is None:
            seeds = categories_depuis_sitemaps(client, journal)
            etat["mode"] = "sitemap" if seeds else "parcours_largeur"
            print(f"Mode : {etat['mode']}")
            for url in seeds or POINTS_DE_DEPART:
                ajouter(url)
            enregistrer()

        print(f"Reprise : {len(visitees)} page(s) déjà visitée(s), {len(file)} en file, "
              f"{len(modeles)} modèle(s) déjà collecté(s)")

        while file:
            if len(modeles) >= args.max_modeles:
                print(f"Arrêt : {len(modeles)} modèles distincts atteints.")
                break
            if requetes >= args.max_requetes:
                print(f"Arrêt : {requetes} requêtes faites dans cette exécution.")
                break

            url = file.popleft()
            visitees.add(url)
            try:
                html = client.get(url).text
            except ErreurPage as erreur:
                journal(url, erreur.code or "erreur", "")
                print(f"[{requetes}] {erreur.code or 'ERREUR'} {url} : {erreur}")
                cible = urljoin(url, erreur.location).rstrip("/") if erreur.location else ""
                if cible and url_liste_autorisee(cible) and "?" not in cible:
                    ajouter(cible)
                enregistrer()
                continue

            lignes, suivante, categories = analyser_page(html, url)
            ecrivain_listes.writerows(lignes)
            fichier_listes.flush()
            modeles.update(ligne["id_modele"] for ligne in lignes if ligne["id_modele"])
            journal(url, 200, len(lignes))
            print(f"[{requetes}] 200, {len(lignes)} tuiles, {len(modeles)} modèles distincts cumulés — {url}")

            if suivante:
                ajouter(suivante)
            if etat["mode"] == "parcours_largeur":
                for lien in categories:
                    ajouter(lien)
            enregistrer()
        else:
            print("Arrêt : la file d'attente est vide.")
    except BlocageServeur as erreur:
        url_bloquee = client.derniere_url
        journal(url_bloquee, erreur.code, "", erreur.retry_after)
        if url_bloquee in visitees:
            # La page bloquée n'a pas été lue : on la remet en tête de file pour la reprise.
            visitees.discard(url_bloquee)
            file.appendleft(url_bloquee)
        enregistrer()
        print(f"ARRÊT : HTTP {erreur.code} (Retry-After : {erreur.retry_after or 'absent'}). "
              "Aucune nouvelle tentative.")
        sys.exit(2)
    except KeyboardInterrupt:
        enregistrer()
        print("Interrompu : relancez le script pour reprendre.")
    finally:
        fichier_listes.close()
        fichier_journal.close()
        print(f"Bilan : {requetes} requête(s), {len(modeles)} modèles distincts, "
              f"{len(file)} URL(s) en file")


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--html-test", help="analyser un fichier HTML local, sans requête réseau")
    parser.add_argument("--url-page", default=f"{SITE}/fr/", help="URL d'origine du fichier --html-test")
    parser.add_argument("--une-page", help="télécharger et analyser UNE page de liste, sans écrire de CSV")
    parser.add_argument("--sauver", help="avec --une-page : enregistrer le HTML reçu dans ce fichier")
    parser.add_argument("--delai", type=float, default=DELAI_SECONDES, help="secondes entre deux requêtes")
    parser.add_argument("--max-modeles", type=int, default=MAX_MODELES)
    parser.add_argument("--max-requetes", type=int, default=MAX_REQUETES, help="par exécution")
    args = parser.parse_args()

    if args.html_test:
        with open(args.html_test, encoding="utf-8") as fichier:
            afficher_analyse(fichier.read(), args.url_page)
    elif args.une_page:
        if not url_liste_autorisee(args.une_page):
            sys.exit(f"URL refusée par les règles de politesse : {args.une_page}")
        client = ClientPoli(delai=args.delai, url_autorisee=url_liste_autorisee)
        try:
            reponse = client.get(args.une_page)
        except BlocageServeur as erreur:
            print(f"ARRÊT : HTTP {erreur.code} (Retry-After : {erreur.retry_after or 'absent'}).")
            sys.exit(2)
        except ErreurPage as erreur:
            sys.exit(f"Erreur : {erreur}")
        print(f"HTTP {reponse.status_code}, {len(reponse.content)} octets")
        if args.sauver:
            with open(args.sauver, "w", encoding="utf-8") as fichier:
                fichier.write(reponse.text)
            print(f"HTML enregistré dans {args.sauver}")
        afficher_analyse(reponse.text, args.une_page)
    else:
        parcourir(args)


if __name__ == "__main__":
    main()
