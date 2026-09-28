#!/usr/bin/env python3
"""
Immersieve Kunst Agenda — Airtable → events.json
-------------------------------------------------
Leest de events uit Airtable en schrijft events.json in het formaat
dat de website verwacht. De festival-banner (NFF-special) wordt NIET
aangeraakt: die staat apart in events.json en blijft behouden.

Gebruik lokaal (om te testen):
    export AIRTABLE_TOKEN="patXXXX..."      # jouw personal access token
    python3 sync-events.py

Op GitHub draait dit automatisch via de Action; daar komt de token
uit de repo-secrets.
"""

import os
import sys
import json
import urllib.request
import urllib.error

# ── Vaste instellingen (jouw base en tabel) ──
BASE_ID  = "apprvpBxNAZ7h01n3"
TABLE_ID = "tblgB5ck9uqPozbh5"
OUTPUT   = "events.json"

# ── Type-mapping: Airtable-label → nette naam op de site ──
# Alles links wordt (case-ongevoelig) omgezet naar de waarde rechts.
# Labels die je in Airtable exact zo gebruikt als de site ze kent,
# hoef je hier niet te noemen.
TYPE_MAP = {
    "xr (vr, ar, mr)": "XR",
    "xr": "XR",
    "exhibition": "Tentoonstelling",
    "tentoonstelling": "Tentoonstelling",
    "immersive installation": "Immersieve installaties",
    "immersive installations": "Immersieve installaties",
    "immersieve installaties": "Immersieve installaties",
    "installation": "Immersieve installaties",
    "performative": "Performatief",
    "perfomative": "Performatief",
    "performatief": "Performatief",
    "audio driven immersion": "Audio driven immersion",
    "digital art": "Digitale kunst",
    "digitale kunst": "Digitale kunst",
    "immersive theatre": "Immersief theater",
    "immersief theater": "Immersief theater",
    "music": "Muziek",
    "muziek": "Muziek",
    "sensory": "Zintuiglijk",
    "zintuiglijk": "Zintuiglijk",
    "generative": "Generatief",
    "generatief": "Generatief",
    "interactive": "Interactief",
    "interactief": "Interactief",
    "spatial": "Spatial",
    "media art history": "Media Art History",
    "ai-driven": "AI-driven",
    "in nature": "In de natuur",
    "in de natuur": "In de natuur",
    "new venue": "New venue",
    "planetarium": "Planetarium",
    "dome concert": "Dome concert",
    "opera": "Opera",
    "participatory": "Participatief",
    "participatief": "Participatief",
    "intimate": "Intiem",
    "intiem": "Intiem",
}


def map_type(label):
    """Zet één Airtable-type-label om naar de nette naam."""
    schoon = (label or "").strip()
    return TYPE_MAP.get(schoon.lower(), schoon)  # onbekend? laat staan zoals ingevuld


def iso_datum(waarde):
    """
    Airtable levert datums als 'YYYY-MM-DD' via de API (ongeacht hoe ze
    in de interface getoond worden). We geven die onveranderd terug.
    Leeg veld → None.
    """
    if not waarde:
        return None
    return waarde[:10]  # kap een eventueel tijdstip eraf


def haal_records():
    """Haalt alle records op uit Airtable (met paginering)."""
    token = os.environ.get("AIRTABLE_TOKEN")
    if not token:
        sys.exit("FOUT: zet eerst de omgevingsvariabele AIRTABLE_TOKEN "
                 "(export AIRTABLE_TOKEN=\"patXXXX...\")")

    records = []
    offset = None
    while True:
        url = f"https://api.airtable.com/v0/{BASE_ID}/{TABLE_ID}?pageSize=100"
        if offset:
            url += f"&offset={offset}"
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
        try:
            with urllib.request.urlopen(req) as r:
                data = json.load(r)
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "ignore")
            sys.exit(f"FOUT bij Airtable ({e.code}): {body}")
        records.extend(data.get("records", []))
        offset = data.get("offset")
        if not offset:
            break
    return records


