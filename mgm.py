"""MGM il merkezi istasyonlarının son ölçümlerini alıp mgm.json'a yazar.

MGM'den alınan izinle kullanılır: 15-30 dakikada bir çekim, kaynak (Meteoroloji Genel Müdürlüğü) belirtilerek gösterim.
İstekler bu sitenin kendi kimliğiyle (User-Agent) gönderilir; başka bir site taklit edilmez.
GitHub Actions bunu 30 dakikada bir çalıştırır (.github/workflows/mgm.yml).
"""
import json, os, sys, time, unicodedata
from datetime import datetime, timezone
import requests

SERVIS = "https://servis.mgm.gov.tr/web"
SITE = os.environ.get("SITE_URL", "https://koksal4071.github.io/hava/")
BASLIK = {"User-Agent": f"kisisel-hava-sitesi/1.0 (+{SITE}; MGM izniyle, 30 dk aralikla)",
          "Accept": "application/json"}
CIKTI = "mgm.json"

ILLER = {
    "Marmara": ["Edirne", "Kırklareli", "Tekirdağ", "İstanbul", "Kocaeli", "Yalova", "Sakarya", "Bilecik", "Bursa", "Balıkesir", "Çanakkale"],
    "Ege": ["İzmir", "Manisa", "Aydın", "Denizli", "Muğla", "Afyonkarahisar", "Kütahya", "Uşak"],
    "Akdeniz": ["Antalya", "Isparta", "Burdur", "Mersin", "Adana", "Hatay", "Osmaniye", "Kahramanmaraş"],
    "İç Anadolu": ["Ankara", "Konya", "Kayseri", "Eskişehir", "Sivas", "Kırıkkale", "Aksaray", "Karaman", "Kırşehir", "Niğde", "Nevşehir", "Yozgat", "Çankırı"],
    "Karadeniz": ["Bolu", "Düzce", "Zonguldak", "Karabük", "Bartın", "Kastamonu", "Sinop", "Samsun", "Ordu", "Giresun", "Trabzon", "Rize", "Artvin", "Gümüşhane", "Bayburt", "Tokat", "Amasya", "Çorum"],
    "Doğu Anadolu": ["Erzurum", "Erzincan", "Kars", "Ardahan", "Iğdır", "Ağrı", "Van", "Muş", "Bitlis", "Bingöl", "Tunceli", "Elazığ", "Malatya", "Hakkari"],
    "Güneydoğu Anadolu": ["Gaziantep", "Kilis", "Şanlıurfa", "Adıyaman", "Diyarbakır", "Mardin", "Batman", "Siirt", "Şırnak"],
}

HADISE = {"A": "Açık", "AB": "Az bulutlu", "PB": "Parçalı bulutlu", "CB": "Çok bulutlu", "HY": "Hafif yağmurlu",
          "Y": "Yağmurlu", "KY": "Kuvvetli yağmurlu", "KKY": "Karla karışık yağmurlu", "HKY": "Hafif kar yağışlı",
          "K": "Kar yağışlı", "YKY": "Yoğun kar yağışlı", "HSY": "Hafif sağanak yağışlı", "SY": "Sağanak yağışlı",
          "KSY": "Kuvvetli sağanak yağışlı", "MSY": "Mevzi sağanak yağışlı", "DY": "Dolu", "GSY": "Gök gürültülü sağanak",
          "KGY": "Kuvvetli gök gürültülü sağanak", "SIS": "Sisli", "PUS": "Puslu", "DMN": "Dumanlı",
          "KF": "Toz veya kum taşınımı", "R": "Rüzgârlı", "GKR": "Güneyli kuvvetli rüzgâr", "KKR": "Kuzeyli kuvvetli rüzgâr",
          "SCK": "Sıcak", "SGK": "Soğuk", "HHY": "Yağışlı"}


def anahtar(ad):
    t = (ad or "").replace("İ", "i").replace("I", "ı").lower()
    t = unicodedata.normalize("NFKD", t.replace("ı", "i"))
    return "".join(c for c in t if c.isalnum() and not unicodedata.combining(c))


BOLGE = {anahtar(il): b for b, liste in ILLER.items() for il in liste}
BOLGE[anahtar("K.Maraş")] = "Akdeniz"
DOGRU_AD = {anahtar(il): il for liste in ILLER.values() for il in liste}


def sayi(x):
    try:
        if x is None or x == "":
            return None
        v = float(x)
        return None if v <= -9999 else v
    except (TypeError, ValueError):
        return None


def al(d, *anahtarlar):
    for k in anahtarlar:
        if isinstance(d, dict) and d.get(k) not in (None, ""):
            return d[k]
    return None


class Reddedildi(Exception):
    pass


class Erisilemiyor(Exception):
    pass


ARDISIK_HATA = 0


