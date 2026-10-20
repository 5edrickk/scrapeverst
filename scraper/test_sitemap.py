"""Test d'accès au sitemap produits de Decathlon Canada."""

import os
import sys

import requests
from dotenv import load_dotenv

SITEMAP_URL = "https://www.decathlon.ca/decathlon-products-index.xml"
TIMEOUT_SECONDES = 20
APERCU_CARACTERES = 1500


def construire_user_agent():
    load_dotenv()
    contact = os.environ.get("SCRAPER_CONTACT", "").strip()
    if not contact:
        sys.exit(
            "Erreur : la variable SCRAPER_CONTACT est absente ou vide. "
            "Ajoutez SCRAPER_CONTACT=<votre courriel> dans le fichier .env."
        )
    return f"Projet scolaire Cegep de Sherbrooke - contact: {contact}"


def main():
    headers = {"User-Agent": construire_user_agent()}
    print(f"GET {SITEMAP_URL}")
    print(f"User-Agent : {headers['User-Agent']}")

    try:
        reponse = requests.get(SITEMAP_URL, headers=headers, timeout=TIMEOUT_SECONDES)
    except requests.exceptions.Timeout:
        sys.exit(f"Erreur : délai dépassé ({TIMEOUT_SECONDES} s) pour {SITEMAP_URL}")
    except requests.exceptions.ConnectionError as erreur:
        sys.exit(f"Erreur de connexion : {erreur}")
    except requests.exceptions.RequestException as erreur:
        sys.exit(f"Erreur réseau : {erreur}")

    print(f"Code HTTP : {reponse.status_code}")
    print(f"Taille    : {len(reponse.content)} octets")
    print(f"--- {APERCU_CARACTERES} premiers caractères ---")
    print(reponse.text[:APERCU_CARACTERES])


if __name__ == "__main__":
    main()
