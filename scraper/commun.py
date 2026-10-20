"""Outils partagés par les scripts du scraper : configuration et requêtes polies."""

import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

RACINE = Path(__file__).resolve().parent.parent
DOSSIER_DATA = RACINE / "data"
DOSSIER_RAW = DOSSIER_DATA / "raw"

DELAI_SECONDES = 2.5
TIMEOUT_SECONDES = 30
CODES_BLOCAGE = {403, 429}


class BlocageServeur(Exception):
    """Le site refuse nos requêtes (403, 429 ou page anti-robot) : il faut arrêter."""


class ErreurPage(Exception):
    """Une page n'a pas pu être récupérée ; on la journalise et on continue."""


def construire_user_agent():
    load_dotenv(RACINE / ".env")
    contact = os.environ.get("SCRAPER_CONTACT", "").strip()
    if not contact:
        sys.exit(
            "Erreur : la variable SCRAPER_CONTACT est absente ou vide. "
            "Ajoutez SCRAPER_CONTACT=<votre courriel> dans le fichier .env."
        )
    return f"Projet scolaire Cegep de Sherbrooke - contact: {contact}"


class ClientPoli:
    """Client HTTP : une requête à la fois, délai minimal entre deux requêtes."""

    def __init__(self, delai=DELAI_SECONDES):
        self.delai = delai
        self.session = requests.Session()
        self.session.headers["User-Agent"] = construire_user_agent()
        self._derniere_requete = 0.0

    def get(self, url):
        if "?" in url or "/api/" in url:
            raise ValueError(f"URL refusée (paramètres ou /api/) : {url}")

        attente = self.delai - (time.monotonic() - self._derniere_requete)
        if attente > 0:
            time.sleep(attente)

        try:
            # Pas de redirection automatique : chaque requête envoyée est contrôlée et espacée.
            reponse = self.session.get(url, timeout=TIMEOUT_SECONDES, allow_redirects=False)
        except requests.exceptions.Timeout:
            raise ErreurPage(f"délai dépassé ({TIMEOUT_SECONDES} s)")
        except requests.exceptions.RequestException as erreur:
            raise ErreurPage(f"erreur réseau : {erreur}")
        finally:
            self._derniere_requete = time.monotonic()

        if reponse.status_code in CODES_BLOCAGE:
            raise BlocageServeur(f"HTTP {reponse.status_code} sur {url}")
        if 300 <= reponse.status_code < 400:
            raise ErreurPage(
                f"redirection HTTP {reponse.status_code} vers {reponse.headers.get('Location', '?')}"
            )
        if reponse.status_code != 200:
            raise ErreurPage(f"HTTP {reponse.status_code}")
        return reponse
