"""
alternances_app.py — Scraper HelloWork + génération de page HTML combinés
Alternances ET stages — Dev / Data / IA / Cybersécurité
Nécessite : pip install requests beautifulsoup4
"""

import requests
from bs4 import BeautifulSoup
import time
import csv
import re
import json
import os
from datetime import datetime

# ---------- CONFIG ----------
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept-Language": "fr-FR,fr;q=0.9",
}

MOTS_CLES = {
    "développeur": "Développement",
    "data": "Data",
    "intelligence artificielle": "IA",
    "machine learning": "IA",
    "cybersécurité": "Cybersécurité",
    "sécurité informatique": "Cybersécurité",
}

TYPES_CONTRAT = ["Alternance", "Stage"]

MAX_PAGES = 2

CSV_PATH = "alternances_hexagone.csv"
OUTPUT_HTML = "index.html"
FIELDNAMES = ["titre", "entreprise", "logo", "date_publiee", "description", "lien",
              "categorie", "type_contrat", "date_detectee"]

COULEUR_PRIMAIRE = "#223d7d"
COULEUR_ACCENT = "#ffcc38"

DATE_PATTERN = re.compile(
    r"(Aujourd'hui|Hier|Il y a \d+\s?(?:heure|jour|semaine|mois)s?|\d{1,2}/\d{1,2}/\d{2,4})",
    re.IGNORECASE,
)

AUTO_RELOAD_MINUTES = 15
OFFRES_PAR_PAGE = 12


# ---------- SCRAPING ----------
def extraire_entreprise(card, titre: str, texte_bloc: str) -> str:
    a = card.select_one("a[href*='/entreprises/']")
    if a:
        img = a.find("img")
        if img:
            alt = (img.get("alt") or "").strip()
            if alt:
                nom = re.sub(r"\s+recrutement$", "", alt, flags=re.IGNORECASE).strip()
                if nom:
                    return nom
            ttl = (img.get("title") or "").strip()
            if ttl:
                nom = re.sub(r"^recrutement\s+", "", ttl, flags=re.IGNORECASE).strip()
                if nom:
                    return nom
        txt = a.get_text(strip=True)
        if txt and 2 < len(txt) < 60:
            return txt

    for sel in ["[class*='company']", "[class*='employer']", "[data-testid*='company']"]:
        el = card.select_one(sel)
        if el:
            txt = el.get_text(strip=True)
            if txt and txt != titre and 2 < len(txt) < 60:
                return txt

    return "Non précisé"


def extraire_logo(card) -> str:
    a = card.select_one("a[href*='/entreprises/']")
    img = a.find("img") if a else card.select_one("img[src*='/entreprises/'], img[data-src*='/entreprises/']")
    if not img:
        return ""

    src = img.get("src") or img.get("data-src") or img.get("data-lazy") or ""
    if src.startswith("//"):
        src = "https:" + src
    return src if src.startswith("http") else ""  



def extraire_date(texte_bloc: str) -> str:
    match = DATE_PATTERN.search(texte_bloc)
    return match.group(0) if match else "Non précisée"


def scrape_hellowork(mot_cle: str, categorie: str, type_contrat: str, max_pages: int = MAX_PAGES) -> list[dict]:
    resultats = []

    for page in range(max_pages):
        url = (
            "https://www.hellowork.com/fr-fr/emploi/recherche.html"
            f"?k={mot_cle.replace(' ', '+')}"
            "&k_autocomplete="
            "&l="
            "&l_autocomplete="
            "&st=relevance"
            f"&c={type_contrat}"
            "&cod=all"
            "&msa=0"
            "&d=all"
            f"&p={page}"
        )
        print(f"[HelloWork] '{mot_cle}' ({categorie} / {type_contrat}) - page {page}")

        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
        except requests.RequestException as e:
            print(f"  Erreur requête : {e}")
            break

        soup = BeautifulSoup(resp.text, "html.parser")
        cards = soup.select("li[data-id-storage-target='item'], article, div[class*='offer']")

        if not cards:
            break

        avant = len(resultats)

        for card in cards:
            a_tag = card.find("a", href=True)
            if not a_tag:
                continue

            lien = a_tag["href"]
            if not lien.startswith("http"):
                lien = "https://www.hellowork.com" + lien

            titre = a_tag.get_text(strip=True)
            texte_bloc = card.get_text(separator=" | ", strip=True)

            if not titre:
                continue

            entreprise = extraire_entreprise(card, titre, texte_bloc)
            logo = extraire_logo(card)
            date_pub = extraire_date(texte_bloc)

            resultats.append({
                "titre": titre,
                "entreprise": entreprise,
                "logo": logo,
                "date_publiee": date_pub,
                "description": texte_bloc[:600],
                "lien": lien,
                "categorie": categorie,
                "type_contrat": type_contrat,
            })

        print(f"  {len(resultats) - avant} offres extraites")

        if len(resultats) - avant == 0:
            break

        time.sleep(2)

    return resultats


