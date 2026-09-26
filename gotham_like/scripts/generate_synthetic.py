#!/usr/bin/env python3
"""Generate the SYNTHETIC / DEMONSTRATION DATA set.

Everything here is fabricated from a fixed random seed. Names are built from
invented syllables, e-mails use reserved example domains, phone numbers use the
fictional 555-01xx range and IP addresses come from RFC 5737 documentation ranges
or private ranges. No real personal information is used.

Planted scenarios (for the demonstration investigation) are described in
docs/DEMO_INVESTIGATION.md.

Usage:  python scripts/generate_synthetic.py [--out data/synthetic] [--seed 42]
"""

from __future__ import annotations

import argparse
import csv
import json
import random
from datetime import UTC, datetime, timedelta
from pathlib import Path

LABEL = "SYNTHETIC / DEMONSTRATION DATA"
START = datetime(2026, 1, 1, tzinfo=UTC)
END = datetime(2026, 6, 30, tzinfo=UTC)

SYL_A = ["ka", "lo", "mi", "ra", "ve", "to", "su", "an", "el", "da", "ni", "or", "be", "zu", "fe", "ti", "ma", "qu", "si", "ho"]
SYL_B = ["ren", "lin", "vas", "dor", "mek", "sil", "tar", "vin", "sok", "lem", "rin", "zal", "pon", "kes", "mar", "tul", "gan", "del"]
ORG_A = ["North", "Blue", "Iron", "Silver", "Quartz", "Cedar", "Harbor", "Summit", "Delta", "Amber", "Crescent", "Orbit", "Granite", "Willow"]
ORG_B = ["wind", "field", "gate", "stone", "line", "bridge", "point", "ridge", "brook", "haven", "vale", "crest"]
ORG_C = ["Trading", "Logistics", "Holdings", "Systems", "Foods", "Metals", "Analytics", "Freight", "Components", "Textiles", "Pharma", "Energy"]
ORG_SFX = ["Ltd", "LLC", "GmbH", "S.A.", "Inc", "Pte Ltd", "B.V."]
JURIS = ["Aldoria", "Brevia", "Castellan Isles", "Dunmark", "Estovia", "Farland"]  # fictional jurisdictions
STREETS = ["Harbor", "Mill", "Station", "Cedar", "Lantern", "Quarry", "Orchard", "Beacon", "Canal", "Foundry"]
STREET_T = ["Street", "Road", "Avenue", "Lane", "Boulevard"]
# fictional city names placed at arbitrary coordinates
CITIES = [
    ("Port Veltra", 51.45, 3.60), ("Marisk", 48.20, 16.40), ("Oldhaven", 53.55, 9.95), ("Kestrel Bay", 1.29, 103.85),
    ("Duskmoor", 40.42, -3.70), ("Sarnath Quay", 25.20, 55.27), ("Brightwater", 41.88, -87.63), ("Lumen City", 35.68, 139.69),
]
PRODUCTS = ["Lithium cells (synthetic)", "Industrial valves (synthetic)", "Cotton textiles (synthetic)", "Solar inverters (synthetic)"]


def name(rng: random.Random) -> str:
    first = (rng.choice(SYL_A) + rng.choice(SYL_B)).capitalize()
    last = (rng.choice(SYL_A) + rng.choice(SYL_A) + rng.choice(SYL_B)).capitalize()
    return f"{first} {last}"


def org_name(rng: random.Random) -> str:
    return f"{rng.choice(ORG_A)}{rng.choice(ORG_B)} {rng.choice(ORG_C)} {rng.choice(ORG_SFX)}"


def ts(rng: random.Random, start: datetime = START, end: datetime = END) -> datetime:
    return start + timedelta(seconds=rng.randint(0, int((end - start).total_seconds())))


def iso(d: datetime) -> str:
    return d.strftime("%Y-%m-%dT%H:%M:%SZ")


