#!/usr/bin/env python3
"""Build the fine gazetteer of the Kingdom from OpenStreetMap (Overpass API), for naming where rain falls:
villages and towns, named roads, bridges and junctions, wadis and mountain peaks, all with Arabic names.

    build_places.py OUT.json

Writes {"places": [[name, lat, lon, kind, known], ...], "lines": [[name, kind, [[lat, lon], ...], known], ...]};
known = 1 for what people outside the area know too: towns and cities, places with an encyclopaedia entry or
over 2000 people, landmarks, the main roads, long wadis.
Lines are resampled every ~700 m so the nearest one can be found with a simple point search.
Run once (by the gazetteer workflow, which has full internet); the result is committed next to this file.
Data (c) OpenStreetMap contributors, ODbL.
"""
import json, math, re, sys, time, urllib.parse, urllib.request

SERVERS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter",
           "https://overpass.private.coffee/api/interpreter"]
AREA = 'area["ISO3166-1"="SA"]["admin_level"="2"]->.sa;'
AR = re.compile(r"[؀-ۿ]")

QUERIES = {
    "places": AREA + 'node["place"~"^(city|town|village|hamlet|suburb|quarter|neighbourhood|locality|isolated_dwelling)$"](area.sa);out body;',
    "points": AREA + '(node["natural"="peak"]["name"](area.sa);node["highway"="motorway_junction"]["name"](area.sa);'
                     'node["natural"="saddle"]["name"](area.sa);node["mountain_pass"="yes"]["name"](area.sa););out body;',
    "bridges": AREA + 'way["bridge"]["name"](area.sa);out center;',
    "roads": AREA + 'way["highway"~"^(motorway|trunk|primary|secondary|tertiary)$"]["name"](area.sa);out geom;',
    "landmarks": AREA + '(nwr["tourism"~"^(attraction|museum|viewpoint|theme_park)$"]["name"]["wikidata"](area.sa);'
                        'nwr["historic"]["name"]["wikidata"](area.sa);nwr["natural"~"^(peak|valley|spring|cliff)$"]["name"]["wikidata"](area.sa);'
                        'nwr["place"="locality"]["name"]["wikidata"](area.sa););out center;',
    "routes": AREA + 'relation["route"="road"](area.sa);out geom;',
    "refroads": AREA + 'way["highway"~"^(motorway|trunk|primary)$"][!"name"]["ref"](area.sa);out geom;',
    "wadis": AREA + '(way["waterway"~"^(wadi|river|stream)$"]["name"](area.sa);way["natural"="valley"]["name"](area.sa););out geom;',
}


def fetch(q):
    data = urllib.parse.urlencode({"data": "[out:json][timeout:900];" + q}).encode()
    for k in range(6):
        url = SERVERS[k % len(SERVERS)]
        try:
            req = urllib.request.Request(url, data=data, headers={"User-Agent": "saudi-wrf-gazetteer/1.0"})
            with urllib.request.urlopen(req, timeout=1000) as r:
                j = json.load(r)
            if "runtime error" in j.get("remark", "") or "timed out" in j.get("remark", ""):
                raise RuntimeError(j["remark"][:200])      # a partial answer: try again
            return j["elements"]
        except Exception as e:  # noqa: BLE001
            print(f"  {url}: {e!r}", flush=True)
            time.sleep(30)
    raise SystemExit("overpass not reachable")


def arname(tags):
    for k in ("name:ar", "name", "alt_name:ar", "official_name:ar"):
        v = tags.get(k, "")
        if v and AR.search(v):
            return re.sub(r"\s+", " ", v).strip()
    return None


