#!/usr/bin/env python3
"""
update-events.py — Scrapes @bpm.traslados via Apify and regenera events.js

Uso:
    python3 scripts/update-events.py --token TU_APIFY_TOKEN

O guardá el token en variable de entorno:
    export APIFY_TOKEN=tu_token
    python3 scripts/update-events.py
"""

import argparse, json, os, re, sys, time, textwrap
import urllib.request, urllib.error
from datetime import datetime, date

# ── Config ─────────────────────────────────────────────────────────────
INSTAGRAM_USER = "bpm.traslados"
APIFY_ACTOR    = "apify~instagram-post-scraper"
WA_NUMBER      = "5493517606189"
EVENTS_JS_PATH = os.path.join(os.path.dirname(__file__), "..", "js", "events.js")

MONTHS_ES = {
    "enero":1,"febrero":2,"marzo":3,"abril":4,"mayo":5,"junio":6,
    "julio":7,"agosto":8,"septiembre":9,"octubre":10,"noviembre":11,"diciembre":12,
}

DAYS_ES = {
    "lunes":"Lun","martes":"Mar","miércoles":"Mié","miercoles":"Mié",
    "jueves":"Jue","viernes":"Vie","sábado":"Sáb","sabado":"Sáb","domingo":"Dom",
}

VENUES = [
    {"kw": ["forja"],                              "name": "Forja Centro de Eventos", "city": "Córdoba"},
    {"kw": ["fábrica","fabrica","la fabrica"],      "name": "La Fábrica",              "city": "La Calera"},
    {"kw": ["estación","estacion","la estacion"],   "name": "La Estación",             "city": "Malagueño"},
    {"kw": ["berta"],                              "name": "Berta",                   "city": "Alta Gracia"},
    {"kw": ["cosquín","cosquin","prospero molina"], "name": "Plaza Próspero Molina",   "city": "Cosquín"},
    {"kw": ["kempes"],                             "name": "Estadio Kempes",           "city": "Córdoba"},
    {"kw": ["atenas"],                             "name": "Estadio Atenas",           "city": "Córdoba"},
    {"kw": ["quality","espacio quality"],          "name": "Quality Espacio",          "city": "Córdoba"},
]

GENRE_KW = {
    "electronica": ["techno","house","electrónica","electronica","dj","b2b","electronic",
                    "trance","psytrance","minimal","progressive","deep","tech house"],
    "rock":        ["rock","metal","heavy","punk","alternativo","nacional"],
    "festival":    ["festival","cosquín rock","cosquin rock","lollapalooza","flow"],
}

ICONS = {"electronica":"🎛️","rock":"🤘","festival":"🎵"}
GENRE_LABELS = {"electronica":"Electrónica","rock":"Rock","festival":"Festival"}

# ── Apify ───────────────────────────────────────────────────────────────

def apify_post(url, token, payload):
    data = json.dumps(payload).encode()
    req  = urllib.request.Request(
        f"{url}?token={token}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read())

def apify_get(url, token):
    req = urllib.request.Request(f"{url}?token={token}&format=json&limit=200")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())

def fetch_posts(token):
    base = "https://api.apify.com/v2"
    print(f"⏳ Iniciando scrape de @{INSTAGRAM_USER} via Apify...")

    run = apify_post(
        f"{base}/acts/{APIFY_ACTOR}/runs",
        token,
        {"username": [INSTAGRAM_USER], "resultsLimit": 100, "dataDetailLevel": "detailedData"}
    )
    run_id    = run["data"]["id"]
    dataset_id = run["data"]["defaultDatasetId"]
    print(f"   Run iniciado: {run_id}")

    # Poll hasta SUCCEEDED
    for _ in range(60):
        status = apify_get(f"{base}/acts/{APIFY_ACTOR}/runs/{run_id}", token)
        s = status["data"]["status"]
        print(f"   Status: {s}", end="\r")
        if s == "SUCCEEDED":
            break
        if s in ("FAILED","ABORTED","TIMED-OUT"):
            sys.exit(f"\n❌ El run terminó con status: {s}")
        time.sleep(5)
    else:
        sys.exit("\n❌ Timeout esperando el run de Apify.")

    items = apify_get(f"{base}/datasets/{dataset_id}/items", token)
    print(f"\n✅ {len(items)} posts descargados.")
    return items

