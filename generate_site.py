"""
Génère une page HTML statique à partir du CSV d'offres.
À lancer après scrapping_hexagone.py (ou enchaîné dans le même job).
"""

import csv
import json
import html

CSV_PATH = "alternances_hexagone.csv"
OUTPUT_HTML = "index.html"

COULEUR_PRIMAIRE = "#223d7d"
COULEUR_ACCENT = "#ffcc38"


def charger_offres() -> list[dict]:
    offres = []
    try:
        with open(CSV_PATH, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                offres.append(row)
    except FileNotFoundError:
        print(f"{CSV_PATH} introuvable — lance d'abord le scraper.")
    return offres


def generer_html(offres: list[dict]) -> str:
    categories = sorted(set(o.get("categorie", "Autre") for o in offres))
    data_json = json.dumps(offres, ensure_ascii=False)

    tabs_html = "".join(
        f'<button class="tab" data-cat="{html.escape(cat)}">{html.escape(cat)}</button>'
        for cat in categories
    )

    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Alternances École Hexagone — Dev / Data / IA</title>
<style>
  :root {{
    --primaire: {COULEUR_PRIMAIRE};
    --accent: {COULEUR_ACCENT};
  }}

  * {{ box-sizing: border-box; }}

  body {{
    margin: 0;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: #f4f6fb;
    color: #1a1a1a;
  }}

  header {{
    background: var(--primaire);
    color: white;
    padding: 32px 24px;
    text-align: center;
  }}

  header h1 {{
    margin: 0 0 6px;
    font-size: 1.8rem;
    letter-spacing: -0.5px;
  }}

  header p {{
    margin: 0;
    opacity: 0.85;
    font-size: 0.95rem;
  }}

  .tabs {{
    display: flex;
    justify-content: center;
    gap: 8px;
    flex-wrap: wrap;
    padding: 20px 16px 0;
  }}

  .tab {{
    border: 2px solid var(--primaire);
    background: white;
    color: var(--primaire);
    padding: 8px 20px;
    border-radius: 999px;
    font-weight: 600;
    font-size: 0.9rem;
    cursor: pointer;
    transition: all 0.15s ease;
  }}

  .tab:hover {{
    background: #eef1fa;
  }}

  .tab.active {{
    background: var(--accent);
    border-color: var(--accent);
    color: var(--primaire);
  }}

  .count-badge {{
    text-align: center;
    color: #666;
    font-size: 0.85rem;
    margin: 12px 0 0;
  }}

  .grid {{
    max-width: 1000px;
    margin: 24px auto 60px;
    padding: 0 16px;
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 16px;
  }}

  .card {{
    background: white;
    border-radius: 14px;
    padding: 18px;
    box-shadow: 0 2px 10px rgba(34, 61, 125, 0.08);
    cursor: pointer;
    border: 1px solid #e8ebf3;
    transition: transform 0.12s ease, box-shadow 0.12s ease;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }}

  .card:hover {{
    transform: translateY(-3px);
    box-shadow: 0 6px 18px rgba(34, 61, 125, 0.15);
  }}

  .card-cat {{
    display: inline-block;
    align-self: flex-start;
    background: var(--primaire);
    color: white;
    font-size: 0.7rem;
    font-weight: 700;
    padding: 3px 10px;
    border-radius: 999px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }}

  .card h3 {{
    margin: 0;
    font-size: 1.05rem;
    color: var(--primaire);
    line-height: 1.3;
  }}

  .card .entreprise {{
    font-weight: 600;
    color: #333;
    font-size: 0.9rem;
  }}

  .card .date {{
    color: #888;
    font-size: 0.8rem;
  }}

  .empty {{
    text-align: center;
    color: #999;
    padding: 60px 20px;
    grid-column: 1 / -1;
  }}

  /* Modal */
  .overlay {{
    display: none;
    position: fixed;
    inset: 0;
    background: rgba(20, 25, 40, 0.55);
    z-index: 100;
    align-items: flex-start;
    justify-content: center;
    padding: 40px 16px;
    overflow-y: auto;
  }}

  .overlay.open {{
    display: flex;
  }}

  .modal {{
    background: white;
    border-radius: 16px;
    max-width: 640px;
    width: 100%;
    overflow: hidden;
    box-shadow: 0 20px 60px rgba(0,0,0,0.3);
  }}

  .modal-header {{
    background: var(--primaire);
    color: white;
    padding: 28px 28px 20px;
    position: relative;
  }}

  .modal-header .card-cat {{
    background: var(--accent);
    color: var(--primaire);
  }}

  .modal-header h2 {{
    margin: 12px 0 4px;
    font-size: 1.4rem;
    line-height: 1.35;
  }}

  .modal-header .entreprise {{
    color: #dfe6f7;
    font-size: 1rem;
    font-weight: 600;
  }}

  .close-btn {{
    position: absolute;
    top: 18px;
    right: 20px;
    background: none;
    border: none;
    color: white;
    font-size: 1.4rem;
    cursor: pointer;
    line-height: 1;
    opacity: 0.8;
  }}

  .close-btn:hover {{ opacity: 1; }}

  .modal-body {{
    padding: 24px 28px 28px;
  }}

  .modal-meta {{
    display: flex;
    gap: 20px;
    margin-bottom: 18px;
    font-size: 0.85rem;
    color: #666;
  }}

  .modal-meta strong {{
    color: #222;
    display: block;
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.4px;
    margin-bottom: 2px;
  }}

  .modal-desc {{
    font-size: 0.95rem;
    line-height: 1.6;
    color: #333;
    white-space: pre-wrap;
    margin-bottom: 26px;
  }}

  .apply-btn {{
    display: inline-block;
    background: var(--accent);
    color: var(--primaire);
    font-weight: 700;
    text-decoration: none;
    padding: 14px 28px;
    border-radius: 10px;
    font-size: 1rem;
    text-align: center;
    width: 100%;
    transition: filter 0.15s ease;
  }}

  .apply-btn:hover {{
    filter: brightness(0.95);
  }}
</style>
</head>
<body>

<header>
  <h1>Alternances École Hexagone</h1>
  <p>Développement · Data · Intelligence Artificielle</p>
</header>

<div class="tabs" id="tabs">
  <button class="tab active" data-cat="Toutes">Toutes</button>
  {tabs_html}
</div>

<p class="count-badge" id="count-badge"></p>

<div class="grid" id="grid"></div>

<div class="overlay" id="overlay">
  <div class="modal">
    <div class="modal-header">
      <button class="close-btn" id="close-btn">&times;</button>
      <span class="card-cat" id="modal-cat"></span>
      <h2 id="modal-title"></h2>
      <div class="entreprise" id="modal-entreprise"></div>
    </div>
    <div class="modal-body">
      <div class="modal-meta">
        <div>
          <strong>Publié</strong>
          <span id="modal-date"></span>
        </div>
      </div>
      <div class="modal-desc" id="modal-desc"></div>
      <a href="#" target="_blank" rel="noopener" class="apply-btn" id="modal-link">Voir l'annonce et postuler →</a>
    </div>
  </div>
</div>

<script>
  const OFFRES = {data_json};

  let activeCat = "Toutes";

  function render() {{
    const grid = document.getElementById("grid");
    const badge = document.getElementById("count-badge");
    const filtrees = activeCat === "Toutes"
      ? OFFRES
      : OFFRES.filter(o => o.categorie === activeCat);

    badge.textContent = filtrees.length + " offre" + (filtrees.length > 1 ? "s" : "");

    if (filtrees.length === 0) {{
      grid.innerHTML = '<div class="empty">Aucune offre pour le moment dans cette catégorie.</div>';
      return;
    }}

    grid.innerHTML = filtrees.map((o, i) => `
      <div class="card" data-index="${{OFFRES.indexOf(o)}}">
        <span class="card-cat">${{o.categorie || "Autre"}}</span>
        <h3>${{o.titre}}</h3>
        <div class="entreprise">${{o.entreprise || "Non précisé"}}</div>
        <div class="date">${{o.date_publiee || ""}}</div>
      </div>
    `).join("");

    document.querySelectorAll(".card").forEach(card => {{
      card.addEventListener("click", () => openModal(OFFRES[card.dataset.index]));
    }});
  }}

  function openModal(offre) {{
    document.getElementById("modal-cat").textContent = offre.categorie || "Autre";
    document.getElementById("modal-title").textContent = offre.titre;
    document.getElementById("modal-entreprise").textContent = offre.entreprise || "Non précisé";
    document.getElementById("modal-date").textContent = offre.date_publiee || "Non précisée";
    document.getElementById("modal-desc").textContent = offre.description || "";
    document.getElementById("modal-link").href = offre.lien;
    document.getElementById("overlay").classList.add("open");
  }}

  document.getElementById("close-btn").addEventListener("click", () => {{
    document.getElementById("overlay").classList.remove("open");
  }});

  document.getElementById("overlay").addEventListener("click", (e) => {{
    if (e.target.id === "overlay") {{
      document.getElementById("overlay").classList.remove("open");
    }}
  }});

  document.getElementById("tabs").addEventListener("click", (e) => {{
    if (!e.target.classList.contains("tab")) return;
    document.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
    e.target.classList.add("active");
    activeCat = e.target.dataset.cat;
    render();
  }});

  render();
</script>

</body>
</html>
"""


def main():
    offres = charger_offres()
    html_content = generer_html(offres)

    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"Page générée -> {OUTPUT_HTML} ({len(offres)} offres)")


if __name__ == "__main__":
    main()