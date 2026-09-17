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
FIELDNAMES = ["titre", "entreprise", "date_publiee", "description", "lien",
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
    # 1. Sélecteurs dédiés (les plus fiables si présents)
    for sel in ["[class*='company']", "[class*='employer']", "[data-testid*='company']",
                "[class*='Company']", "span[class*='tw-typo']"]:
        el = card.select_one(sel)
        if el:
            txt = el.get_text(strip=True)
            if txt and txt != titre and 2 < len(txt) < 60:
                return txt

    # 2. Fallback : segment suivant le titre dans le texte du bloc
    segments = [s.strip() for s in texte_bloc.split("|") if s.strip()]
    try:
        idx = next(i for i, s in enumerate(segments) if titre in s or s in titre)
        for suivant in segments[idx + 1:]:
            # Écarte les segments qui sont clairement des métadonnées, pas un nom d'entreprise
            if DATE_PATTERN.search(suivant):
                continue
            if re.search(r"\b(alternance|stage|cdi|cdd|temps plein|télétravail|\d{2,5}\s?€)\b",
                         suivant, re.IGNORECASE):
                continue
            if 2 < len(suivant) < 60:
                return suivant
    except StopIteration:
        pass

    return "Non précisé"    

    for sel in ["[class*='company']", "[class*='employer']", "[data-testid*='company']", "p"]:
        el = card.select_one(sel)
        if el:
            txt = el.get_text(strip=True)
            if txt and txt != titre and len(txt) < 60:
                return txt

    idx_titre = texte_bloc.find(titre)
    if idx_titre != -1:
        reste = texte_bloc[idx_titre + len(titre):].strip(" |")
        candidat = reste.split(" | ")[0].strip()
        if candidat and len(candidat) < 60:
            return candidat
    return "Non précisé"


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
            date_pub = extraire_date(texte_bloc)

            resultats.append({
                "titre": titre,
                "entreprise": entreprise,
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
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            existantes[row["lien"]] = row
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
    --primaire-clair: #2f4f9e;
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

  /* ---------- HEADER ---------- */
  header {{
    background: linear-gradient(135deg, var(--primaire) 0%, #1a2f60 100%);
    color: white;
    padding: 48px 24px 40px;
    text-align: center;
    position: relative;
    overflow: hidden;
  }}

  header::after {{
    content: "";
    position: absolute;
    width: 320px; height: 320px;
    background: var(--accent);
    opacity: 0.09;
    border-radius: 50%;
    top: -160px; right: -80px;
  }}

  .eyebrow {{
    display: inline-block;
    background: rgba(255,255,255,0.12);
    border: 1px solid rgba(255,255,255,0.2);
    padding: 5px 14px;
    border-radius: 999px;
    font-size: 0.72rem;
    font-weight: 600;
    letter-spacing: 1px;
    text-transform: uppercase;
    margin-bottom: 16px;
  }}

  header h1 {{
    margin: 0 0 10px;
    font-size: 2.2rem;
    font-weight: 800;
    letter-spacing: -1px;
    line-height: 1.15;
  }}

  header h1 span {{ color: var(--accent); }}

  header .sous-titre {{
    margin: 0;
    opacity: 0.8;
    font-size: 1rem;
    font-weight: 400;
  }}

  .maj {{
    font-size: 0.75rem;
    opacity: 0.55;
    margin-top: 18px;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 7px;
  }}

  .dot-live {{
    width: 7px; height: 7px;
    border-radius: 50%;
    background: #4ade80;
    box-shadow: 0 0 0 0 rgba(74,222,128,0.6);
    animation: pulse 2s infinite;
  }}

  @keyframes pulse {{
    0% {{ box-shadow: 0 0 0 0 rgba(74,222,128,0.5); }}
    70% {{ box-shadow: 0 0 0 7px rgba(74,222,128,0); }}
    100% {{ box-shadow: 0 0 0 0 rgba(74,222,128,0); }}
  }}

  /* ---------- BARRE STICKY ---------- */
  .sticky-bar {{
    position: sticky;
    top: 0;
    z-index: 50;
    background: rgba(247,248,252,0.88);
    backdrop-filter: saturate(180%) blur(14px);
    -webkit-backdrop-filter: saturate(180%) blur(14px);
    border-bottom: 1px solid var(--bordure);
    padding: 18px 0 14px;
  }}

  .container {{ max-width: 920px; margin: 0 auto; padding: 0 20px; }}

  /* ---------- RECHERCHE ---------- */
  .search-wrap {{
    position: relative;
    margin-bottom: 14px;
  }}

  .search-icon {{
    position: absolute;
    left: 20px; top: 50%;
    transform: translateY(-50%);
    color: var(--texte-doux);
    pointer-events: none;
    transition: color 0.2s ease;
  }}

  #search-input {{
    width: 100%;
    padding: 15px 46px 15px 52px;
    border-radius: 999px;
    border: 1.5px solid var(--bordure);
    background: white;
    font-family: inherit;
    font-size: 0.98rem;
    color: var(--texte);
    outline: none;
    transition: border-color 0.2s ease, box-shadow 0.2s ease;
    box-shadow: 0 1px 3px rgba(22,25,42,0.04);
  }}

  #search-input::placeholder {{ color: #a8aec0; }}

  #search-input:focus {{
    border-color: var(--primaire);
    box-shadow: 0 0 0 4px rgba(34,61,125,0.1);
  }}

  .search-wrap:focus-within .search-icon {{ color: var(--primaire); }}

  .clear-btn {{
    position: absolute;
    right: 16px; top: 50%;
    transform: translateY(-50%);
    background: #eceff7;
    border: none;
    width: 24px; height: 24px;
    border-radius: 50%;
    cursor: pointer;
    color: var(--texte-doux);
    font-size: 0.9rem;
    line-height: 1;
    display: none;
    align-items: center;
    justify-content: center;
    transition: background 0.15s ease;
  }}

  .clear-btn:hover {{ background: #dde2ee; }}
  .clear-btn.visible {{ display: flex; }}

  /* ---------- FILTRES ---------- */
  .filters {{
    display: flex;
    align-items: center;
    gap: 10px;
    flex-wrap: wrap;
  }}

  .chip {{
    border: 1.5px solid var(--bordure);
    background: white;
    color: var(--texte-doux);
    padding: 7px 15px;
    border-radius: 999px;
    font-family: inherit;
    font-weight: 600;
    font-size: 0.82rem;
    cursor: pointer;
    transition: all 0.18s ease;
    white-space: nowrap;
  }}

  .chip:hover {{
    border-color: var(--primaire);
    color: var(--primaire);
    transform: translateY(-1px);
  }}

  .chip.active {{
    background: var(--primaire);
    border-color: var(--primaire);
    color: white;
  }}

  .chip-contrat.active {{
    background: var(--accent);
    border-color: var(--accent);
    color: var(--primaire);
  }}

  .sep {{
    width: 1px;
    height: 22px;
    background: var(--bordure);
    margin: 0 4px;
  }}
    .select-wrap {{ position: relative; display: flex; align-items: center; }}

  #sort-select {{
    appearance: none;
    -webkit-appearance: none;
    border: 1.5px solid var(--bordure);
    background: white;
    color: var(--texte-doux);
    padding: 7px 32px 7px 15px;
    border-radius: 999px;
    font-family: inherit;
    font-weight: 600;
    font-size: 0.82rem;
    cursor: pointer;
    outline: none;
    transition: all 0.18s ease;
  }}

  #sort-select:hover {{ border-color: var(--primaire); color: var(--primaire); }}
  #sort-select:focus {{ border-color: var(--primaire); box-shadow: 0 0 0 3px rgba(34,61,125,0.1); }}

  .select-arrow {{
    position: absolute;
    right: 13px;
    pointer-events: none;
    color: var(--texte-doux);
  }}

  /* ---------- RÉSULTATS ---------- */
  .results-head {{
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    margin: 28px 0 14px;
  }}

  .results-count {{
    font-size: 0.9rem;
    color: var(--texte-doux);
  }}

  .results-count strong {{ color: var(--texte); font-weight: 700; }}

  .list {{
    display: flex;
    flex-direction: column;
    gap: 10px;
    padding-bottom: 8px;
  }}

  .row {{
    background: white;
    border: 1.5px solid var(--bordure);
    border-radius: var(--rayon);
    padding: 18px 20px;
    cursor: pointer;
    display: flex;
    align-items: center;
    gap: 16px;
    transition: border-color 0.18s ease, box-shadow 0.18s ease, transform 0.18s ease;
    position: relative;
    overflow: hidden;
  }}

  .row::before {{
    content: "";
    position: absolute;
    left: 0; top: 0; bottom: 0;
    width: 3px;
    background: var(--accent);
    transform: scaleY(0);
    transition: transform 0.22s ease;
  }}

  .row:hover {{
    border-color: #cbd3e8;
    box-shadow: 0 6px 20px rgba(34,61,125,0.09);
    transform: translateY(-2px);
  }}

  .row:hover::before {{ transform: scaleY(1); }}

  .row-main {{ flex: 1; min-width: 0; }}

  .row-badges {{
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
    margin-bottom: 7px;
    align-items: center;
  }}

  .badge {{
    font-size: 0.65rem;
    font-weight: 700;
    padding: 3px 9px;
    border-radius: 6px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }}

  .badge-cat {{ background: #eef1fa; color: var(--primaire); }}
  .badge-contrat {{ background: #f2f4f9; color: var(--texte-doux); border: 1px solid var(--bordure); }}
  .badge-new {{ background: var(--accent); color: var(--primaire); }}

  .row h3 {{
    margin: 0 0 5px;
    font-size: 1.02rem;
    font-weight: 700;
    color: var(--texte);
    line-height: 1.35;
    transition: color 0.18s ease;
    overflow: hidden;
    text-overflow: ellipsis;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
  }}

  .row:hover h3 {{ color: var(--primaire); }}

  .row-meta {{
    display: flex;
    gap: 14px;
    flex-wrap: wrap;
    font-size: 0.84rem;
    color: var(--texte-doux);
  }}

  .row-meta span {{ display: flex; align-items: center; gap: 5px; }}

  .row-arrow {{
    flex-shrink: 0;
    width: 32px; height: 32px;
    border-radius: 50%;
    background: #f2f4f9;
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--texte-doux);
    transition: all 0.18s ease;
  }}

  .row:hover .row-arrow {{
    background: var(--primaire);
    color: white;
    transform: translateX(3px);
  }}

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
  .pagination {{
    display: flex;
    justify-content: center;
    align-items: center;
    gap: 6px;
    margin: 32px 0 60px;
    flex-wrap: wrap;
  }}

  .page-btn {{
    min-width: 38px;
    height: 38px;
    padding: 0 12px;
    border: 1.5px solid var(--bordure);
    background: white;
    color: var(--texte-doux);
    border-radius: 10px;
    font-family: inherit;
    font-weight: 600;
    font-size: 0.88rem;
    cursor: pointer;
    transition: all 0.16s ease;
    display: flex;
    align-items: center;
    justify-content: center;
  }}

  .page-btn:hover:not(:disabled):not(.active) {{
    border-color: var(--primaire);
    color: var(--primaire);
  }}

  .page-btn.active {{
    background: var(--primaire);
    border-color: var(--primaire);
    color: white;
  }}

  .page-btn:disabled {{ opacity: 0.35; cursor: not-allowed; }}

  .page-dots {{ color: var(--texte-doux); padding: 0 4px; font-weight: 600; }}

  /* ---------- MODAL ---------- */
  .overlay {{
    display: none;
    position: fixed;
    inset: 0;
    background: rgba(16, 20, 35, 0.6);
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
    max-width: 620px;
    width: 100%;
    overflow: hidden;
    box-shadow: 0 24px 70px rgba(0,0,0,0.28);
    animation: slideUp 0.22s ease;
  }}

  .modal-header {{
    background: linear-gradient(135deg, var(--primaire) 0%, #1a2f60 100%);
    color: white;
    padding: 30px 30px 24px;
    position: relative;
  }}

  .modal-header .badge-cat {{ background: var(--accent); color: var(--primaire); }}
  .modal-header .badge-contrat {{ background: rgba(255,255,255,0.14); color: white; border-color: rgba(255,255,255,0.25); }}

  .modal-header h2 {{
    margin: 14px 0 6px;
    font-size: 1.45rem;
    font-weight: 800;
    line-height: 1.3;
    letter-spacing: -0.4px;
    padding-right: 30px;
  }}

  .modal-header .entreprise {{
    color: rgba(255,255,255,0.75);
    font-size: 1rem;
    font-weight: 500;
  }}

  .close-btn {{
    position: absolute;
    top: 18px; right: 18px;
    background: rgba(255,255,255,0.12);
    border: none;
    width: 32px; height: 32px;
    border-radius: 50%;
    color: white;
    font-size: 1.1rem;
    cursor: pointer;
    line-height: 1;
    transition: background 0.16s ease;
    display: flex;
    align-items: center;
    justify-content: center;
  }}

  .close-btn:hover {{ background: rgba(255,255,255,0.25); }}

  .modal-body {{ padding: 26px 30px 30px; }}

  .modal-meta {{
    display: flex;
    gap: 28px;
    flex-wrap: wrap;
    margin-bottom: 20px;
    padding-bottom: 18px;
    border-bottom: 1px solid var(--bordure);
  }}

  .modal-meta div strong {{
    display: block;
    font-size: 0.68rem;
    text-transform: uppercase;
    letter-spacing: 0.7px;
    color: var(--texte-doux);
    margin-bottom: 3px;
    font-weight: 700;
  }}

  .modal-meta div span {{ font-size: 0.92rem; font-weight: 500; }}

  .modal-desc {{
    font-size: 0.93rem;
    line-height: 1.7;
    color: #3d4356;
    white-space: pre-wrap;
    margin-bottom: 26px;
    max-height: 320px;
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
    padding: 14px 24px;
    border-radius: 11px;
    font-size: 0.95rem;
    width: 100%;
    transition: all 0.16s ease;
    cursor: pointer;
  }}

  .btn-primary {{
    background: var(--accent);
    color: var(--primaire);
    border: none;
    margin-bottom: 10px;
  }}

  .btn-primary:hover {{ filter: brightness(0.94); transform: translateY(-1px); }}

  .btn-secondary {{
    background: white;
    color: var(--primaire);
    border: 1.5px solid var(--bordure);
  }}

  .btn-secondary:hover {{ border-color: var(--primaire); background: #f7f8fc; }}

  @media (max-width: 640px) {{
    header h1 {{ font-size: 1.65rem; }}
    .row {{ padding: 16px; }}
    .row-arrow {{ display: none; }}
    .modal-header {{ padding: 24px 22px 20px; }}
    .modal-body {{ padding: 22px; }}
  }}
</style>
</head>
<body>

<header>
  <span class="eyebrow">École Hexagone</span>
  <h1>Alternances &amp; <span>Stages</span></h1>
  <p class="sous-titre">Développement · Data · Intelligence Artificielle · Cybersécurité</p>
  <p class="maj"><span class="dot-live"></span><span id="maj-info"></span></p>
</header>

<div class="sticky-bar">
  <div class="container">
    <div class="search-wrap">
      <svg class="search-icon" width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round">
        <circle cx="11" cy="11" r="7"></circle>
        <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
      </svg>
      <input type="text" id="search-input" placeholder="Rechercher un poste, une entreprise, une techno…" autocomplete="off">
      <button class="clear-btn" id="clear-btn" title="Effacer">&times;</button>
    </div>

    <div class="filters">
      <button class="chip active" data-cat="Toutes">Tous les domaines</button>
      {chips_html}
      <span class="sep"></span>
      <button class="chip chip-contrat active" data-contrat="Tous">Tous contrats</button>
      <button class="chip chip-contrat" data-contrat="Alternance">Alternance</button>
      <button class="chip chip-contrat" data-contrat="Stage">Stage</button>
            <span class="sep"></span>
      <div class="select-wrap">
        <select id="sort-select">
          <option value="recent">Plus récentes d'abord</option>
          <option value="ancien">Plus anciennes d'abord</option>
          <option value="titre">Titre (A → Z)</option>
          <option value="entreprise">Entreprise (A → Z)</option>
        </select>
        <svg class="select-arrow" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="6 9 12 15 18 9"></polyline>
        </svg>
      </div>
    </div>
  </div>
</div>

<div class="container">
  <div class="results-head">
    <div class="results-count" id="results-count"></div>
  </div>

  <div class="list" id="list"></div>
  <div class="pagination" id="pagination"></div>
</div>

<div class="overlay" id="overlay">
  <div class="modal">
    <div class="modal-header">
      <button class="close-btn" id="close-btn">&times;</button>
      <div class="row-badges">
        <span class="badge badge-cat" id="modal-cat"></span>
        <span class="badge badge-contrat" id="modal-contrat"></span>
      </div>
      <h2 id="modal-title"></h2>
      <div class="entreprise" id="modal-entreprise"></div>
    </div>
    <div class="modal-body">
      <div class="modal-meta">
        <div><strong>Publiée</strong><span id="modal-date"></span></div>
        <div><strong>Entreprise</strong><span id="modal-entreprise-2"></span></div>
      </div>
      <div class="modal-desc" id="modal-desc"></div>
      <a href="#" target="_blank" rel="noopener" class="btn btn-primary" id="modal-link">
        Voir l'annonce et postuler
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">
          <line x1="5" y1="12" x2="19" y2="12"></line><polyline points="12 5 19 12 12 19"></polyline>
        </svg>
      </a>
      <a href="#" target="_blank" rel="noopener" class="btn btn-secondary" id="modal-linkedin">
        Chercher les employés sur LinkedIn
      </a>
    </div>
  </div>
</div>

<script>
  const OFFRES = {data_json};
  const GENERE_LE = "{datetime.now().strftime('%d/%m/%Y à %H:%M')}";
  const PAR_PAGE = {OFFRES_PAR_PAGE};

  let activeCat = "Toutes";
  let activeContrat = "Tous";
  let searchQuery = "";
  let pageCourante = 1;
  let triActif = "recent";

  document.getElementById("maj-info").textContent = "Mis à jour le " + GENERE_LE;

  function estRecente(offre) {{
    if (!offre.date_detectee) return false;
    const detectee = new Date(offre.date_detectee.replace(" ", "T"));
    return (new Date() - detectee) < 24 * 3600 * 1000;
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

    // Repli : date de détection par le scraper
    if (offre.date_detectee) {{
      const det = new Date(offre.date_detectee.replace(" ", "T"));
      if (!isNaN(det)) return (new Date() - det) / 86400000;
    }}

    return 99999;
  }}

  function offresFiltrees() {{
    const resultat = OFFRES.filter(o => {{
      const okCat = activeCat === "Toutes" || o.categorie === activeCat;
      const okContrat = activeContrat === "Tous" || o.type_contrat === activeContrat;
      return okCat && okContrat && correspondRecherche(o, searchQuery);
    }});

    if (triActif === "recent") {{
      resultat.sort((a, b) => ancienneteJours(a) - ancienneteJours(b));
    }} else if (triActif === "ancien") {{
      resultat.sort((a, b) => ancienneteJours(b) - ancienneteJours(a));
    }} else if (triActif === "titre") {{
      resultat.sort((a, b) => (a.titre || "").localeCompare(b.titre || "", "fr"));
    }} else if (triActif === "entreprise") {{
      resultat.sort((a, b) => (a.entreprise || "").localeCompare(b.entreprise || "", "fr"));
    }}

    return resultat;
  }}

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
    const pageOffres = filtrees.slice(debut, debut + PAR_PAGE);

    liste.innerHTML = pageOffres.map(o => `
      <div class="row" data-lien="${{encodeURIComponent(o.lien)}}">
        <div class="row-main">
          <div class="row-badges">
            <span class="badge badge-cat">${{o.categorie || "Autre"}}</span>
            <span class="badge badge-contrat">${{o.type_contrat || ""}}</span>
            ${{estRecente(o) ? '<span class="badge badge-new">Nouveau</span>' : ''}}
          </div>
          <h3>${{o.titre}}</h3>
          <div class="row-meta">
            <span>${{o.entreprise || "Non précisé"}}</span>
            <span>${{o.date_publiee || ""}}</span>
          </div>
        </div>
        <div class="row-arrow">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="9 18 15 12 9 6"></polyline>
          </svg>
        </div>
      </div>
    `).join("");

    document.querySelectorAll(".row").forEach(row => {{
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

  function openModal(offre) {{
    if (!offre) return;
    document.getElementById("modal-cat").textContent = offre.categorie || "Autre";
    document.getElementById("modal-contrat").textContent = offre.type_contrat || "";
    document.getElementById("modal-title").textContent = offre.titre;
    document.getElementById("modal-entreprise").textContent = offre.entreprise || "Non précisé";
    document.getElementById("modal-entreprise-2").textContent = offre.entreprise || "Non précisé";
    document.getElementById("modal-date").textContent = offre.date_publiee || "Non précisée";
    document.getElementById("modal-desc").textContent = offre.description || "";
    document.getElementById("modal-link").href = offre.lien;

    const nomEntreprise = (offre.entreprise || "").trim();
    const btnLinkedIn = document.getElementById("modal-linkedin");

    if (nomEntreprise && nomEntreprise !== "Non précisé") {{
      btnLinkedIn.href = "https://www.linkedin.com/search/results/people/?keywords=" + encodeURIComponent(nomEntreprise);
      btnLinkedIn.textContent = "Chercher les employés de " + nomEntreprise + " sur LinkedIn";
    }} else {{
      btnLinkedIn.href = "https://www.linkedin.com/search/results/all/?keywords=" + encodeURIComponent(offre.titre || "");
      btnLinkedIn.textContent = "Chercher cette offre sur LinkedIn";
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
  document.addEventListener("keydown", e => {{
    if (e.key === "Escape") closeModal();
  }});

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
    input.value = "";
    searchQuery = "";
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