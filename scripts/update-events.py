#!/usr/bin/env python3
"""
update-events.py — Scrapes @bpm.traslados via Apify y analiza cada flyer
                   con Claude vision para extraer artista/fecha/venue/género.

Uso:
    # Activar el virtualenv primero:
    source .venv/bin/activate

    python3 scripts/update-events.py --apify-token TU_APIFY_TOKEN --claude-token TU_ANTHROPIC_KEY

O con variables de entorno:
    export APIFY_TOKEN=xxx
    export ANTHROPIC_API_KEY=xxx
    python3 scripts/update-events.py
"""

import argparse, json, os, re, sys, time, base64
import urllib.request, urllib.error
from datetime import datetime, date

# ── Config ──────────────────────────────────────────────────────────────
INSTAGRAM_USER = "bpm.traslados"
APIFY_ACTOR    = "apify~instagram-post-scraper"
WA_NUMBER      = "5493517606189"
CLAUDE_MODEL   = "claude-haiku-4-5-20251001"
EVENTS_JS_PATH = os.path.join(os.path.dirname(__file__), "..", "js", "events.js")

GENRE_LABELS = {"electronica": "Electrónica", "rock": "Rock", "festival": "Festival"}
ICONS        = {"electronica": "🎛️", "rock": "🤘", "festival": "🎵"}

CLAUDE_PROMPT = """\
Sos un asistente que extrae datos de flyers de eventos musicales.

Esta imagen es el flyer de un traslado en combi a un recital/festival organizado por \
"BPM Traslados" en Córdoba, Argentina.

Extraé la siguiente información y respondé ÚNICAMENTE con un objeto JSON válido, \
sin texto adicional, sin markdown, sin explicaciones:

{
  "artist": "nombre del artista o evento principal",
  "venue": "nombre del lugar/venue donde se hace el evento",
  "city": "ciudad donde es el evento",
  "date": "DD/MM/YYYY (si no hay año, asumí el más próximo futuro)",
  "time": "HH:MM (hora de salida o del evento, formato 24h)",
  "genre": "electronica | rock | festival",
  "badge": "avail | few | sold | pre"
}

Reglas:
- genre "electronica": techno, house, trance, DJ sets, música electrónica
- genre "rock": rock, metal, punk, bandas en vivo
- genre "festival": festivales multigenero (Cosquín Rock, Lollapalooza, etc.)
- badge "sold": agotado / sold out
- badge "few": últimos lugares / pocos cupos
- badge "pre": preventa
- badge "avail": disponible (default si no hay info)
- Si un campo no es visible en la imagen, usá null.
- Respondé SOLO el JSON, nada más."""


# ── Helpers HTTP ─────────────────────────────────────────────────────────

def http_post(url, payload, headers=None):
    data = json.dumps(payload).encode()
    h    = {"Content-Type": "application/json"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, data=data, headers=h, method="POST")
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read())

