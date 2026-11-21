"""
Hava uyarı bildirimi — GitHub Actions'ta 30 dakikada bir çalışır.

uyari_ayar.json'daki şehirler için Open-Meteo tahminini indirir, sitedeki
(index.html) uyarı kurallarının aynısını uygular ve yeni bir uyarı varsa
ntfy ile telefona bildirim gönderir. Aynı uyarıyı 'tekrar_saat' içinde
bir daha göndermez (durum uyari_durum.json'da, Actions önbelleğinde tutulur).

Ortam değişkenleri:
  NTFY_TOPIC  (zorunlu, GitHub Secret)  ntfy konu adı
  SITE_URL    (isteğe bağlı)            bildirime tıklayınca açılacak site
  TEST=true   (isteğe bağlı)            test bildirimi gönderir
"""

import json
import os
import sys
import urllib.parse
from datetime import datetime, timedelta, timezone

import requests

AYAR_DOSYA = "uyari_ayar.json"
DURUM_DOSYA = "uyari_durum.json"
SEVIYE = {"sari": 1, "turuncu": 2, "kirmizi": 3}
ONCELIK = {"sari": 3, "turuncu": 4, "kirmizi": 5}
OTURUM = requests.Session()
OTURUM.headers["User-Agent"] = "hava-uyari/1.0 (GitHub Actions)"


def yuv(x, d=0):
    return f"{x:.{d}f}".replace(".", ",")


# ---------------- veri ----------------

def konum_bul(sehir):
    if isinstance(sehir, dict) and "lat" in sehir:
        return sehir["ad"], sehir["lat"], sehir["lon"]
    ad = sehir if isinstance(sehir, str) else sehir["ad"]
    r = OTURUM.get("https://geocoding-api.open-meteo.com/v1/search",
                   params={"name": ad, "count": 1, "language": "tr", "format": "json"}, timeout=30)
    r.raise_for_status()
    sonuc = r.json().get("results") or []
    if not sonuc:
        raise ValueError(f"'{ad}' bulunamadı")
    return ad, sonuc[0]["latitude"], sonuc[0]["longitude"]


def tahmin(lat, lon):
    r = OTURUM.get("https://api.open-meteo.com/v1/forecast", timeout=60, params={
        "latitude": lat, "longitude": lon, "timezone": "auto", "forecast_days": 3,
        "current": "temperature_2m",
        "hourly": "temperature_2m,precipitation,precipitation_probability,snowfall,weather_code,wind_gusts_10m"})
    r.raise_for_status()
    return r.json()


# ---------------- kurallar (index.html ile aynı) ----------------

def uyarilar(d):
    h, simdi = d["hourly"], d["current"]["time"][:13] + ":00"
    i = h["time"].index(simdi) if simdi in h["time"] else 0
    dil = lambda k, n: [v if v is not None else 0 for v in h[k][i + 1:i + 1 + n]]
    zaman = lambda n: h["time"][i + 1:i + 1 + n]
    u = []

    p3, z3 = dil("precipitation", 3), zaman(3)
    top3, maks3 = sum(p3), max(p3 or [0])
    kod3 = dil("weather_code", 3)
    olas3 = max(dil("precipitation_probability", 3) or [0])
    if any(k >= 95 for k in kod3):
        saat = next(z for z, k in zip(z3, kod3) if k >= 95)[11:16]
        u.append(("kirmizi", "simsek", "3 saat içinde gök gürültülü sağanak",
                  f"Yıldırım ve ani kuvvetli yağış riski. İlk olası saat {saat}.", ["zap"]))
    if maks3 >= 8 or top3 >= 15:
        u.append(("kirmizi", "yagmur3", "3 saat içinde KUVVETLİ YAĞMUR",
                  f"3 saatte {yuv(top3, 1)} mm, saatlik en fazla {yuv(maks3, 1)} mm. Sel ve su baskınına dikkat.",
                  ["rotating_light", "cloud_with_rain"]))
    elif maks3 >= 4 or top3 >= 8:
        u.append(("turuncu", "yagmur3", "3 saat içinde kuvvetli yağış",
                  f"3 saatte {yuv(top3, 1)} mm, saatlik en fazla {yuv(maks3, 1)} mm.", ["cloud_with_rain"]))
    elif top3 >= 0.5:
        bas = next((z[11:16] for z, v in zip(z3, p3) if v >= 0.2), "–")
        u.append(("sari", "yagmur3", "3 saat içinde yağış bekleniyor",
                  f"{yuv(top3, 1)} mm, olasılık %{olas3:.0f}. Başlangıç {bas}.", ["umbrella"]))

    top12 = sum(dil("precipitation", 12))
    if top12 >= 40:
        u.append(("kirmizi", "yagmur12", "12 saatte çok kuvvetli yağış", f"Toplam {yuv(top12)} mm bekleniyor.", ["cloud_with_rain"]))
    elif top12 >= 20:
        u.append(("turuncu", "yagmur12", "12 saatte kuvvetli yağış", f"Toplam {yuv(top12)} mm bekleniyor.", ["cloud_with_rain"]))

    kar12 = sum(dil("snowfall", 12))
    if kar12 >= 5:
        u.append(("turuncu", "kar", "Kar yağışı", f"12 saatte {yuv(kar12)} cm kar bekleniyor. Buzlanma ve ulaşıma dikkat.", ["snowflake"]))
    elif kar12 >= 0.5:
        u.append(("sari", "kar", "Kar yağışı", f"12 saatte {yuv(kar12, 1)} cm kar bekleniyor.", ["snowflake"]))

    ruz = max(dil("wind_gusts_10m", 12) or [0])
    if ruz >= 75:
        u.append(("kirmizi", "ruzgar", "Fırtına", f"12 saat içinde {yuv(ruz)} km/sa'e varan hamleler.", ["dash"]))
    elif ruz >= 50:
        u.append(("turuncu", "ruzgar", "Kuvvetli rüzgâr", f"12 saat içinde {yuv(ruz)} km/sa'e varan hamleler.", ["dash"]))

    t24 = [v for v in h["temperature_2m"][i + 1:i + 25] if v is not None]
    if t24 and min(t24) <= -10:
        u.append(("turuncu", "soguk", "Çok soğuk", f"24 saat içinde {yuv(min(t24))}°C'ye kadar düşüş.", ["cold_face"]))
    elif t24 and min(t24) <= 0:
        u.append(("sari", "don", "Don ve buzlanma", f"24 saat içinde sıcaklık {yuv(min(t24))}°C'ye düşüyor.", ["ice_cube"]))
    if t24 and max(t24) >= 37:
        u.append(("turuncu", "sicak", "Aşırı sıcak", f"24 saat içinde {yuv(max(t24))}°C.", ["hot_face"]))
    return u


