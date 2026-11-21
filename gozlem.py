"""Türkiye ve çevresindeki havalimanlarının son METAR gözlemlerini çekip gozlem.json'a yazar.

Kaynak: NOAA Aviation Weather Center (aviationweather.gov) Data API, anahtar gerekmez.
GitHub Actions bunu 30 dakikada bir çalıştırır; site gozlem.json'u okuyup en yakın istasyonu gösterir.
"""
import json, math, re, sys, time
from datetime import datetime, timezone
import requests

URL = "https://aviationweather.gov/api/data/metar"
# Türkiye + Kıbrıs + komşu sınır bölgeleri (güney, batı, kuzey, doğu)
BBOX = "34.5,25.0,42.6,45.5"
CIKTI = "gozlem.json"

HAVA_RE = re.compile(r"^(\+|-|VC)?(MI|PR|BC|DR|BL|SH|TS|FZ)?((DZ|RA|SN|SG|PL|GR|GS|UP|BR|FG|FU|VA|DU|SA|HZ|PO|SQ|FC|SS|DS)+)?$")
BULUT_RE = re.compile(r"^(FEW|SCT|BKN|OVC|VV)(\d{3}|///)(CB|TCU|///)?$")


def sayi(x):
    try:
        if x is None or x == "":
            return None
        return float(str(x).replace("+", ""))
    except (TypeError, ValueError):
        return None


def govde(raw):
    """Trend (TEMPO/BECMG/NOSIG) ve RMK kısımlarını at, sadece gözlem gövdesini bırak."""
    return re.split(r"\s(?:TEMPO|BECMG|NOSIG|RMK)\b", raw or "")[0].split()


def ham_coz(raw):
    t = govde(raw)
    s = {"gorus": None, "hava": [], "bulut": [], "cavok": False, "qnh": None, "tamam": False}
    for i, k in enumerate(t):
        if i < 2:  # METAR/SPECI, istasyon kodu, zaman
            continue
        if k == "CAVOK":
            s["cavok"] = True; s["gorus"] = 10000
        elif re.fullmatch(r"\d{4}", k) and s["gorus"] is None:
            s["gorus"] = int(k)
        elif re.fullmatch(r"\d{4}NDV", k) and s["gorus"] is None:
            s["gorus"] = int(k[:4])
        elif k in ("NSC", "SKC", "CLR", "NCD"):
            s["tamam"] = True
        elif BULUT_RE.match(k):
            m = BULUT_RE.match(k)
            taban = None if m.group(2) == "///" else int(m.group(2)) * 100
            s["bulut"].append([m.group(1), taban, (m.group(3) or "").replace("///", "")])
        elif re.fullmatch(r"Q\d{4}", k):
            s["qnh"] = int(k[1:])
        elif re.fullmatch(r"A\d{4}", k) and s["qnh"] is None:
            s["qnh"] = round(int(k[1:]) / 100 * 33.8639)
        elif k not in ("AUTO", "COR", "NIL") and not re.search(r"\d", k) and HAVA_RE.match(k) and k not in ("VC",):
            s["hava"].append(k)
    return s


def istasyon(m):
    raw = m.get("rawOb") or ""
    h = ham_coz(raw)
    zaman = m.get("obsTime")
    if not isinstance(zaman, (int, float)):
        try:
            zaman = int(datetime.fromisoformat(str(m.get("reportTime")).replace("Z", "+00:00")).timestamp())
        except Exception:
            zaman = None
    qnh = h["qnh"]
    if qnh is None:
        a = sayi(m.get("altim"))
        if a is not None:
            qnh = round(a * 33.8639) if a < 50 else round(a)
    gorus = h["gorus"]
    if gorus is None:
        v = sayi(m.get("visib"))  # statute mile
        if v is not None:
            gorus = min(10000, round(v * 1609))
    kt = lambda x: None if sayi(x) is None else round(sayi(x) * 1.852)
    ad = (m.get("name") or m.get("icaoId") or "").split(",")[0].strip()
    return {
        "id": m.get("icaoId"), "ad": ad, "lat": sayi(m.get("lat")), "lon": sayi(m.get("lon")),
        "yuk": sayi(m.get("elev")), "zaman": zaman,
        "t": sayi(m.get("temp")), "td": sayi(m.get("dewp")),
        "yon": m.get("wdir") if m.get("wdir") == "VRB" else sayi(m.get("wdir")),
        "hiz": kt(m.get("wspd")), "hamle": kt(m.get("wgst")),
        "gorus": gorus, "qnh": qnh, "hava": h["hava"], "bulut": h["bulut"],
        "cavok": h["cavok"], "acik": h["tamam"], "ham": raw,
    }


def main():
    r = None
    for deneme in range(3):
        try:
            r = requests.get(URL, params={"bbox": BBOX, "format": "json", "hours": 3}, timeout=40,
                             headers={"User-Agent": "kisisel-hava-sitesi (github pages)"})
            if r.status_code == 200:
                break
            print("HTTP", r.status_code, r.text[:200])
        except requests.RequestException as e:
            print("hata:", e)
        time.sleep(10 * (deneme + 1))
    if r is None or r.status_code != 200:
        print("Gözlem alınamadı; eski dosya korunuyor."); return 0
    veri = r.json()
    if isinstance(veri, dict):
        veri = veri.get("data") or veri.get("features") or []
    en_son = {}
    for m in veri:
        if isinstance(m, dict) and "properties" in m:  # geojson gelirse
            m = {**m["properties"], "lat": m["geometry"]["coordinates"][1], "lon": m["geometry"]["coordinates"][0]}
        try:
            s = istasyon(m)
        except Exception as e:
            print("atlandı:", m.get("icaoId"), e); continue
        if not s["id"] or s["lat"] is None or s["lon"] is None or s["zaman"] is None:
            continue
        if s["id"] not in en_son or s["zaman"] > en_son[s["id"]]["zaman"]:
            en_son[s["id"]] = s
    if not en_son:
        print("Hiç istasyon çözülemedi; eski dosya korunuyor."); return 0
    cikti = {"guncel": int(time.time()), "kaynak": "NOAA Aviation Weather Center (METAR)",
             "istasyonlar": sorted(en_son.values(), key=lambda s: s["id"])}
    with open(CIKTI, "w", encoding="utf-8") as f:
        json.dump(cikti, f, ensure_ascii=False, separators=(",", ":"))
    tr = [s for s in en_son.values() if (s["id"] or "").startswith("LT")]
    print(f"{len(en_son)} istasyon yazıldı ({len(tr)} Türkiye).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