# ── Parsing ─────────────────────────────────────────────────────────────

def clean(text):
    return re.sub(r'\s+', ' ', text or "").strip()

def extract_date(caption):
    """Intenta extraer una fecha futura del caption. Retorna (date_obj, display_str, time_str) o None."""
    cap = caption.lower()
    today = date.today()

    # Patrón: "23 de agosto", "23 de agosto 2025"
    m = re.search(
        r'(\d{1,2})\s+de\s+(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)'
        r'(?:\s+(?:de\s+)?(\d{4}))?',
        cap
    )
    if m:
        day   = int(m.group(1))
        month = MONTHS_ES[m.group(2)]
        year  = int(m.group(3)) if m.group(3) else today.year
        try:
            d = date(year, month, day)
            if d < today:
                d = date(year + 1, month, day)
            # Display como "Sáb 23 Ago 2025"
            month_abbr = m.group(2)[:3].capitalize()
            display = f"{d.strftime('%a')} {day} {month_abbr} {d.year}"
            # Buscar hora
            th = re.search(r'(\d{1,2})[:\.](\d{2})\s*(?:hs|h)?', cap)
            t  = f"{th.group(1)}:{th.group(2)}" if th else "22:00"
            return d, display, t
        except ValueError:
            pass

    # Patrón: "23/08" o "23/08/2025"
    m2 = re.search(r'(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?', cap)
    if m2:
        day   = int(m2.group(1))
        month = int(m2.group(2))
        year  = int(m2.group(3)) if m2.group(3) else today.year
        if year < 100:
            year += 2000
        try:
            d = date(year, month, day)
            if d < today:
                return None
            display = d.strftime("%a %-d %b %Y").capitalize()
            th = re.search(r'(\d{1,2})[:\.](\d{2})\s*(?:hs|h)?', cap)
            t  = f"{th.group(1)}:{th.group(2)}" if th else "22:00"
            return d, display, t
        except ValueError:
            pass

    return None

def extract_venue(caption):
    cap = caption.lower()
    for v in VENUES:
        if any(k in cap for k in v["kw"]):
            return v["name"], v["city"]
    return None, None

def extract_genre(caption):
    cap = caption.lower()
    for genre, kws in GENRE_KW.items():
        if any(k in cap for k in kws):
            return genre
    return "electronica"  # default para BPM

def extract_artist(caption):
    """Extrae el nombre del artista de la primera línea no-emoji del caption."""
    lines = [l.strip() for l in caption.split("\n") if l.strip()]
    for line in lines[:4]:
        # Eliminar emojis y caracteres especiales para evaluar
        clean_line = re.sub(r'[^\w\s\-\.\|&áéíóúÁÉÍÓÚñÑ]', '', line).strip()
        # Ignorar líneas de logística
        skip = ["traslado","salida","regreso","reserva","cupos","lugares","punto","precio",
                "info","consulta","link","bio","whatsapp","contacto","combi","trafic"]
        if clean_line and not any(s in clean_line.lower() for s in skip) and len(clean_line) > 2:
            # Limpiar prefijos tipo "TRASLADO |", "🚌 |"
            clean_line = re.sub(r'^(traslado\s*[|\-]?\s*)', '', clean_line, flags=re.I).strip()
            if clean_line:
                return clean_line.title()
    return None

def badge_from_caption(caption):
    cap = caption.lower()
    if any(w in cap for w in ["agotado","sold out","sin lugares","no hay lugares"]):
        return "sold", "Agotado"
    if any(w in cap for w in ["últimos","ultimos","pocos lugares","quedan"]):
        return "few", "Últimos lugares"
    if any(w in cap for w in ["preventa","pre-venta","pre venta"]):
        return "pre", "Preventa"
    return "avail", "Disponible"