# ---------- FUSION AVEC L'HISTORIQUE ----------
def charger_offres_existantes() -> dict:
    if not os.path.exists(CSV_PATH):
        return {}
    existantes = {}
    try:
        with open(CSV_PATH, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            if not reader.fieldnames or "lien" not in reader.fieldnames:
                print("CSV au format obsolète ou illisible — repart de zéro.")
                return {}
            for row in reader:
                lien = row.get("lien")
                if lien:
                    existantes[lien] = row
    except Exception as e:
        print(f"Erreur de lecture du CSV ({e}) — repart de zéro.")
        return {}
    return existantes


def sauvegarder_offres(offres: dict):
    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        for row in sorted(offres.values(), key=lambda r: r["date_detectee"], reverse=True):
            writer.writerow(row)


def scraper_et_fusionner() -> dict:
    horodatage = datetime.now().strftime("%Y-%m-%d %H:%M")
    existantes = charger_offres_existantes()
    nb_avant = len(existantes)

    toutes_brutes = []
    for mot, categorie in MOTS_CLES.items():
        for type_contrat in TYPES_CONTRAT:
            toutes_brutes.extend(scrape_hellowork(mot, categorie, type_contrat))

    nouvelles = 0
    for offre in toutes_brutes:
        lien = offre["lien"]
        if lien in existantes:
            # Rafraîchit les métadonnées, conserve la date de première détection
            date_detectee = existantes[lien].get("date_detectee") or horodatage
            existantes[lien] = {**offre, "date_detectee": date_detectee}
        else:
            existantes[lien] = {**offre, "date_detectee": horodatage}
            nouvelles += 1

    # Filet de sécurité : purge les lignes héritées sans type_contrat
    existantes = {k: v for k, v in existantes.items() if v.get("type_contrat")}

    sauvegarder_offres(existantes)
    print(f"[{horodatage}] {nouvelles} nouvelle(s) offre(s), {len(existantes)} au total (avant : {nb_avant})")

    return existantes


# ---------- GÉNÉRATION DE LA PAGE ----------
def generer_html(offres: list[dict]) -> str:
    categories = sorted(set(o.get("categorie", "Autre") for o in offres))
    data_json = json.dumps(offres, ensure_ascii=False)

    chips_html = "".join(
        f'<button class="chip" data-cat="{cat}">{cat}</button>' for cat in categories
    )

    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Alternances &amp; Stages — École Hexagone</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
  :root {{
    --primaire: {COULEUR_PRIMAIRE};
    --accent: {COULEUR_ACCENT};
    --texte: #16192a;
    --texte-doux: #6b7285;
    --bordure: #e6e9f2;
    --fond: #f7f8fc;
    --rayon: 14px;
  }}

  * {{ box-sizing: border-box; }}
  html {{ scroll-behavior: smooth; }}

  body {{
    margin: 0;
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: var(--fond);
    color: var(--texte);
    -webkit-font-smoothing: antialiased;
  }}

  /* ---------- TOPBAR ---------- */
  .topbar {{
    position: sticky;
    top: 0;
    z-index: 60;
    background: white;
    border-bottom: 1px solid var(--bordure);
    padding: 12px 0;
  }}

  .topbar-inner {{
    max-width: 1240px;
    margin: 0 auto;
    padding: 0 24px;
    display: flex;
    align-items: center;
    gap: 20px;
  }}

  .logo {{
    display: flex;
    align-items: center;
    gap: 9px;
    flex-shrink: 0;
    text-decoration: none;
  }}

  .logo-mark {{
    width: 34px; height: 34px;
    border-radius: 9px;
    background: var(--primaire);
    color: var(--accent);
    display: flex;
    align-items: center;
    justify-content: center;
    font-weight: 800;
    font-size: 1rem;
  }}

  .logo-text {{
    font-weight: 800;
    font-size: 1.05rem;
    color: var(--primaire);
    letter-spacing: -0.4px;
  }}

  .logo-text span {{ color: var(--texte-doux); font-weight: 500; }}

  .search-wrap {{ position: relative; flex: 1; max-width: 520px; }}

  .search-icon {{
    position: absolute;
    left: 16px; top: 50%;
    transform: translateY(-50%);
    color: var(--texte-doux);
    pointer-events: none;
    transition: color 0.2s ease;
  }}

  #search-input {{
    width: 100%;
    padding: 11px 40px 11px 44px;
    border-radius: 999px;
    border: 1.5px solid var(--bordure);
    background: var(--fond);
    font-family: inherit;
    font-size: 0.92rem;
    color: var(--texte);
    outline: none;
    transition: all 0.2s ease;
  }}

  #search-input::placeholder {{ color: #a8aec0; }}

  #search-input:focus {{
    background: white;
    border-color: var(--primaire);
    box-shadow: 0 0 0 4px rgba(34,61,125,0.09);
  }}

  .search-wrap:focus-within .search-icon {{ color: var(--primaire); }}

  .clear-btn {{
    position: absolute;
    right: 14px; top: 50%;
    transform: translateY(-50%);
    background: #dde2ee;
    border: none;
    width: 20px; height: 20px;
    border-radius: 50%;
    cursor: pointer;
    color: var(--texte-doux);
    font-size: 0.8rem;
    line-height: 1;
    display: none;
    align-items: center;
    justify-content: center;
  }}

  .clear-btn.visible {{ display: flex; }}

  .topbar-right {{ margin-left: auto; display: flex; align-items: center; gap: 14px; }}

  .avatar {{
    width: 36px; height: 36px;
    border-radius: 50%;
    background: linear-gradient(135deg, var(--primaire), #3a5ba8);
    color: white;
    display: flex;
    align-items: center;
    justify-content: center;
    font-weight: 700;
    font-size: 0.85rem;
    cursor: pointer;
    border: 2px solid transparent;
    transition: border-color 0.18s ease;
  }}

  .avatar:hover {{ border-color: var(--accent); }}

  /* ---------- LAYOUT ---------- */
  .layout {{
    max-width: 1240px;
    margin: 0 auto;
    padding: 26px 24px 0;
    display: grid;
    grid-template-columns: 290px 1fr;
    gap: 26px;
    align-items: start;
  }}

  /* ---------- SIDEBAR ---------- */
  .sidebar {{
    position: sticky;
    top: 86px;
    display: flex;
    flex-direction: column;
    gap: 14px;
  }}

  .panel {{
    background: white;
    border: 1.5px solid var(--bordure);
    border-radius: var(--rayon);
    padding: 18px;
  }}

  .panel-title {{
    font-size: 0.7rem;
    font-weight: 800;
    text-transform: uppercase;
    letter-spacing: 0.8px;
    color: var(--texte-doux);
    margin: 0 0 12px;
  }}

  .profil {{ display: flex; align-items: center; gap: 12px; }}

  .profil .avatar {{ width: 44px; height: 44px; font-size: 1rem; cursor: default; }}

  .profil-nom {{ font-weight: 700; font-size: 0.95rem; }}
  .profil-sous {{ font-size: 0.8rem; color: var(--texte-doux); }}

  .stats {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }}

  .stat {{
    background: var(--fond);
    border-radius: 10px;
    padding: 12px;
    text-align: center;
  }}

  .stat-num {{ font-size: 1.5rem; font-weight: 800; color: var(--primaire); line-height: 1; }}
  .stat-lbl {{ font-size: 0.7rem; color: var(--texte-doux); margin-top: 4px; font-weight: 600; }}

  /* calendrier */
  .cal-head {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 10px;
  }}

  .cal-mois {{ font-weight: 700; font-size: 0.88rem; text-transform: capitalize; }}

  .cal-grid {{
    display: grid;
    grid-template-columns: repeat(7, 1fr);
    gap: 2px;
    text-align: center;
  }}

  .cal-jour-nom {{
    font-size: 0.62rem;
    font-weight: 700;
    color: var(--texte-doux);
    padding: 4px 0;
    text-transform: uppercase;
  }}

  .cal-case {{
    font-size: 0.75rem;
    padding: 6px 0;
    border-radius: 7px;
    color: var(--texte);
  }}

  .cal-case.vide {{ color: transparent; }}
  .cal-case.today {{ background: var(--primaire); color: white; font-weight: 700; }}

  /* candidatures */
  .cand-liste {{ display: flex; flex-direction: column; gap: 8px; max-height: 240px; overflow-y: auto; }}

  .cand-item {{
    display: flex;
    gap: 9px;
    align-items: center;
    padding: 8px;
    border-radius: 9px;
    background: var(--fond);
    cursor: pointer;
    transition: background 0.15s ease;
  }}

  .cand-item:hover {{ background: #eef1fa; }}

  .cand-txt {{ min-width: 0; }}
  .cand-titre {{ font-size: 0.78rem; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
  .cand-ent {{ font-size: 0.7rem; color: var(--texte-doux); }}

  .cand-vide {{ font-size: 0.8rem; color: var(--texte-doux); line-height: 1.5; }}

  /* ---------- MAIN ---------- */
  .main-head {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 16px;
    flex-wrap: wrap;
    gap: 12px;
  }}

  .main-head h1 {{ margin: 0; font-size: 1.5rem; font-weight: 800; letter-spacing: -0.6px; }}
  .main-head .maj {{ font-size: 0.75rem; color: var(--texte-doux); display: flex; align-items: center; gap: 6px; margin: 4px 0 0; }}

  .dot-live {{
    width: 6px; height: 6px;
    border-radius: 50%;
    background: #22c55e;
    animation: pulse 2s infinite;
  }}

  @keyframes pulse {{
    0% {{ box-shadow: 0 0 0 0 rgba(34,197,94,0.5); }}
    70% {{ box-shadow: 0 0 0 6px rgba(34,197,94,0); }}
    100% {{ box-shadow: 0 0 0 0 rgba(34,197,94,0); }}
  }}

  .filters {{ display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 18px; }}

  .chip {{
    border: 1.5px solid var(--bordure);
    background: white;
    color: var(--texte-doux);
    padding: 7px 14px;
    border-radius: 999px;
    font-family: inherit;
    font-weight: 600;
    font-size: 0.8rem;
    cursor: pointer;
    transition: all 0.18s ease;
    white-space: nowrap;
  }}

  .chip:hover {{ border-color: var(--primaire); color: var(--primaire); }}
  .chip.active {{ background: var(--primaire); border-color: var(--primaire); color: white; }}
  .chip-contrat.active {{ background: var(--accent); border-color: var(--accent); color: var(--primaire); }}

  .sep {{ width: 1px; height: 20px; background: var(--bordure); margin: 0 3px; }}

  .select-wrap {{ position: relative; display: flex; align-items: center; margin-left: auto; }}

  #sort-select {{
    appearance: none; -webkit-appearance: none;
    border: 1.5px solid var(--bordure);
    background: white;
    color: var(--texte-doux);
    padding: 7px 30px 7px 14px;
    border-radius: 999px;
    font-family: inherit;
    font-weight: 600;
    font-size: 0.8rem;
    cursor: pointer;
    outline: none;
  }}

  #sort-select:hover {{ border-color: var(--primaire); color: var(--primaire); }}

  .select-arrow {{ position: absolute; right: 12px; pointer-events: none; color: var(--texte-doux); }}

  .results-count {{ font-size: 0.85rem; color: var(--texte-doux); margin-bottom: 12px; }}
  .results-count strong {{ color: var(--texte); font-weight: 700; }}

  /* ---------- LISTE ---------- */
  .list {{ display: flex; flex-direction: column; gap: 10px; }}

  .row {{
    background: white;
    border: 1.5px solid var(--bordure);
    border-radius: var(--rayon);
    padding: 16px 18px;
    cursor: pointer;
    display: flex;
    align-items: center;
    gap: 15px;
    transition: border-color 0.18s ease, box-shadow 0.18s ease, transform 0.18s ease;
  }}

  .row:hover {{
    border-color: #cbd3e8;
    box-shadow: 0 6px 20px rgba(34,61,125,0.09);
    transform: translateY(-2px);
  }}

  .row-logo {{
    width: 52px; height: 52px;
    border-radius: 12px;
    flex-shrink: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    font-weight: 800;
    font-size: 1.05rem;
    color: white;
    letter-spacing: -0.5px;
    position: relative;
    overflow: hidden;
  }}

  .row-logo img {{
    position: absolute;
    inset: 0;
    width: 100%; height: 100%;
    object-fit: contain;
    background: white;
    padding: 5px;
  }}

  .row-main {{ flex: 1; min-width: 0; }}

  .row h3 {{
    margin: 0 0 4px;
    font-size: 1rem;
    font-weight: 700;
    line-height: 1.35;
    transition: color 0.18s ease;
    overflow: hidden;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
  }}

  .row:hover h3 {{ color: var(--primaire); }}

  .row-ent {{ font-size: 0.86rem; color: var(--texte-doux); font-weight: 600; margin-bottom: 6px; }}

  .row-badges {{ display: flex; gap: 6px; flex-wrap: wrap; align-items: center; }}

  .badge {{
    font-size: 0.63rem;
    font-weight: 700;
    padding: 3px 8px;
    border-radius: 6px;
    text-transform: uppercase;
    letter-spacing: 0.4px;
  }}

  .badge-cat {{ background: #eef1fa; color: var(--primaire); }}
  .badge-contrat {{ background: #f2f4f9; color: var(--texte-doux); border: 1px solid var(--bordure); }}
  .badge-new {{ background: var(--accent); color: var(--primaire); }}
  .badge-date {{ background: transparent; color: var(--texte-doux); text-transform: none; font-weight: 500; letter-spacing: 0; padding-left: 2px; }}

  .row-arrow {{
    flex-shrink: 0;
    width: 30px; height: 30px;
    border-radius: 50%;
    background: var(--fond);
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--texte-doux);
    transition: all 0.18s ease;
  }}

  .row:hover .row-arrow {{ background: var(--primaire); color: white; transform: translateX(3px); }}

  .empty {{
    text-align: center;
    color: var(--texte-doux);
    padding: 70px 20px;
    background: white;
    border: 1.5px dashed var(--bordure);
    border-radius: var(--rayon);
  }}

  .empty strong {{ display: block; color: var(--texte); margin-bottom: 6px; font-size: 1.05rem; }}

  /* ---------- PAGINATION ---------- */
  .pagination {{ display: flex; justify-content: center; align-items: center; gap: 6px; margin: 28px 0 0; flex-wrap: wrap; }}

  .page-btn {{
    min-width: 36px; height: 36px;
    padding: 0 11px;
    border: 1.5px solid var(--bordure);
    background: white;
    color: var(--texte-doux);
    border-radius: 10px;
    font-family: inherit;
    font-weight: 600;
    font-size: 0.85rem;
    cursor: pointer;
    transition: all 0.16s ease;
    display: flex;
    align-items: center;
    justify-content: center;
  }}

  .page-btn:hover:not(:disabled):not(.active) {{ border-color: var(--primaire); color: var(--primaire); }}
  .page-btn.active {{ background: var(--primaire); border-color: var(--primaire); color: white; }}
  .page-btn:disabled {{ opacity: 0.35; cursor: not-allowed; }}
  .page-dots {{ color: var(--texte-doux); padding: 0 3px; font-weight: 600; }}

  /* ---------- MODAL ---------- */
  .overlay {{
    display: none;
    position: fixed;
    inset: 0;
    background: rgba(16,20,35,0.6);
    backdrop-filter: blur(3px);
    z-index: 200;
    align-items: flex-start;
    justify-content: center;
    padding: 40px 16px;
    overflow-y: auto;
    animation: fadeIn 0.18s ease;
  }}

  .overlay.open {{ display: flex; }}

  @keyframes fadeIn {{ from {{ opacity: 0; }} to {{ opacity: 1; }} }}
  @keyframes slideUp {{ from {{ transform: translateY(16px); opacity: 0; }} to {{ transform: translateY(0); opacity: 1; }} }}

  .modal {{
    background: white;
    border-radius: 18px;
    max-width: 640px;
    width: 100%;
    overflow: hidden;
    box-shadow: 0 24px 70px rgba(0,0,0,0.28);
    animation: slideUp 0.22s ease;
  }}

  .modal-header {{
    background: linear-gradient(135deg, var(--primaire) 0%, #1a2f60 100%);
    color: white;
    padding: 28px 30px 24px;
    position: relative;
    display: flex;
    gap: 16px;
    align-items: flex-start;
  }}

  .modal-header .row-logo {{ width: 58px; height: 58px; font-size: 1.15rem; border: 2px solid rgba(255,255,255,0.25); }}

  .modal-header h2 {{
    margin: 0 0 6px;
    font-size: 1.3rem;
    font-weight: 800;
    line-height: 1.3;
    letter-spacing: -0.4px;
    padding-right: 26px;
  }}

  .modal-header .entreprise {{ color: rgba(255,255,255,0.75); font-size: 0.95rem; font-weight: 500; margin-bottom: 10px; }}
  .modal-header .badge-cat {{ background: var(--accent); color: var(--primaire); }}
  .modal-header .badge-contrat {{ background: rgba(255,255,255,0.14); color: white; border-color: rgba(255,255,255,0.25); }}

  .close-btn {{
    position: absolute;
    top: 16px; right: 16px;
    background: rgba(255,255,255,0.12);
    border: none;
    width: 30px; height: 30px;
    border-radius: 50%;
    color: white;
    font-size: 1.05rem;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: background 0.16s ease;
  }}

  .close-btn:hover {{ background: rgba(255,255,255,0.25); }}

  .modal-body {{ padding: 24px 30px 30px; }}

  .modal-meta {{
    display: flex;
    gap: 28px;
    flex-wrap: wrap;
    margin-bottom: 18px;
    padding-bottom: 16px;
    border-bottom: 1px solid var(--bordure);
  }}

  .modal-meta div strong {{
    display: block;
    font-size: 0.66rem;
    text-transform: uppercase;
    letter-spacing: 0.7px;
    color: var(--texte-doux);
    margin-bottom: 3px;
    font-weight: 700;
  }}

  .modal-meta div span {{ font-size: 0.9rem; font-weight: 500; }}

  .modal-desc {{
    font-size: 0.92rem;
    line-height: 1.7;
    color: #3d4356;
    white-space: pre-wrap;
    margin-bottom: 24px;
    max-height: 300px;
    overflow-y: auto;
  }}

  .btn {{
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    font-family: inherit;
    font-weight: 700;
    text-decoration: none;
    padding: 13px 22px;
    border-radius: 11px;
    font-size: 0.93rem;
    width: 100%;
    transition: all 0.16s ease;
    cursor: pointer;
    border: none;
  }}

  .btn-primary {{ background: var(--accent); color: var(--primaire); margin-bottom: 9px; }}
  .btn-primary:hover {{ filter: brightness(0.94); transform: translateY(-1px); }}

  .btn-secondary {{ background: white; color: var(--primaire); border: 1.5px solid var(--bordure); }}
  .btn-secondary:hover {{ border-color: var(--primaire); background: var(--fond); }}

  /* ---------- FOOTER ---------- */
  footer {{
    margin-top: 60px;
    background: var(--primaire);
    color: rgba(255,255,255,0.75);
    padding: 44px 0 26px;
  }}

  .footer-inner {{ max-width: 1240px; margin: 0 auto; padding: 0 24px; }}

  .footer-top {{
    display: grid;
    grid-template-columns: 1.5fr 1fr 1fr 1fr;
    gap: 32px;
    padding-bottom: 30px;
    border-bottom: 1px solid rgba(255,255,255,0.14);
  }}

  .footer-brand .logo-mark {{ background: var(--accent); color: var(--primaire); }}
  .footer-brand .logo-text {{ color: white; }}
  .footer-brand .logo-text span {{ color: rgba(255,255,255,0.55); }}
  .footer-brand p {{ font-size: 0.83rem; line-height: 1.6; margin: 14px 0 0; max-width: 280px; }}

  .footer-col h4 {{
    color: white;
    font-size: 0.72rem;
    text-transform: uppercase;
    letter-spacing: 0.8px;
    margin: 0 0 14px;
    font-weight: 800;
  }}

  .footer-col a {{
    display: block;
    color: rgba(255,255,255,0.7);
    text-decoration: none;
    font-size: 0.85rem;
    margin-bottom: 9px;
    transition: color 0.15s ease;
  }}

  .footer-col a:hover {{ color: var(--accent); }}

  .footer-bottom {{
    padding-top: 22px;
    display: flex;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 10px;
    font-size: 0.78rem;
    color: rgba(255,255,255,0.5);
  }}

  @media (max-width: 960px) {{
    .layout {{ grid-template-columns: 1fr; }}
    .sidebar {{ position: static; }}
    .footer-top {{ grid-template-columns: 1fr 1fr; }}
  }}

  @media (max-width: 640px) {{
    .logo-text {{ display: none; }}
    .row-arrow {{ display: none; }}
    .footer-top {{ grid-template-columns: 1fr; }}
    .modal-header {{ padding: 22px; flex-direction: column; }}
    .modal-body {{ padding: 20px; }}
  }}
</style>
</head>
<body>

<div class="topbar">
  <div class="topbar-inner">
    <a class="logo" href="#">
      <div class="logo-mark">H</div>
      <div class="logo-text">Hexagone<span>Jobs</span></div>
    </a>

    <div class="search-wrap">
      <svg class="search-icon" width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round">
        <circle cx="11" cy="11" r="7"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line>
      </svg>
      <input type="text" id="search-input" placeholder="Rechercher un poste, une entreprise, une techno…" autocomplete="off">
      <button class="clear-btn" id="clear-btn">&times;</button>
    </div>

    <div class="topbar-right">
      <div class="avatar" title="Compte (démo)">KK</div>
    </div>
  </div>
</div>

<div class="layout">
  <aside class="sidebar">

    <div class="panel">
      <div class="profil">
        <div class="avatar">KK</div>
        <div>
          <div class="profil-nom">Étudiant Hexagone</div>
          <div class="profil-sous">Versailles · M1</div>
        </div>
      </div>
    </div>

    <div class="panel">
      <p class="panel-title">Mon activité</p>
      <div class="stats">
        <div class="stat">
          <div class="stat-num" id="stat-cand">0</div>
          <div class="stat-lbl">Candidatures</div>
        </div>
        <div class="stat">
          <div class="stat-num" id="stat-total">0</div>
          <div class="stat-lbl">Offres suivies</div>
        </div>
      </div>
    </div>

    <div class="panel">
      <div class="cal-head">
        <span class="panel-title" style="margin:0">Calendrier</span>
        <span class="cal-mois" id="cal-mois"></span>
      </div>
      <div class="cal-grid" id="cal-grid"></div>
    </div>

    <div class="panel">
      <p class="panel-title">Mes candidatures</p>
      <div class="cand-liste" id="cand-liste"></div>
    </div>

  </aside>

  <main>
    <div class="main-head">
      <div>
        <h1>Offres disponibles</h1>
        <p class="maj"><span class="dot-live"></span><span id="maj-info"></span></p>
      </div>
    </div>

    <div class="filters">
      <button class="chip active" data-cat="Toutes">Tous les domaines</button>
      {chips_html}
      <span class="sep"></span>
      <button class="chip chip-contrat active" data-contrat="Tous">Tous contrats</button>
      <button class="chip chip-contrat" data-contrat="Alternance">Alternance</button>
      <button class="chip chip-contrat" data-contrat="Stage">Stage</button>
      <div class="select-wrap">
        <select id="sort-select">
          <option value="recent">Plus récentes</option>
          <option value="ancien">Plus anciennes</option>
          <option value="titre">Titre (A → Z)</option>
          <option value="entreprise">Entreprise (A → Z)</option>
        </select>
        <svg class="select-arrow" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="6 9 12 15 18 9"></polyline>
        </svg>
      </div>
    </div>

    <div class="results-count" id="results-count"></div>
    <div class="list" id="list"></div>
    <div class="pagination" id="pagination"></div>
  </main>
</div>

<div class="overlay" id="overlay">
  <div class="modal">
    <div class="modal-header">
      <button class="close-btn" id="close-btn">&times;</button>
      <div class="row-logo" id="modal-logo"></div>
      <div style="min-width:0">
        <h2 id="modal-title"></h2>
        <div class="entreprise" id="modal-entreprise"></div>
        <div class="row-badges">
          <span class="badge badge-cat" id="modal-cat"></span>
          <span class="badge badge-contrat" id="modal-contrat"></span>
        </div>
      </div>
    </div>
    <div class="modal-body">
      <div class="modal-meta">
        <div><strong>Publiée</strong><span id="modal-date"></span></div>
        <div><strong>Entreprise</strong><span id="modal-entreprise-2"></span></div>
        <div><strong>Source</strong><span>HelloWork</span></div>
      </div>
      <div class="modal-desc" id="modal-desc"></div>
      <a href="#" target="_blank" rel="noopener" class="btn btn-primary" id="modal-link">
        Voir l'annonce et postuler
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">
          <line x1="5" y1="12" x2="19" y2="12"></line><polyline points="12 5 19 12 12 19"></polyline>
        </svg>
      </a>
      <a href="#" target="_blank" rel="noopener" class="btn btn-secondary" id="modal-linkedin">
        Chercher les employés sur LinkedIn
      </a>
    </div>
  </div>
</div>

<footer>
  <div class="footer-inner">
    <div class="footer-top">
      <div class="footer-brand">
        <a class="logo" href="#">
          <div class="logo-mark">H</div>
          <div class="logo-text">Hexagone<span>Jobs</span></div>
        </a>
        <p>Les offres d'alternance et de stage en Dev, Data, IA et Cybersécurité, agrégées automatiquement pour les élèves de l'École Hexagone.</p>
      </div>
      <div class="footer-col">
        <h4>Domaines</h4>
        <a href="#">Développement</a>
        <a href="#">Data</a>
        <a href="#">Intelligence Artificielle</a>
        <a href="#">Cybersécurité</a>
      </div>
      <div class="footer-col">
        <h4>Ressources</h4>
        <a href="https://www.hellowork.com" target="_blank" rel="noopener">HelloWork</a>
        <a href="https://www.linkedin.com" target="_blank" rel="noopener">LinkedIn</a>
        <a href="https://labonnealternance.apprentissage.beta.gouv.fr" target="_blank" rel="noopener">La Bonne Alternance</a>
      </div>
      <div class="footer-col">
        <h4>À propos</h4>
        <a href="#">Le projet</a>
        <a href="#">Mentions légales</a>
        <a href="#">Contact</a>
      </div>
    </div>
    <div class="footer-bottom">
      <span>© 2026 HexagoneJobs — projet étudiant</span>
      <span id="footer-maj"></span>
    </div>
  </div>
</footer>

<script>
  const OFFRES = {data_json};
  const GENERE_LE = "{datetime.now().strftime('%d/%m/%Y à %H:%M')}";
  const PAR_PAGE = {OFFRES_PAR_PAGE};

  let activeCat = "Toutes";
  let activeContrat = "Tous";
  let searchQuery = "";
  let pageCourante = 1;
  let triActif = "recent";
  let candidatures = [];

  document.getElementById("maj-info").textContent = "Mis à jour le " + GENERE_LE;
  document.getElementById("footer-maj").textContent = "Dernière actualisation : " + GENERE_LE;
  document.getElementById("stat-total").textContent = OFFRES.length;

  /* ---------- logos générés ---------- */
  const PALETTE = ["#223d7d","#2f6fb5","#3e8a7a","#8a5b2f","#7b3f8f","#b04a4a","#3a6b3a","#5a5f8a"];

  function initiales(nom) {{
    const mots = (nom || "?").replace(/[^\\p{{L}}\\s]/gu, " ").trim().split(/\\s+/);
    if (mots.length === 1) return mots[0].substring(0, 2).toUpperCase();
    return (mots[0][0] + mots[1][0]).toUpperCase();
  }}

  function couleurLogo(nom) {{
    let h = 0;
    for (let i = 0; i < (nom || "").length; i++) h = (h * 31 + nom.charCodeAt(i)) % 9973;
    return PALETTE[h % PALETTE.length];
  }}
  function logoHTML(offre, style) {{
    const ent = offre.entreprise || "";
    const img = offre.logo
      ? `<img src="${{offre.logo}}" alt="" loading="lazy" onerror="this.remove()">`
      : "";
    return `<div class="row-logo" style="background:${{couleurLogo(ent)}};${{style || ""}}">${{initiales(ent)}}${{img}}</div>`;
  }}

  /* ---------- calendrier ---------- */
  function renderCalendrier() {{
    const now = new Date();
    const annee = now.getFullYear(), mois = now.getMonth();
    document.getElementById("cal-mois").textContent =
      now.toLocaleDateString("fr-FR", {{ month: "long", year: "numeric" }});

    const premier = new Date(annee, mois, 1).getDay();
    const decalage = (premier + 6) % 7;
    const nbJours = new Date(annee, mois + 1, 0).getDate();

    let html = ["L","M","M","J","V","S","D"]
      .map(j => `<div class="cal-jour-nom">${{j}}</div>`).join("");

    for (let i = 0; i < decalage; i++) html += '<div class="cal-case vide">0</div>';
    for (let j = 1; j <= nbJours; j++) {{
      const today = (j === now.getDate()) ? " today" : "";
      html += `<div class="cal-case${{today}}">${{j}}</div>`;
    }}
    document.getElementById("cal-grid").innerHTML = html;
  }}

  /* ---------- candidatures (simulation) ---------- */
  function chargerCandidatures() {{
    try {{
      candidatures = JSON.parse(localStorage.getItem("hexagone_candidatures") || "[]");
    }} catch (e) {{ candidatures = []; }}
  }}

  function sauverCandidatures() {{
    try {{ localStorage.setItem("hexagone_candidatures", JSON.stringify(candidatures)); }} catch (e) {{}}
  }}

  function ajouterCandidature(offre) {{
    if (candidatures.some(c => c.lien === offre.lien)) return;
    candidatures.unshift({{ lien: offre.lien, titre: offre.titre, entreprise: offre.entreprise, logo: offre.logo }});
    sauverCandidatures();
    renderCandidatures();
  }}

  function renderCandidatures() {{
    const el = document.getElementById("cand-liste");
    document.getElementById("stat-cand").textContent = candidatures.length;

    if (candidatures.length === 0) {{
      el.innerHTML = '<div class="cand-vide">Aucune candidature pour le moment. Clique sur « postuler » dans une offre pour la suivre ici.</div>';
      return;
    }}

    el.innerHTML = candidatures.map(c => `
      <div class="cand-item" data-lien="${{encodeURIComponent(c.lien)}}">
        ${{logoHTML(c, "width:30px;height:30px;font-size:0.7rem;border-radius:8px")}}
        <div class="cand-txt">
          <div class="cand-titre">${{c.titre}}</div>
          <div class="cand-ent">${{c.entreprise || "Non précisé"}}</div>
        </div>
      </div>
    `).join("");

    el.querySelectorAll(".cand-item").forEach(item => {{
      item.addEventListener("click", () => {{
        const lien = decodeURIComponent(item.dataset.lien);
        openModal(OFFRES.find(o => o.lien === lien));
      }});
    }});
  }}

  /* ---------- filtres / tri ---------- */
  function estRecente(offre) {{
    if (!offre.date_detectee) return false;
    const d = new Date(offre.date_detectee.replace(" ", "T"));
    return (new Date() - d) < 24 * 3600 * 1000;
  }}

  function correspondRecherche(offre, q) {{
    if (!q) return true;
    const cible = (offre.titre + " " + offre.entreprise + " " + offre.description).toLowerCase();
    return q.toLowerCase().split(/\\s+/).every(mot => cible.includes(mot));
  }}

  function ancienneteJours(offre) {{
    const txt = (offre.date_publiee || "").toLowerCase();
    if (txt.includes("aujourd")) return 0;
    if (txt.includes("hier")) return 1;

    const rel = txt.match(/il y a (\\d+)\\s*(heure|jour|semaine|mois)/);
    if (rel) {{
      const n = parseInt(rel[1]);
      if (rel[2] === "heure") return n / 24;
      if (rel[2] === "jour") return n;
      if (rel[2] === "semaine") return n * 7;
      if (rel[2] === "mois") return n * 30;
    }}

    const abs = txt.match(/(\\d{{1,2}})\\/(\\d{{1,2}})\\/(\\d{{2,4}})/);
    if (abs) {{
      let annee = parseInt(abs[3]);
      if (annee < 100) annee += 2000;
      const d = new Date(annee, parseInt(abs[2]) - 1, parseInt(abs[1]));
      if (!isNaN(d)) return (new Date() - d) / 86400000;
    }}

    if (offre.date_detectee) {{
      const det = new Date(offre.date_detectee.replace(" ", "T"));
      if (!isNaN(det)) return (new Date() - det) / 86400000;
    }}
    return 99999;
  }}

  function offresFiltrees() {{
    const r = OFFRES.filter(o => {{
      const okCat = activeCat === "Toutes" || o.categorie === activeCat;
      const okContrat = activeContrat === "Tous" || o.type_contrat === activeContrat;
      return okCat && okContrat && correspondRecherche(o, searchQuery);
    }});

    if (triActif === "recent") r.sort((a, b) => ancienneteJours(a) - ancienneteJours(b));
    else if (triActif === "ancien") r.sort((a, b) => ancienneteJours(b) - ancienneteJours(a));
    else if (triActif === "titre") r.sort((a, b) => (a.titre || "").localeCompare(b.titre || "", "fr"));
    else if (triActif === "entreprise") r.sort((a, b) => (a.entreprise || "").localeCompare(b.entreprise || "", "fr"));

    return r;
  }}

  /* ---------- rendu ---------- */
  function render() {{
    const liste = document.getElementById("list");
    const filtrees = offresFiltrees();
    const totalPages = Math.max(1, Math.ceil(filtrees.length / PAR_PAGE));
    if (pageCourante > totalPages) pageCourante = totalPages;

    document.getElementById("results-count").innerHTML =
      "<strong>" + filtrees.length + "</strong> offre" + (filtrees.length > 1 ? "s" : "") +
      (filtrees.length > 0 ? " — page " + pageCourante + " sur " + totalPages : "");

    if (filtrees.length === 0) {{
      liste.innerHTML = '<div class="empty"><strong>Aucun résultat</strong>Essaie un autre mot-clé ou élargis les filtres.</div>';
      document.getElementById("pagination").innerHTML = "";
      return;
    }}

    const debut = (pageCourante - 1) * PAR_PAGE;
    liste.innerHTML = filtrees.slice(debut, debut + PAR_PAGE).map(o => `
      <div class="row" data-lien="${{encodeURIComponent(o.lien)}}">
        ${{logoHTML(o)}}
        <div class="row-main">
          <h3>${{o.titre}}</h3>
          <div class="row-ent">${{o.entreprise || "Non précisé"}}</div>
          <div class="row-badges">
            <span class="badge badge-cat">${{o.categorie || "Autre"}}</span>
            <span class="badge badge-contrat">${{o.type_contrat || ""}}</span>
            ${{estRecente(o) ? '<span class="badge badge-new">Nouveau</span>' : ''}}
            <span class="badge badge-date">${{o.date_publiee || ""}}</span>
          </div>
        </div>
        <div class="row-arrow">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="9 18 15 12 9 6"></polyline>
          </svg>
        </div>
      </div>
    `).join("");

    liste.querySelectorAll(".row").forEach(row => {{
      row.addEventListener("click", () => {{
        const lien = decodeURIComponent(row.dataset.lien);
        openModal(OFFRES.find(o => o.lien === lien));
      }});
    }});

    renderPagination(totalPages);
  }}

  function renderPagination(totalPages) {{
    const pag = document.getElementById("pagination");
    if (totalPages <= 1) {{ pag.innerHTML = ""; return; }}

    let html = `<button class="page-btn" data-page="${{pageCourante - 1}}" ${{pageCourante === 1 ? "disabled" : ""}}>‹</button>`;
    const pages = [];
    for (let i = 1; i <= totalPages; i++) {{
      if (i === 1 || i === totalPages || Math.abs(i - pageCourante) <= 1) pages.push(i);
      else if (pages[pages.length - 1] !== "...") pages.push("...");
    }}
    pages.forEach(p => {{
      if (p === "...") html += '<span class="page-dots">…</span>';
      else html += `<button class="page-btn ${{p === pageCourante ? "active" : ""}}" data-page="${{p}}">${{p}}</button>`;
    }});
    html += `<button class="page-btn" data-page="${{pageCourante + 1}}" ${{pageCourante === totalPages ? "disabled" : ""}}>›</button>`;
    pag.innerHTML = html;

    pag.querySelectorAll(".page-btn[data-page]").forEach(btn => {{
      btn.addEventListener("click", () => {{
        const p = parseInt(btn.dataset.page);
        if (isNaN(p) || p < 1 || p > totalPages) return;
        pageCourante = p;
        render();
        window.scrollTo({{ top: 0, behavior: "smooth" }});
      }});
    }});
  }}

  /* ---------- modal ---------- */
  function openModal(offre) {{
    if (!offre) return;
    const ent = (offre.entreprise || "").trim();

    const ancien = document.getElementById("modal-logo");
    const neuf = document.createElement("div");
    neuf.innerHTML = logoHTML(offre, "width:58px;height:58px;font-size:1.15rem;border:2px solid rgba(255,255,255,0.25)");
    const logoEl = neuf.firstElementChild;
    logoEl.id = "modal-logo";
    ancien.replaceWith(logoEl);

    document.getElementById("modal-cat").textContent = offre.categorie || "Autre";
    document.getElementById("modal-contrat").textContent = offre.type_contrat || "";
    document.getElementById("modal-title").textContent = offre.titre;
    document.getElementById("modal-entreprise").textContent = ent || "Non précisé";
    document.getElementById("modal-entreprise-2").textContent = ent || "Non précisé";
    document.getElementById("modal-date").textContent = offre.date_publiee || "Non précisée";
    document.getElementById("modal-desc").textContent = offre.description || "";

    const lien = document.getElementById("modal-link");
    lien.href = offre.lien;
    lien.onclick = () => ajouterCandidature(offre);

    const li = document.getElementById("modal-linkedin");
    if (ent && ent !== "Non précisé") {{
      li.href = "https://www.linkedin.com/search/results/people/?keywords=" + encodeURIComponent(ent);
      li.textContent = "Chercher les employés de " + ent + " sur LinkedIn";
    }} else {{
      li.href = "https://www.linkedin.com/search/results/all/?keywords=" + encodeURIComponent(offre.titre || "");
      li.textContent = "Chercher cette offre sur LinkedIn";
    }}

    document.getElementById("overlay").classList.add("open");
    document.body.style.overflow = "hidden";
  }}

  function closeModal() {{
    document.getElementById("overlay").classList.remove("open");
    document.body.style.overflow = "";
  }}

  document.getElementById("close-btn").addEventListener("click", closeModal);
  document.getElementById("overlay").addEventListener("click", e => {{
    if (e.target.id === "overlay") closeModal();
  }});
  document.addEventListener("keydown", e => {{ if (e.key === "Escape") closeModal(); }});

  /* ---------- écouteurs ---------- */
  document.querySelectorAll(".chip[data-cat]").forEach(chip => {{
    chip.addEventListener("click", () => {{
      document.querySelectorAll(".chip[data-cat]").forEach(c => c.classList.remove("active"));
      chip.classList.add("active");
      activeCat = chip.dataset.cat;
      pageCourante = 1;
      render();
    }});
  }});

  document.querySelectorAll(".chip[data-contrat]").forEach(chip => {{
    chip.addEventListener("click", () => {{
      document.querySelectorAll(".chip[data-contrat]").forEach(c => c.classList.remove("active"));
      chip.classList.add("active");
      activeContrat = chip.dataset.contrat;
      pageCourante = 1;
      render();
    }});
  }});

  const input = document.getElementById("search-input");
  const clearBtn = document.getElementById("clear-btn");

  input.addEventListener("input", e => {{
    searchQuery = e.target.value;
    clearBtn.classList.toggle("visible", searchQuery.length > 0);
    pageCourante = 1;
    render();
  }});

  clearBtn.addEventListener("click", () => {{
    input.value = ""; searchQuery = "";
    clearBtn.classList.remove("visible");
    pageCourante = 1;
    render();
    input.focus();
  }});

  document.getElementById("sort-select").addEventListener("change", e => {{
    triActif = e.target.value;
    pageCourante = 1;
    render();
  }});

  /* ---------- init ---------- */
  chargerCandidatures();
  renderCalendrier();
  renderCandidatures();
  render();

  setTimeout(() => location.reload(), {AUTO_RELOAD_MINUTES} * 60 * 1000);
</script>

</body>
</html>
"""    

def main():
    offres_dict = scraper_et_fusionner()
    html_content = generer_html(list(offres_dict.values()))

    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"Page générée -> {OUTPUT_HTML} ({len(offres_dict)} offres)")


if __name__ == "__main__":
    main()