# ---------------- bildirim ----------------

def gonder(konu, baslik, mesaj, seviye, etiketler, tik=None):
    govde = {"topic": konu, "title": baslik, "message": mesaj,
             "priority": ONCELIK.get(seviye, 3), "tags": etiketler}
    if tik:
        govde["click"] = tik
    r = OTURUM.post("https://ntfy.sh/", json=govde, timeout=30)
    r.raise_for_status()


def main():
    konu = os.environ.get("NTFY_TOPIC", "").strip()
    if not konu:
        sys.exit("NTFY_TOPIC tanımlı değil (GitHub → Settings → Secrets and variables → Actions).")
    site = os.environ.get("SITE_URL", "").strip()
    with open(AYAR_DOSYA, encoding="utf-8") as f:
        ayar = json.load(f)
    esik = SEVIYE[ayar.get("en_dusuk_seviye", "turuncu")]
    tekrar = timedelta(hours=ayar.get("tekrar_saat", 6))

    if os.environ.get("TEST", "").lower() == "true":
        gonder(konu, "Test bildirimi", "Hava uyarı sistemi çalışıyor. Uyarılar bu kanaldan gelecek.",
               "sari", ["white_check_mark"], site or None)
        print("Test bildirimi gönderildi.")

    try:
        with open(DURUM_DOSYA, encoding="utf-8") as f:
            durum = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        durum = {}
    simdi = datetime.now(timezone.utc)

    for sehir in ayar["sehirler"]:
        try:
            ad, lat, lon = konum_bul(sehir)
            liste = uyarilar(tahmin(lat, lon))
        except Exception as e:
            print(f"⚠️  {sehir}: {e}")
            continue
        sd = durum.setdefault(ad, {})
        for seviye, anahtar, baslik, aciklama, etiket in liste:
            if SEVIYE[seviye] < esik:
                continue
            onceki = sd.get(anahtar)
            yeni = (onceki is None or SEVIYE[seviye] > SEVIYE.get(onceki["seviye"], 0)
                    or simdi - datetime.fromisoformat(onceki["zaman"]) >= tekrar)
            print(f"{ad}: {seviye.upper():8s} {baslik} {'→ GÖNDER' if yeni else '(daha önce gönderildi)'}")
            if yeni:
                tik = f"{site.rstrip('#')}#{urllib.parse.quote(ad)}" if site else None
                gonder(konu, f"{ad}: {baslik}", aciklama, seviye, etiket, tik)
                sd[anahtar] = {"seviye": seviye, "zaman": simdi.isoformat()}
        if not liste:
            print(f"{ad}: uyarı yok")

    # 2 günden eski kayıtları temizle
    for ad in list(durum):
        durum[ad] = {k: v for k, v in durum[ad].items()
                     if simdi - datetime.fromisoformat(v["zaman"]) < timedelta(days=2)}
    with open(DURUM_DOSYA, "w", encoding="utf-8") as f:
        json.dump(durum, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