def http_get(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()

def http_get_json(url):
    return json.loads(http_get(url))


# ── Apify ────────────────────────────────────────────────────────────────

def fetch_posts(token):
    base = "https://api.apify.com/v2"
    print(f"⏳ Iniciando scrape de @{INSTAGRAM_USER} via Apify...")

    run = http_post(
        f"{base}/acts/{APIFY_ACTOR}/runs?token={token}",
        {"username": [INSTAGRAM_USER], "resultsLimit": 50, "dataDetailLevel": "detailedData"}
    )
    run_id     = run["data"]["id"]
    dataset_id = run["data"]["defaultDatasetId"]
    print(f"   Run iniciado: {run_id}")

    for attempt in range(72):  # máx 6 min
        status = http_get_json(f"{base}/acts/{APIFY_ACTOR}/runs/{run_id}?token={token}")
        s = status["data"]["status"]
        print(f"   Status: {s}   ({attempt*5}s)", end="\r")
        if s == "SUCCEEDED":
            break
        if s in ("FAILED", "ABORTED", "TIMED-OUT"):
            sys.exit(f"\n❌ Run terminó con status: {s}")
        time.sleep(5)
    else:
        sys.exit("\n❌ Timeout esperando el run de Apify.")

    items = http_get_json(f"{base}/datasets/{dataset_id}/items?token={token}&format=json&limit=200")
    print(f"\n✅ {len(items)} posts descargados de Instagram.")
    return items


# ── Claude Vision ─────────────────────────────────────────────────────────

def image_to_base64(url):
    """Descarga la imagen y la convierte a base64."""
    try:
        data = http_get(url, headers={"User-Agent": "Mozilla/5.0"})
        return base64.standard_b64encode(data).decode("utf-8")
    except Exception as e:
        print(f"      ⚠️  No se pudo descargar imagen: {e}")
        return None

def analyze_flyer(image_url, claude_key):
    """Manda la imagen a Claude Haiku y devuelve el JSON con los datos del evento."""
    img_b64 = image_to_base64(image_url)
    if not img_b64:
        return None

    # Detectar media type por extensión / magic bytes
    media_type = "image/jpeg"
    if image_url.lower().endswith(".png"):
        media_type = "image/png"
    elif image_url.lower().endswith(".webp"):
        media_type = "image/webp"

    payload = {
        "model": CLAUDE_MODEL,
        "max_tokens": 300,
        "messages": [{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": img_b64,
                    }
                },
                {"type": "text", "text": CLAUDE_PROMPT}
            ]
        }]
    }

    try:
        resp = http_post(
            "https://api.anthropic.com/v1/messages",
            payload,
            headers={
                "x-api-key": claude_key,
                "anthropic-version": "2023-06-01",
            }
        )
        raw = resp["content"][0]["text"].strip()
        # Limpiar markdown si Claude lo incluye igual
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        return json.loads(raw)
    except Exception as e:
        print(f"      ⚠️  Error analizando imagen: {e}")
        return None


# ── Parseo de fecha ───────────────────────────────────────────────────────

def parse_date(raw):
    """Convierte 'DD/MM/YYYY' o 'DD/MM' a (date, display_str)."""
    if not raw:
        return None, None
    today = date.today()
    for fmt in ("%d/%m/%Y", "%d/%m/%y", "%d/%m"):
        try:
            d = datetime.strptime(raw.strip(), fmt).date()
            if fmt == "%d/%m":
                d = d.replace(year=today.year)
                if d < today:
                    d = d.replace(year=today.year + 1)
            if d < today:
                return None, None  # fecha pasada → skip
            abbr_months = ["","Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"]
            days_es = ["Lun","Mar","Mié","Jue","Vie","Sáb","Dom"]
            display = f"{days_es[d.weekday()]} {d.day} {abbr_months[d.month]} {d.year}"
            return d, display
        except ValueError:
            continue
    return None, None


# ── Render events.js ──────────────────────────────────────────────────────

def render_events_js(events):
    lines = ["const WA_NUMBER = '5493517606189';\n\nconst EVENTS = ["]
    for i, e in enumerate(events):
        comma = "," if i < len(events) - 1 else ""
        lines.append(f"""  {{
    id:          {json.dumps(str(i + 1))},
    title:       {json.dumps(e['title'])},
    subtitle:    "",
    genre:       {json.dumps(e['genre'])},
    genreLabel:  {json.dumps(GENRE_LABELS.get(e['genre'], 'Electrónica'))},
    venue:       {json.dumps(e['venue'] or 'Por confirmar')},
    city:        {json.dumps(e['city']  or 'Córdoba')},
    date:        {json.dumps(e['date'])},
    dateDisplay: {json.dumps(e['dateDisplay'])},
    time:        {json.dumps(e['time']  or '22:00')},
    price:       null,
    badge:       {json.dumps(e['badge'] or 'avail')},
    badgeLabel:  {json.dumps(e['badgeLabel'])},
    icon:        {json.dumps(ICONS.get(e['genre'], '🎵'))},
  }}{comma}""")
    lines.append("];\n")
    lines.append("function buildWhatsAppLink(event) {")
    lines.append("  const text = encodeURIComponent(")
    lines.append("    `Hola! Quiero reservar mi lugar para el traslado a ${event.title} — ${event.dateDisplay} — ${event.venue}, ${event.city}. ¿Tienen lugares disponibles?`")
    lines.append("  );")
    lines.append("  return `https://wa.me/${WA_NUMBER}?text=${text}`;")
    lines.append("}")
    return "\n".join(lines) + "\n"

