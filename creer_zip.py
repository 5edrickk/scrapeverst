"""Construit remise.zip (livrables du Projet 2) et vérifie qu'aucun mot de passe n'y figure.

Exclus : .env, .venv, __pycache__, .git, data/raw/erreurs.csv, data/raw/crawl_etat.json, .gitkeep.
Code de sortie 1 (et ZIP supprimé) si un mot de passe est trouvé.
AVERTISSEMENT (sans bloquer) si une image référencée dans rapport.md ou README.md est absente.

Exemple :
    python creer_zip.py
"""

import os
import re
import sys
import zipfile
from pathlib import Path

RACINE = Path(__file__).resolve().parent
ZIP = RACINE / "remise.zip"

FICHIERS = [
    "rapport.md", "README.md", "requirements.txt", ".env.example",
    "data/urls_echantillon.csv", "data/donnees.json", "data/rapport_nettoyage.txt",
]
GLOBS = ["data/raw/*.csv"]
DOSSIERS = ["scraper", "nettoyage", "couchdb", "images"]
EXCLUS_NOMS = {".env", "erreurs.csv", "crawl_etat.json", ".gitkeep"}
DOCUMENTS_AVEC_IMAGES = ["rapport.md", "README.md"]
MOTIF_IMAGE = re.compile(r"!\[[^\]]*\]\(([^)\s]+)\)")
EXCLUS_DOSSIERS = {".venv", "__pycache__", ".git"}

MOTIFS_SECRETS = [
    re.compile(r"User123"),
    re.compile(r"COUCHDB_PASSWORD=[^\s\"'`]+"),
]


def lister_fichiers():
    chemins = [RACINE / f for f in FICHIERS]
    for motif in GLOBS:
        chemins += sorted(RACINE.glob(motif))
    for dossier in DOSSIERS:
        for parent, sous_dossiers, noms in os.walk(RACINE / dossier):
            sous_dossiers[:] = sorted(d for d in sous_dossiers if d not in EXCLUS_DOSSIERS)
            chemins += [Path(parent) / nom for nom in sorted(noms)]
    retenus = []
    for chemin in chemins:
        if chemin.name in EXCLUS_NOMS or EXCLUS_DOSSIERS & set(chemin.relative_to(RACINE).parts):
            continue
        if not chemin.is_file():
            sys.exit(f"Fichier manquant : {chemin.relative_to(RACINE)}")
        retenus.append(chemin)
    return retenus


def images_manquantes():
    """Images locales référencées par ![...](chemin) dans les documents, mais absentes du disque."""
    manquantes = []
    for document in DOCUMENTS_AVEC_IMAGES:
        texte = (RACINE / document).read_text(encoding="utf-8")
        for chemin in MOTIF_IMAGE.findall(texte):
            if "://" not in chemin and not (RACINE / chemin).is_file():
                manquantes.append(f"{document} -> {chemin}")
    return manquantes


def motifs_secrets():
    """Motifs fixes + le mot de passe réel du .env local (jamais affiché)."""
    motifs = list(MOTIFS_SECRETS)
    env = RACINE / ".env"
    if env.exists():
        for ligne in env.read_text(encoding="utf-8").splitlines():
            if ligne.startswith("COUCHDB_PASSWORD="):
                valeur = ligne.split("=", 1)[1].strip()
                if valeur:
                    motifs.append(re.compile(re.escape(valeur)))
    return motifs


def chercher_secrets(zip_path):
    motifs = motifs_secrets()
    trouves = []
    with zipfile.ZipFile(zip_path) as archive:
        for nom in archive.namelist():
            texte = archive.read(nom).decode("utf-8", errors="ignore")
            for numero, ligne in enumerate(texte.splitlines(), 1):
                if any(m.search(ligne) for m in motifs):
                    trouves.append(f"{nom}:{numero}")
    return trouves


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    fichiers = lister_fichiers()
    with zipfile.ZipFile(ZIP, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for chemin in fichiers:
            archive.write(chemin, chemin.relative_to(RACINE).as_posix())

    with zipfile.ZipFile(ZIP) as archive:
        infos = archive.infolist()
    print(f"{ZIP.name} : {len(infos)} fichiers, {ZIP.stat().st_size / 1_000_000:.2f} Mo")
    for info in infos:
        print(f"  {info.file_size:>10}  {info.filename}")

    trouves = chercher_secrets(ZIP)
    if trouves:
        ZIP.unlink()
        print("\nÉCHEC : mot de passe possible trouvé (ligne non affichée) dans :")
        for endroit in trouves:
            print(f"  {endroit}")
        print("remise.zip supprimé.")
        sys.exit(1)
    print("\nOK : aucun mot de passe trouvé (« User123 », « COUCHDB_PASSWORD=<valeur> », mot de passe du .env).")

    manquantes = images_manquantes()
    if manquantes:
        print("\nAVERTISSEMENT : images référencées mais absentes (le ZIP est quand même créé) :")
        for endroit in manquantes:
            print(f"  {endroit}")


if __name__ == "__main__":
    main()