def resample(geom, step_km=0.7):
    pts = [(g["lat"], g["lon"]) for g in geom]
    out = [pts[0]]
    for (a, b), (c, d) in zip(pts, pts[1:]):
        dist = 111.2 * math.hypot(c - a, (d - b) * math.cos(math.radians(a)))
        n = int(dist // step_km)
        for i in range(1, n + 1):
            f = i * step_km / dist
            out.append((a + f * (c - a), b + f * (d - b)))
        out.append((c, d))
    keep, last = [], None       # drop points closer than half a step to the previous kept one
    for p in out:
        if last is None or 111.2 * math.hypot(p[0] - last[0], (p[1] - last[1]) * math.cos(math.radians(p[0]))) >= step_km / 2:
            keep.append([round(p[0], 4), round(p[1], 4)]); last = p
    return keep


def main():
    out = {"places": [], "lines": [], "source": "OpenStreetMap contributors (ODbL)", "built": time.strftime("%Y-%m-%d")}
    for key, q in QUERIES.items():
        print("query", key, flush=True)
        els = fetch(q)
        print(" ", len(els), "elements", flush=True)
        for e in els:
            t = e.get("tags", {})
            n = arname(t)
            if key == "refroads" and t.get("ref"):
                n = "الطريق رقم " + t["ref"].split(";")[0].strip()
                g = e.get("geometry")
                if g and len(g) >= 2:
                    out["lines"].append([n, "ref", resample(g, 1.0), 1])
                continue
            if not n:
                continue
            known = int(bool(t.get("wikidata") or t.get("wikipedia") or t.get("wikipedia:ar")))
            if key == "places":
                pop = re.sub(r"[^0-9]", "", t.get("population", "") or "")
                known = int(known or t["place"] in ("city", "town") or (pop != "" and int(pop) >= 2000))
                out["places"].append([n, round(e["lat"], 5), round(e["lon"], 5), t["place"], known])
            elif key == "landmarks":
                c = e.get("center") or ({"lat": e["lat"], "lon": e["lon"]} if "lat" in e else None)
                if c:
                    out["places"].append([n, round(c["lat"], 5), round(c["lon"], 5), "landmark", 1])
            elif key == "points":
                kind = "peak" if t.get("natural") == "peak" else "junction" if t.get("highway") == "motorway_junction" else "pass"
                out["places"].append([n, round(e["lat"], 5), round(e["lon"], 5), kind, known])
            elif key == "bridges":
                c = e.get("center")
                if c:
                    out["places"].append([n, round(c["lat"], 5), round(c["lon"], 5), "bridge", known])
            elif key == "routes":
                # a numbered highway as a whole, e.g. "طريق الطائف - الرياض": its member ways
                for mb in e.get("members", []):
                    g = mb.get("geometry")
                    if mb.get("type") == "way" and g and len(g) >= 2:
                        out["lines"].append([n, "route", resample(g, 1.0), 1])
            else:
                g = e.get("geometry")
                if g and len(g) >= 2:
                    kind = t.get("highway") or ("wadi" if key == "wadis" else "line")
                    pts = resample(g)
                    # well known: the main roads, and wadis with an encyclopaedia entry or over 30 km long
                    k2 = int(known or kind in ("motorway", "trunk", "primary") or (kind == "wadi" and len(pts) * 0.7 >= 30))
                    out["lines"].append([n, kind, pts, k2])
        time.sleep(5)
    # a wadi drawn as many short pieces: well known when all its pieces of the same name nearby reach 30 km
    tot = {}
    for x in out["lines"]:
        if x[1] == "wadi":
            k = (x[0], round(x[2][0][0]), round(x[2][0][1]))
            tot[k] = tot.get(k, 0) + len(x[2]) * 0.7
    for x in out["lines"]:
        if x[1] == "wadi" and tot.get((x[0], round(x[2][0][0]), round(x[2][0][1])), 0) >= 30:
            x[3] = 1
    # one entry per bridge name and place (OSM often splits a bridge into several ways)
    seen, places = set(), []
    for p in out["places"]:
        k = (p[0], round(p[1], 2), round(p[2], 2), p[3])
        if k not in seen:
            seen.add(k); places.append(p)
    out["places"] = places
    json.dump(out, open(sys.argv[1], "w"), ensure_ascii=False, separators=(",", ":"))
    kinds = {}
    for p in places:
        kinds[p[3]] = kinds.get(p[3], 0) + 1
    print("places", len(places), kinds, "lines", len(out["lines"]), "points on lines", sum(len(x[2]) for x in out["lines"]))


if __name__ == "__main__":
    main()