BADGE_LABELS = {"avail": "Disponible", "few": "Últimos lugares", "sold": "Agotado", "pre": "Preventa"}

# ── Main ──────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apify-token",  default=os.environ.get("APIFY_TOKEN"))
    parser.add_argument("--claude-token", default=os.environ.get("ANTHROPIC_API_KEY"))
    parser.add_argument("--dry-run", action="store_true", help="No escribe events.js")
    args = parser.parse_args()

    if not args.apify_token:
        sys.exit("❌ Falta --apify-token o APIFY_TOKEN en env")
    if not args.claude_token:
        sys.exit("❌ Falta --claude-token o ANTHROPIC_API_KEY en env")

    posts = fetch_posts(args.apify_token)

    events  = []
    skipped = 0
    total   = len(posts)

    print(f"\n🔍 Analizando {total} flyers con Claude vision...\n")

    for idx, post in enumerate(posts, 1):
        image_url = post.get("displayUrl") or post.get("imageUrl")
        timestamp = post.get("timestamp", "")[:10]
        caption_preview = (post.get("caption") or "")[:60].replace("\n", " ")

        print(f"[{idx:>2}/{total}] {timestamp}  {caption_preview[:50]}")

        if not image_url:
            print("      ⏭  Sin imagen, skip.\n")
            skipped += 1
            continue

        data = analyze_flyer(image_url, args.claude_token)

        if not data or not data.get("artist") or not data.get("date"):
            print(f"      ⏭  No se pudo extraer info completa: {data}\n")
            skipped += 1
            continue

        d, display = parse_date(data.get("date"))
        if not d:
            print(f"      ⏭  Fecha pasada o no parseable ({data.get('date')}), skip.\n")
            skipped += 1
            continue

        genre = data.get("genre", "electronica")
        if genre not in GENRE_LABELS:
            genre = "electronica"

        badge = data.get("badge", "avail")
        if badge not in BADGE_LABELS:
            badge = "avail"

        event = {
            "title":      data["artist"],
            "genre":      genre,
            "venue":      data.get("venue"),
            "city":       data.get("city") or "Córdoba",
            "date":       d.isoformat(),
            "dateDisplay": display,
            "time":       data.get("time") or "22:00",
            "badge":      badge,
            "badgeLabel": BADGE_LABELS[badge],
        }

        events.append(event)
        print(f"      ✅ {event['title']:<28} {display}  {event['venue']}, {event['city']}\n")

    events.sort(key=lambda e: e["date"])

    print(f"\n{'─'*55}")
    print(f"  ✅ {len(events)} eventos detectados")
    print(f"  ⏭  {skipped} posts ignorados (sin fecha futura o sin imagen)")
    print(f"{'─'*55}\n")

    if not events:
        print("⚠️  Sin eventos futuros detectados. Revisá los posts manualmente.")
        sys.exit(0)

    if args.dry_run:
        print("(dry-run: events.js no fue modificado)")
        return

    path = os.path.abspath(EVENTS_JS_PATH)
    with open(path, "w", encoding="utf-8") as f:
        f.write(render_events_js(events))

    print(f"✅ events.js actualizado → {path}")
    print(f"\nPara publicar los cambios:\n")
    print(f"  cd ~/Downloads/bpm-traslados-web")
    print(f"  git add js/events.js")
    print(f"  git commit -m 'chore: update events from instagram'")
    print(f"  git push\n")

if __name__ == "__main__":
    main()
