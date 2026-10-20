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

    def __init__(self, message, code=None, retry_after=None):
        super().__init__(message)
        self.code = code
        self.retry_after = retry_after


class ErreurPage(Exception):
    """Une page n'a pas pu être récupérée ; on la journalise et on continue."""

    def __init__(self, message, code=None, location=None):
        super().__init__(message)
        self.code = code
        self.location = location


def url_produit_autorisee(url):
    return "?" not in url and "/api/" not in url


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

    def __init__(self, delai=DELAI_SECONDES, url_autorisee=url_produit_autorisee):
        self.delai = delai
        self.url_autorisee = url_autorisee
        self.derniere_url = None
        self.session = requests.Session()
        self.session.headers["User-Agent"] = construire_user_agent()
        self._derniere_requete = 0.0

    def get(self, url):
        if not self.url_autorisee(url):
            raise ValueError(f"URL refusée par les règles de politesse : {url}")

        attente = self.delai - (time.monotonic() - self._derniere_requete)
        if attente > 0:
            time.sleep(attente)

        self.derniere_url = url
        try:
            # Pas de redirection automatique : chaque requête envoyée est contrôlée et espacée.
            reponse = self.session.get(url, timeout=TIMEOUT_SECONDES, allow_redirects=False)
        except requests.exceptions.Timeout:
            raise ErreurPage(f"délai dépassé ({TIMEOUT_SECONDES} s)")
        except requests.exceptions.RequestException as erreur:
            raise ErreurPage(f"erreur réseau : {erreur}")
        finally:
            self._derniere_requete = time.monotonic()

        code = reponse.status_code
        if code in CODES_BLOCAGE:
            raise BlocageServeur(
                f"HTTP {code} sur {url}", code=code, retry_after=reponse.headers.get("Retry-After")
            )
        if 300 <= code < 400:
            location = reponse.headers.get("Location")
            raise ErreurPage(f"redirection HTTP {code} vers {location or '?'}", code=code, location=location)
        if code != 200:
            raise ErreurPage(f"HTTP {code}", code=code)
        return reponse