def parse_post(post):
    caption = post.get("caption") or ""
    if not caption:
        return None

    date_info = extract_date(caption)
    if not date_info:
        return None  # Sin fecha reconocible → skip

    d, display, t = date_info
    venue, city   = extract_venue(caption)
    genre         = extract_genre(caption)
    artist        = extract_artist(caption)
    badge, badge_label = badge_from_caption(caption)

    if not artist:
        return None  # No pudimos identificar el artista → skip

    return {
        "id":           post.get("id", ""),
        "title":        artist,
        "subtitle":     "",
        "genre":        genre,
        "genreLabel":   GENRE_LABELS[genre],
        "venue":        venue or "Por confirmar",
        "city":         city  or "Córdoba",
        "date":         d.isoformat(),
        "dateDisplay":  display,
        "time":         t,
        "price":        None,
        "badge":        badge,
        "badgeLabel":   badge_label,
        "icon":         ICONS[genre],
        "_caption_preview": caption[:120].replace("\n", " "),
    }

# ── Render events.js ────────────────────────────────────────────────────

def render_events_js(events):
    lines = ["const WA_NUMBER = '5493517606189';\n\nconst EVENTS = ["]
    for i, e in enumerate(events):
        comma = "," if i < len(events) - 1 else ""
        lines.append(f"""  {{
    id:          {json.dumps(e['id'])},
    title:       {json.dumps(e['title'])},
    subtitle:    {json.dumps(e['subtitle'])},
    genre:       {json.dumps(e['genre'])},
    genreLabel:  {json.dumps(e['genreLabel'])},
    venue:       {json.dumps(e['venue'])},
    city:        {json.dumps(e['city'])},
    date:        {json.dumps(e['date'])},
    dateDisplay: {json.dumps(e['dateDisplay'])},
    time:        {json.dumps(e['time'])},
    price:       null,
    badge:       {json.dumps(e['badge'])},
    badgeLabel:  {json.dumps(e['badgeLabel'])},
    icon:        {json.dumps(e['icon'])},
  }}{comma}""")
    lines.append("];\n")
    lines.append("function buildWhatsAppLink(event) {")
    lines.append("  const text = encodeURIComponent(")
    lines.append("    `Hola! Quiero reservar mi lugar para el traslado a ${event.title} — ${event.dateDisplay} — ${event.venue}, ${event.city}. ¿Tienen lugares disponibles?`")
    lines.append("  );")
    lines.append("  return `https://wa.me/${WA_NUMBER}?text=${text}`;")
    lines.append("}")
    return "\n".join(lines) + "\n"

# ── Main ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Actualiza events.js desde Instagram via Apify")
    parser.add_argument("--token", default=os.environ.get("APIFY_TOKEN"), help="Apify API token")
    parser.add_argument("--dry-run", action="store_true", help="Mostrar eventos sin escribir el archivo")
    args = parser.parse_args()

    if not args.token:
        sys.exit("❌ Necesitás un Apify token. Pasalo con --token o APIFY_TOKEN=xxx")

    posts  = fetch_posts(args.token)
    events = []
    skipped = 0

    for post in posts:
        parsed = parse_post(post)
        if parsed:
            events.append(parsed)
        else:
            skipped += 1

    # Ordenar por fecha
    events.sort(key=lambda e: e["date"])

    print(f"\n📋 Resultados:")
    print(f"   ✅ {len(events)} eventos detectados")
    print(f"   ⏭  {skipped} posts sin fecha reconocible (ignorados)\n")

    if not events:
        print("⚠️  No se encontraron eventos futuros. Revisá los posts de Instagram manualmente.")
        sys.exit(0)

    for e in events:
        print(f"   🎵 {e['title']:<30} {e['dateDisplay']:<22} {e['venue']}, {e['city']}")
        print(f"      Caption: {e['_caption_preview']}")
        print()

    if args.dry_run:
        print("(dry-run: no se escribió events.js)")
        return

    # Limpiar campo interno antes de escribir
    for e in events:
        e.pop("_caption_preview", None)

    js_content = render_events_js(events)
    path = os.path.abspath(EVENTS_JS_PATH)
    with open(path, "w", encoding="utf-8") as f:
        f.write(js_content)

    print(f"✅ events.js actualizado con {len(events)} eventos → {path}")
    print(f"\nPróximo paso:")
    print(f"  cd ~/Downloads/bpm-traslados-web && git add js/events.js && git commit -m 'chore: update events from instagram' && git push")

if __name__ == "__main__":
    main()
