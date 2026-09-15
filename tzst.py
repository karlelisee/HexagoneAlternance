"""
Scraper multi-sites — appartements à Versailles et alentours
Sites : PAP.fr + Logic-Immo
Nécessite : pip install requests beautifulsoup4
"""

import requests
from bs4 import BeautifulSoup
import time
import json
import csv
import re
from dataclasses import dataclass, asdict

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept-Language": "fr-FR,fr;q=0.9",
}

# --- PAP : g-codes vérifiés / à compléter (voir méthode ci-dessus) ---
VILLES_PAP = {
    "Versailles": "https://www.pap.fr/annonce/locations-appartement-versailles-78000-g39053",
    "Fresnes": "https://www.pap.fr/annonce/locations-appartement-fresnes-94260-g43355",
    "Rungis": "https://www.pap.fr/annonce/locations-appartement-rungis-94150-g43395",
    "Chevilly-Larue": "https://www.pap.fr/annonce/locations-appartement-chevilly-larue-94550-g43296",
    "L'Hay-les-Roses": "https://www.pap.fr/annonce/locations-appartement-l-hay-les-roses-94240-g43317",
    "Wissous": "https://www.pap.fr/annonce/locations-appartement-wissous-91320-g43700",
    "Antony": "https://www.pap.fr/annonce/locations-appartement-antony-92160-g43181",
    "Viroflay": "https://www.pap.fr/annonce/locations-appartement-viroflay-78220-g39133",
    "Saint-Cyr-l'École": "https://www.pap.fr/annonce/locations-appartement-saint-cyr-l-ecole-78210-g39131",
    "Le Chesnay-Rocquencourt": "https://www.pap.fr/annonce/locations-appartement-le-chesnay-rocquencourt-78150-g39071",
}

# --- Logic-Immo : slugs ville (nom-codepostal) ---
VILLES_LOGICIMMO = {
    "Versailles": "https://www.logic-immo.com/location-immobilier-versailles-78000",
    "Fresnes": "https://www.logic-immo.com/location-immobilier-fresnes-94260",
}


@dataclass
class Annonce:
    source: str
    ville: str
    titre: str
    prix: str
    pieces: str
    chambres: str
    surface: str
    lien: str


def get_soup(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


# ---------- PAP ----------
def parse_liste_pap(soup: BeautifulSoup, ville: str) -> list[Annonce]:
    resultats = []
    items = soup.select("a.item-title, div.item")
    if not items:
        items = soup.select("a[href*='/annonces/']")

    liens_vus = set()
    for item in items:
        lien = item.get("href") if item.name == "a" else None
        if not lien:
            a_tag = item.find("a", href=True)
            lien = a_tag["href"] if a_tag else None
        if not lien or lien in liens_vus or "/annonces/" not in lien:
            continue
        liens_vus.add(lien)
        if not lien.startswith("http"):
            lien = "https://www.pap.fr" + lien

        bloc = item if item.name != "a" else item.find_parent()
        texte_bloc = bloc.get_text(separator=" | ", strip=True) if bloc else ""
        titre = item.get_text(strip=True) if item.name == "a" else ""

        prix_m = re.search(r"([\d.\s]{3,}\s?€)", texte_bloc)
        pieces_m = re.search(r"(\d+)\s*pi[eè]ces?", texte_bloc)
        chambres_m = re.search(r"(\d+)\s*chambres?", texte_bloc)
        surface_m = re.search(r"([\d,]+)\s*m[²2]", texte_bloc)

        resultats.append(Annonce(
            source="PAP",
            ville=ville,
            titre=titre or texte_bloc[:80],
            prix=prix_m.group(1) if prix_m else "",
            pieces=pieces_m.group(1) if pieces_m else "",
            chambres=chambres_m.group(1) if chambres_m else "",
            surface=surface_m.group(1) if surface_m else "",
            lien=lien,
        ))
    return resultats


def scrape_pap(ville: str, base_url: str, max_pages: int = 3) -> list[Annonce]:
    toutes = []
    for page in range(1, max_pages + 1):
        url = base_url if page == 1 else f"{base_url}?page={page}"
        print(f"[PAP][{ville}] Page {page}")
        try:
            soup = get_soup(url)
        except requests.RequestException as e:
            print(f"  Erreur : {e}")
            break
        annonces = parse_liste_pap(soup, ville)
        if not annonces:
            break
        toutes.extend(annonces)
        time.sleep(1.5)
    return toutes


# ---------- Logic-Immo ----------
def parse_liste_logicimmo(soup: BeautifulSoup, ville: str) -> list[Annonce]:
    resultats = []
    cards = soup.select("div.offer-block, article")

    for card in cards:
        a_tag = card.find("a", href=True)
        if not a_tag:
            continue
        lien = a_tag["href"]
        if not lien.startswith("http"):
            lien = "https://www.logic-immo.com" + lien

        texte_bloc = card.get_text(separator=" | ", strip=True)
        prix_m = re.search(r"([\d.\s]{3,}\s?€)", texte_bloc)
        pieces_m = re.search(r"(\d+)\s*pi[eè]ces?", texte_bloc)
        chambres_m = re.search(r"(\d+)\s*chambres?", texte_bloc)
        surface_m = re.search(r"([\d,]+)\s*m[²2]", texte_bloc)

        resultats.append(Annonce(
            source="LogicImmo",
            ville=ville,
            titre=texte_bloc[:80],
            prix=prix_m.group(1) if prix_m else "",
            pieces=pieces_m.group(1) if pieces_m else "",
            chambres=chambres_m.group(1) if chambres_m else "",
            surface=surface_m.group(1) if surface_m else "",
            lien=lien,
        ))
    return resultats


def scrape_logicimmo(ville: str, base_url: str, max_pages: int = 3) -> list[Annonce]:
    toutes = []
    for page in range(1, max_pages + 1):
        url = base_url if page == 1 else f"{base_url}/page-{page}"
        print(f"[LogicImmo][{ville}] Page {page}")
        try:
            soup = get_soup(url)
        except requests.RequestException as e:
            print(f"  Erreur : {e}")
            break
        annonces = parse_liste_logicimmo(soup, ville)
        if not annonces:
            break
        toutes.extend(annonces)
        time.sleep(1.5)
    return toutes


def filtrer_3_chambres(annonces: list[Annonce]) -> list[Annonce]:
    return [a for a in annonces if a.chambres == "3"]


def save_results(annonces: list[Annonce], filename="annonces"):
    with open(f"{filename}.json", "w", encoding="utf-8") as f:
        json.dump([asdict(a) for a in annonces], f, ensure_ascii=False, indent=2)
    if annonces:
        with open(f"{filename}.csv", "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=asdict(annonces[0]).keys())
            writer.writeheader()
            writer.writerows(asdict(a) for a in annonces)
    print(f"{len(annonces)} annonces -> {filename}.json / .csv")


def main():
    toutes = []

    for ville, url in VILLES_PAP.items():
        toutes.extend(scrape_pap(ville, url, max_pages=3))

    for ville, url in VILLES_LOGICIMMO.items():
        toutes.extend(scrape_logicimmo(ville, url, max_pages=3))

    print(f"\nTotal brut : {len(toutes)} annonces")
    annonces_3ch = filtrer_3_chambres(toutes)
    print(f"Total 3 chambres : {len(annonces_3ch)} annonces")

    save_results(toutes, "annonces_toutes")
    save_results(annonces_3ch, "annonces_3chambres")


if __name__ == "__main__":
    main()