def jitter(rng: random.Random, lat: float, lon: float, km: float) -> tuple[float, float]:
    return round(lat + rng.uniform(-km, km) / 111.0, 6), round(lon + rng.uniform(-km, km) / 111.0, 6)


def typo(rng: random.Random, s: str) -> str:
    if len(s) < 4:
        return s
    i = rng.randint(1, len(s) - 2)
    return s[:i] + s[i + 1] + s[i] + s[i + 2 :]


def generate(out: Path, seed: int = 42) -> dict[str, int]:
    rng = random.Random(seed)
    out.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}

    # ---------------- locations (500) ----------------
    categories = ["retail", "atm", "office", "residential", "port", "warehouse", "cafe", "hotel", "transit"]
    locations = []
    for i in range(500):
        city, clat, clon = CITIES[i % len(CITIES)]
        lat, lon = jitter(rng, clat, clon, 8)
        cat = "port" if i % 50 == 0 else rng.choice(categories)
        locations.append({"location_id": f"LOC-{i:04d}", "name": f"{rng.choice(STREETS)} {cat.title()} {i}", "city": city,
                          "country": JURIS[i % len(JURIS)], "lat": lat, "lon": lon, "category": cat})
    # planted: Harbor Plaza in Port Veltra (geo-temporal scenario)
    locations[1] = {"location_id": "LOC-0001", "name": "Harbor Plaza", "city": "Port Veltra", "country": "Aldoria",
                    "lat": 51.4500, "lon": 3.6000, "category": "retail"}
    ports = [l for l in locations if l["category"] == "port"]
    loc_by_city: dict[str, list[dict]] = {}
    for l in locations:
        loc_by_city.setdefault(l["city"], []).append(l)
    with (out / "locations.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(locations[0]))
        w.writeheader()
        w.writerows(locations)
    counts["locations"] = len(locations)

    # ---------------- persons (1000, CRM) + duplicates (KYC) ----------------
    persons = []
    for i in range(1000):
        nm = name(rng)
        first, last = nm.lower().split()
        city = CITIES[i % len(CITIES)][0]
        persons.append({
            "person_id": f"P-{i:05d}", "full_name": nm, "email": f"{first}.{last}{i}@example.com",
            "phone": f"+1-202-555-{(100 + i) % 10000:04d}", "dob": f"{rng.randint(1950, 2003)}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}",
            "address": f"{rng.randint(1, 250)} {rng.choice(STREETS)} {rng.choice(STREET_T)}, {city}",
            "nationality": rng.choice(JURIS), "occupation": rng.choice(["engineer", "trader", "teacher", "driver", "clerk", "consultant", "nurse", "analyst"]),
            "city": city, "data_label": LABEL,
        })
    with (out / "persons_crm.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(persons[0]))
        w.writeheader()
        w.writerows(persons)
    counts["persons"] = len(persons)

    # KYC source: 60 records describing CRM persons with variations (true duplicates) and
    # 10 look-alikes (same-ish name, different DOB/email) that must NOT be auto-merged.
    kyc = []
    for j, p in enumerate(rng.sample(persons, 60)):
        first, last = p["full_name"].split()
        variant = j % 4
        rec = {"kyc_id": f"KYC-{j:04d}", "name": p["full_name"], "email": p["email"], "phone": p["phone"], "date_of_birth": p["dob"],
               "address": p["address"], "data_label": LABEL}
        if variant == 0:
            rec["name"] = f"{typo(rng, first)} {last}"; rec["email"] = p["email"].upper()
        elif variant == 1:
            rec["name"] = f"{last}, {first}".replace(",", ""); rec["phone"] = p["phone"].replace("-", " ").replace("+1 ", "(").replace(" 555", ") 555")
        elif variant == 2:
            rec["name"] = f"Dr {first} {last}"; rec["address"] = rec["address"].replace("Street", "St").replace("Road", "Rd")
        else:
            rec["email"] = ""; rec["name"] = f"{first} {typo(rng, last)}"
        kyc.append(rec)
    for j, p in enumerate(rng.sample(persons, 10)):
        kyc.append({"kyc_id": f"KYC-L{j:03d}", "name": p["full_name"], "email": f"other{j}@example.org", "phone": f"+1-303-555-{j:04d}",
                    "date_of_birth": f"{int(p['dob'][:4]) - 7}-01-15", "address": f"{j + 5} Lantern Lane, Marisk", "data_label": LABEL})
    with (out / "persons_kyc.jsonl").open("w") as fh:
        for r in kyc:
            fh.write(json.dumps(r) + "\n")
    counts["kyc_records"] = len(kyc)

    # ---------------- organizations (200) ----------------
    orgs = []
    for i in range(200):
        orgs.append({"org_id": f"ORG-{i:04d}", "name": org_name(rng), "registration_number": f"REG{rng.randint(10**6, 10**7 - 1)}",
                     "jurisdiction": rng.choice(JURIS), "industry": rng.choice(ORG_C).lower(),
                     "address": f"{rng.randint(1, 99)} {rng.choice(STREETS)} Boulevard, {rng.choice(CITIES)[0]}", "data_label": LABEL})
    orgs[0].update(name="Northwind Quartz Trading Ltd", jurisdiction="Castellan Isles", industry="trading")   # merchant in ring
    orgs[1].update(name="Amberline Holdings S.A.", jurisdiction="Castellan Isles", industry="holdings")       # AML layer 1
    orgs[2].update(name="Crescentvale Freight B.V.", jurisdiction="Farland", industry="freight")              # AML layer 2
    orgs[3].update(name="Granitegate Components GmbH", jurisdiction="Dunmark", industry="components")        # supplier
    orgs[4].update(name="Willowhaven Energy Inc", jurisdiction="Brevia", industry="energy")                   # customer
    orgs[5].update(name="Orbitpoint Logistics Pte Ltd", jurisdiction="Estovia", industry="logistics")         # warehouse operator
    with (out / "organizations.json").open("w") as fh:
        json.dump({"data_label": LABEL, "organizations": orgs}, fh, indent=1)
    counts["organizations"] = len(orgs)

    employment = []
    for p in rng.sample(persons, 700):
        employment.append({"person_id": p["person_id"], "org_id": rng.choice(orgs)["org_id"], "since": iso(ts(rng, datetime(2018, 1, 1, tzinfo=UTC), START)),
                           "role_title": rng.choice(["staff", "manager", "director", "contractor"])})
    with (out / "employment.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(employment[0]))
        w.writeheader()
        w.writerows(employment)

    # beneficial ownership / control (AML)
    controls = [
        {"controller_type": "Person", "controller_id": "P-00007", "controlled_id": "ORG-0001", "share_pct": 85, "since": "2025-11-02T00:00:00Z"},
        {"controller_type": "Organization", "controller_id": "ORG-0001", "controlled_id": "ORG-0002", "share_pct": 100, "since": "2025-12-10T00:00:00Z"},
        {"controller_type": "Organization", "controller_id": "ORG-0002", "controlled_id": "ORG-0000", "share_pct": 60, "since": "2026-01-05T00:00:00Z"},
    ]
    for o in orgs[6:60]:
        controls.append({"controller_type": "Person", "controller_id": rng.choice(persons)["person_id"], "controlled_id": o["org_id"],
                         "share_pct": rng.choice([25, 33, 51, 75, 100]), "since": iso(ts(rng, datetime(2015, 1, 1, tzinfo=UTC), START))})
    with (out / "controls.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(controls[0]))
        w.writeheader()
        w.writerows(controls)

    # ---------------- accounts (2000) ----------------
    accounts = []
    for i in range(2000):
        if i < 1700:
            owner_type, owner = "Person", persons[i % 1000]["person_id"]
        else:
            owner_type, owner = "Organization", orgs[i % 200]["org_id"]
        accounts.append({"account_id": f"ACC-{i:07d}", "account_number": f"{rng.randint(10**9, 10**10 - 1)}",
                         "owner_type": owner_type, "owner_id": owner, "account_type": rng.choice(["checking", "savings", "card", "wallet"]),
                         "currency": rng.choice(["EUR", "USD", "SGD"]), "opened_at": iso(ts(rng, datetime(2020, 1, 1, tzinfo=UTC), START)),
                         "status": "active", "data_label": LABEL})
    merchant = accounts[1700 + 0]  # owned by ORG-1700%200 = ORG-0100 -> reassign to ORG-0000
    merchant.update(account_id="ACC-9000001", owner_id="ORG-0000", account_type="merchant")
    aml_acc = accounts[1701]
    aml_acc.update(account_id="ACC-9000002", owner_id="ORG-0002", account_type="checking")
    with (out / "accounts.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(accounts[0]))
        w.writeheader()
        w.writerows(accounts)
    counts["accounts"] = len(accounts)

    # ---------------- devices (1000) + usage ----------------
    devices = []
    for i in range(999):
        devices.append({"device_id": f"DV-{i:05d}", "device_type": rng.choice(["mobile", "laptop", "desktop", "tablet"]),
                        "os": rng.choice(["AndroidX", "iOSX", "WinX", "LinX"]), "fingerprint": f"fp{rng.getrandbits(48):012x}", "data_label": LABEL})
    devices.append({"device_id": "DV-7F3A-SHARED", "device_type": "mobile", "os": "AndroidX", "fingerprint": "fp7f3a0000shared", "data_label": LABEL})
    with (out / "devices.jsonl").open("w") as fh:
        for d in devices:
            fh.write(json.dumps(d) + "\n")
    counts["devices"] = len(devices)

    usage = []
    acct_devices: dict[str, list[str]] = {}
    home_ip = {a["account_id"]: f"10.{rng.randint(0, 255)}.{rng.randint(0, 255)}.{rng.randint(1, 254)}" for a in accounts}
    # devices belong to people: all accounts of a person share that person's device(s)
    person_devices = {p["person_id"]: [devices[k % 999]["device_id"]] for k, p in enumerate(persons)}
    for p in persons:
        if rng.random() < 0.15:
            person_devices[p["person_id"]].append(rng.choice(devices[:999])["device_id"])
    for a in accounts[:1700]:
        for d in person_devices[a["owner_id"]]:
            acct_devices.setdefault(a["account_id"], []).append(d)
            usage.append({"account_id": a["account_id"], "device_id": d, "first_seen": iso(ts(rng))})
    ring_accounts = [accounts[k] for k in (11, 112, 223, 334, 445, 556, 667)]  # 7 accounts, 7 different persons
    ring_start = datetime(2026, 3, 1, tzinfo=UTC)
    for k, a in enumerate(ring_accounts):
        usage.append({"account_id": a["account_id"], "device_id": "DV-7F3A-SHARED", "first_seen": iso(ring_start + timedelta(days=3 * k, hours=k))})
    with (out / "device_usage.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(usage[0]))
        w.writeheader()
        w.writerows(usage)

    # ---------------- transactions (10,000) ----------------
    txns = []
    person_accounts = accounts[:1700]
    def add_txn(src: str, dst: str, amount: float, when: datetime, loc: dict, channel: str, ip: str) -> None:
        lat, lon = jitter(rng, loc["lat"], loc["lon"], 0.3)
        txns.append({"txn_id": f"TX-{len(txns):07d}", "from_account": src, "to_account": dst, "amount": round(amount, 2),
                     "currency": "EUR", "ts": iso(when), "channel": channel, "location_id": loc["location_id"], "lat": lat, "lon": lon,
                     "ip": ip, "status": "settled", "data_label": LABEL})
    harbor = locations[1]
    # planted: ring accounts pay the merchant account shortly after using the shared device
    for k, a in enumerate(ring_accounts):
        for n in range(4):
            add_txn(a["account_id"], "ACC-9000001", rng.uniform(900, 2400), ring_start + timedelta(days=3 * k + n, hours=2), harbor, "mobile", "203.0.113.66")
    # planted: circular flow A→B→C→A
    cyc = [accounts[50]["account_id"], accounts[51]["account_id"], accounts[52]["account_id"]]
    for n in range(3):
        base = datetime(2026, 4, 10 + n, 10, tzinfo=UTC)
        for s_i in range(3):
            add_txn(cyc[s_i], cyc[(s_i + 1) % 3], 9500 - n * 10, base + timedelta(hours=s_i), locations[20], "wire", "198.51.100.23")
    # planted: AML layering into ORG-0002 account
    for n in range(12):
        src = rng.choice(person_accounts)["account_id"]
        add_txn(src, "ACC-9000002", rng.uniform(9000, 9900), datetime(2026, 5, 2, tzinfo=UTC) + timedelta(hours=7 * n), locations[30], "wire", "198.51.100.77")
    # planted: geo-temporal burst near Harbor Plaza, 2026-02-14 18:00-20:00
    for n in range(25):
        src, dst = rng.sample(person_accounts, 2)
        add_txn(src["account_id"], dst["account_id"], rng.uniform(20, 300), datetime(2026, 2, 14, 18, tzinfo=UTC) + timedelta(minutes=rng.randint(0, 120)),
                harbor, "card", f"10.20.{rng.randint(0, 255)}.{rng.randint(1, 254)}")
    while len(txns) < 10000:
        src, dst = rng.sample(accounts, 2)
        loc = rng.choice(locations)
        ip = home_ip[src["account_id"]] if rng.random() < 0.9 else f"10.{rng.randint(0, 255)}.{rng.randint(0, 255)}.{rng.randint(1, 254)}"
        add_txn(src["account_id"], dst["account_id"], rng.lognormvariate(4, 1.2), ts(rng), loc, rng.choice(["card", "mobile", "wire", "atm"]), ip)
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq

        pq.write_table(pa.Table.from_pylist(txns), out / "transactions.parquet")
    except ImportError:  # pragma: no cover
        with (out / "transactions.jsonl").open("w") as fh:
            for t in txns:
                fh.write(json.dumps(t) + "\n")
    counts["transactions"] = len(txns)

    # ---------------- events (5,000) ----------------
    events = []
    suspicious_ip = "203.0.113.66"
    def add_event(etype: str, when: datetime, account: str | None, device: str | None, ip: str | None, loc: dict | None, **extra) -> None:
        e = {"event_id": f"EV-{len(events):06d}", "event_type": etype, "ts": iso(when), "account_id": account or "", "device_id": device or "",
             "ip": ip or "", "location_id": loc["location_id"] if loc else "", "lat": loc["lat"] if loc else "", "lon": loc["lon"] if loc else "",
             "domain": extra.pop("domain", ""), "detail": json.dumps(extra) if extra else "", "data_label": LABEL}
        events.append(e)
    # planted cyber scenario: suspicious IP logins across ring accounts, auth failures, DNS lookups
    for k, a in enumerate(ring_accounts):
        t0 = ring_start + timedelta(days=3 * k, hours=1, minutes=30)
        add_event("auth_failure", t0 - timedelta(minutes=12), a["account_id"], "DV-7F3A-SHARED", suspicious_ip, harbor)
        add_event("login", t0, a["account_id"], "DV-7F3A-SHARED", suspicious_ip, harbor)
        add_event("device_connection", t0 + timedelta(minutes=12), a["account_id"], "DV-7F3A-SHARED", suspicious_ip, harbor)
        add_event("dns_query", t0 + timedelta(minutes=14), None, "DV-7F3A-SHARED", suspicious_ip, None, domain="update-portal.example")
        add_event("location_change", t0 + timedelta(minutes=40), a["account_id"], "DV-7F3A-SHARED", suspicious_ip, locations[2])
    etypes = ["login", "logout", "device_connection", "location_change", "auth_failure", "account_opened", "communication"]
    while len(events) < 5000:
        a = rng.choice(person_accounts)
        loc = rng.choice(locations)
        own = acct_devices.get(a["account_id"]) or [rng.choice(devices[:999])["device_id"]]
        dev = rng.choice(own) if rng.random() < 0.99 else rng.choice(devices[:999])["device_id"]
        ip = home_ip[a["account_id"]] if rng.random() < 0.85 else f"10.{rng.randint(0, 255)}.{rng.randint(0, 255)}.{rng.randint(1, 254)}"
        add_event(rng.choices(etypes, weights=[30, 25, 20, 10, 5, 2, 8])[0], ts(rng), a["account_id"], dev, ip, loc)
    with (out / "events.jsonl").open("w") as fh:
        for e in events:
            fh.write(json.dumps(e) + "\n")
    counts["events"] = len(events)

    domains = [{"domain": "update-portal.example", "registrar": "Example Registrar (synthetic)", "created": "2026-02-20", "resolves_to": suspicious_ip},
               {"domain": "northwind-quartz.example", "registrar": "Example Registrar (synthetic)", "created": "2025-10-01", "resolves_to": "198.51.100.10"}]
    for i in range(40):
        domains.append({"domain": f"site{i}.example", "registrar": "Example Registrar (synthetic)", "created": f"2025-{rng.randint(1, 12):02d}-01",
                        "resolves_to": f"198.51.100.{100 + i}"})
    with (out / "domains.json").open("w") as fh:
        json.dump({"data_label": LABEL, "domains": domains}, fh, indent=1)

    # ---------------- supply chain ----------------
    vessels = [{"vessel_id": f"VSL-{i:03d}", "name": f"MV {rng.choice(ORG_A)} {rng.choice(['Star', 'Spirit', 'Trader', 'Voyager'])}",
                "imo": f"IMO{9000000 + i * 137}", "flag": rng.choice(JURIS), "data_label": LABEL} for i in range(20)]
    with (out / "vessels.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(vessels[0]))
        w.writeheader()
        w.writerows(vessels)
    shipments = []
    for i in range(150):
        o, d = rng.sample(ports, 2)
        dep = ts(rng)
        shipments.append({"shipment_id": f"SHP-{i:06d}", "product": rng.choice(PRODUCTS), "quantity": rng.randint(10, 5000),
                          "supplier_id": rng.choice(orgs)["org_id"], "customer_id": rng.choice(orgs)["org_id"], "vessel_id": rng.choice(vessels)["vessel_id"],
                          "origin_port": o["location_id"], "destination_port": d["location_id"], "origin_lat": o["lat"], "origin_lon": o["lon"],
                          "dest_lat": d["lat"], "dest_lon": d["lon"], "departed_at": iso(dep), "arrived_at": iso(dep + timedelta(days=rng.randint(5, 30))),
                          "status": "delivered", "data_label": LABEL})
    s42 = shipments[42]
    s42.update(product="Lithium cells (synthetic)", supplier_id="ORG-0003", customer_id="ORG-0004", vessel_id="VSL-007",
               origin_port=ports[0]["location_id"], destination_port=ports[3]["location_id"], origin_lat=ports[0]["lat"], origin_lon=ports[0]["lon"],
               dest_lat=ports[3]["lat"], dest_lon=ports[3]["lon"], departed_at="2026-03-03T06:00:00Z", arrived_at="2026-03-21T15:30:00Z", warehouse_org="ORG-0005")
    with (out / "shipments.jsonl").open("w") as fh:
        for s in shipments:
            fh.write(json.dumps(s) + "\n")
    counts["shipments"] = len(shipments)

    manifest = {"label": LABEL, "seed": seed, "generated_for": "Tessera demonstration", "counts": counts,
                "notice": "All records are fabricated. Any resemblance to real persons or organisations is coincidental."}
    (out / "MANIFEST.json").write_text(json.dumps(manifest, indent=2))
    return counts


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(Path(__file__).resolve().parents[1] / "data" / "synthetic"))
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    print(json.dumps(generate(Path(args.out), args.seed), indent=2))