def getir(ses, yol, params):
    """Tek istek. Bağlantı/zaman aşımı üst üste 4 kez olursa Erisilemiyor fırlatır (gereksiz yere beklememek için)."""
    global ARDISIK_HATA
    for deneme in range(2):
        try:
            r = ses.get(f"{SERVIS}/{yol}", params=params, timeout=(6, 12))
        except requests.RequestException as e:
            ARDISIK_HATA += 1
            print(f"  bağlantı hatası ({yol}): {type(e).__name__}", flush=True)
            if ARDISIK_HATA >= 4:
                raise Erisilemiyor(f"{type(e).__name__}: {e}")
            time.sleep(2); continue
        if r.status_code < 500 and r.status_code != 429:
            ARDISIK_HATA = 0
        if r.status_code in (401, 403):
            raise Reddedildi(f"HTTP {r.status_code}: {r.text[:200]}")
        if r.status_code == 429 or r.status_code >= 500:
            ARDISIK_HATA += 1
            print(f"  HTTP {r.status_code} ({yol}): {r.text[:150]!r}", flush=True)
            if ARDISIK_HATA >= 4:
                raise Erisilemiyor(f"art arda HTTP {r.status_code}; yanıt: {r.text[:300]!r}")
            time.sleep(3); continue
        if r.status_code != 200:
            print(f"  HTTP {r.status_code} ({yol}): {r.text[:120]}", flush=True)
            return None
        try:
            return r.json()
        except ValueError:
            print(f"  JSON değil ({yol}): {r.text[:120]}", flush=True)
            return None
    return None


def il_merkezi(ses, il):
    liste = getir(ses, "merkezler", {"il": il}) or []
    if isinstance(liste, dict):
        liste = [liste]
    ak = anahtar(il)
    # il merkezi: ilçe adı boş ya da il adıyla aynı olan kayıt; yoksa ilk kayıt
    for m in liste:
        if not al(m, "ilce") or anahtar(al(m, "ilce")) in (ak, "merkez"):
            return m
    return liste[0] if liste else None


def main():
    ses = requests.Session(); ses.headers.update(BASLIK)
    print("MGM servisine bağlanılıyor…", flush=True)
    sonuc, eksik = [], []
    try:
        for bolge, iller in ILLER.items():
            for il in iller:
                m = il_merkezi(ses, il)
                mid = al(m, "merkezId", "merkezid") if m else None
                if not mid:
                    print(f"{il}: merkez bulunamadı", flush=True)
                    eksik.append(il); continue
                d = getir(ses, "sondurumlar", {"merkezid": mid})
                d = d[0] if isinstance(d, list) and d else d
                if not isinstance(d, dict):
                    eksik.append(il); continue
                try:
                    zaman = int(datetime.fromisoformat(str(al(d, "veriZamani")).replace("Z", "+00:00")).timestamp())
                except Exception:
                    eksik.append(il); continue
                kod = al(d, "hadiseKodu")
                sonuc.append({
                    "il": il, "bolge": bolge, "merkezId": mid, "istNo": al(d, "istNo") or al(m, "sondurumIstNo", "istNo"),
                    "lat": sayi(al(m, "enlem", "lat")), "lon": sayi(al(m, "boylam", "lon")), "yuk": sayi(al(m, "yukseklik")),
                    "zaman": zaman, "t": sayi(al(d, "sicaklik")), "nem": sayi(al(d, "nem")),
                    "hiz": sayi(al(d, "ruzgarHiz")), "yon": sayi(al(d, "ruzgarYon")),
                    "basinc": sayi(al(d, "denizeIndirgenmisBasinc")), "yagis": sayi(al(d, "yagis00Now")),
                    "kod": kod, "durum": HADISE.get(kod, kod),
                })
                print(f"{il}: {sonuc[-1]['t']}° {sonuc[-1]['durum']}", flush=True)
                time.sleep(0.4)  # nazik ol: ~80 il, 2 istek/il
    except Erisilemiyor as e:
        print("MGM servisi art arda hata verdi:", e)
        print("Servis bu tür isteklere hizmet vermiyor. İzinli erişim şeklini MGM'ye sorun. Eski mgm.json korunuyor.")
        return 1
    except Reddedildi as e:
        print("MGM servisi isteği reddetti:", e)
        print("İzin verilen erişim şeklini (gerekli başlık, IP veya anahtar) MGM'ye sorun. Eski mgm.json korunuyor.")
        return 1
    if not sonuc:
        print("Hiç ölçüm alınamadı; eski mgm.json korunuyor. Eksik iller:", ", ".join(eksik[:10]), "...")
        return 1
    with open(CIKTI, "w", encoding="utf-8") as f:
        json.dump({"guncel": int(time.time()), "kaynak": "Meteoroloji Genel Müdürlüğü (MGM)",
                   "kaynak_url": "https://www.mgm.gov.tr/", "iller": sonuc}, f, ensure_ascii=False, separators=(",", ":"))
    print(f"{len(sonuc)} il yazıldı." + (f" Alınamayan: {', '.join(eksik)}" if eksik else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