def bouw_event(fields):
    """Zet één Airtable-record om naar een event-dict voor events.json."""
    def veld(naam):
        v = fields.get(naam)
        # AI-velden geeft Airtable terug als {state, value, isStale} — pak de tekst eruit
        if isinstance(v, dict) and "value" in v:
            v = v.get("value")
        # Multiple/collaborator-velden kunnen een lijst zijn — voeg samen
        if isinstance(v, list):
            v = ", ".join(str(x) for x in v if x)
        if isinstance(v, str):
            v = v.strip()
        return v or None

    naam   = veld("Naam event")
    start  = iso_datum(fields.get("Start datum"))
    eind   = iso_datum(fields.get("Eind datum")) or start  # geen einddatum = eendaags

    if not naam or not start:
        return None  # onvolledige rij: overslaan

    # Types (multiple select → lijst)
    ruwe_types = fields.get("Type") or []
    if isinstance(ruwe_types, str):
        ruwe_types = [ruwe_types]
    types = []
    for t in ruwe_types:
        m = map_type(t)
        if m and m not in types:
            types.append(m)

    # Foto: bestandsnaam → /images/…
    foto_naam = veld("Foto naam")
    foto = f"/images/{foto_naam}" if foto_naam else None

    return {
        "naam": {"nl": naam, "en": naam},
        "start": start,
        "eind": eind,
        "maker": veld("Maker / Kunstenaar"),
        "duur": veld("Duur"),
        "handig": veld("Handig te weten"),
        "logline": {
            "nl": veld("Logline NL") or "",
            "en": veld("Logline EN") or veld("Logline NL") or "",
        },
        "beschrijving": {
            "nl": veld("Beschrijving NL") or "",
            "en": veld("Beschrijving EN") or veld("Beschrijving NL") or "",
        },
        "stad": veld("Stad"),
        "locatie": veld("Location"),
        "types": types,
        "foto": foto,
        "link": veld("Koop hier een kaartje"),
        "uitgelicht": bool(fields.get("Uitgelicht")),
        "verseTip": bool(fields.get("Verse tip")),
    }


def main():
    records = haal_records()
    events = []
    overgeslagen = []
    for rec in records:
        ev = bouw_event(rec.get("fields", {}))
        if ev:
            events.append(ev)
        else:
            naam = rec.get("fields", {}).get("Naam event", "(zonder naam)")
            overgeslagen.append(naam)

    # Sorteer op einddatum, dan startdatum (net als de site verwacht)
    events.sort(key=lambda e: (e["eind"], e["start"]))

    # ── Festival-special (NFF) behouden uit de bestaande events.json ──
    # Die beheer je handmatig; het script raakt 'm niet aan.
    behouden_specials = {}
    if os.path.exists(OUTPUT):
        try:
            oud = json.load(open(OUTPUT, encoding="utf-8"))
            for e in oud.get("events", []):
                if e.get("special"):
                    behouden_specials[e["naam"]["nl"]] = e["special"]
        except Exception:
            pass

    aantal_specials = 0
    for e in events:
        sp = behouden_specials.get(e["naam"]["nl"])
        if sp:
            e["special"] = sp
            aantal_specials += 1

    uit = {"events": events, "studentenEvents": []}
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(uit, f, ensure_ascii=False, indent=2)

    # ── Rapport ──
    print(f"✓ {len(events)} events geschreven naar {OUTPUT}")
    if aantal_specials:
        print(f"  ({aantal_specials} festival-special(s) behouden uit bestaande {OUTPUT})")
    uitgelicht = [e["naam"]["nl"] for e in events if e["uitgelicht"]]
    verse = [e["naam"]["nl"] for e in events if e["verseTip"]]
    if uitgelicht:
        print(f"  ★ Uitgelicht: {', '.join(uitgelicht)}")
    if verse:
        print(f"  ✦ Verse tip: {', '.join(verse)}")
    zonder_foto = [e["naam"]["nl"] for e in events if not e["foto"]]
    if zonder_foto:
        print(f"  ⚠ Zonder foto: {', '.join(zonder_foto)}")
    if overgeslagen:
        print(f"  ⚠ Overgeslagen (geen naam of startdatum): {', '.join(str(o) for o in overgeslagen)}")


if __name__ == "__main__":
    main()
