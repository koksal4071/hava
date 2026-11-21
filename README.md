# Hava Durumu + Kış Sinyali + Uyarı Bildirimi

| Dosya | Görevi |
|---|---|
| `index.html` | Site: şehir arama, anlık durum, uyarılar, 1-3-6-12 saat yağış, kar özeti, 10 gün, model seçimi ve karşılaştırma, kış sinyali |
| `uyari.py` | 30 dakikada bir tahmini kontrol eder, uyarı varsa telefona bildirim yollar |
| `uyari_ayar.json` | Bildirim alınacak şehirler ve ayarlar |
| `.github/workflows/hava-uyari.yml` | `uyari.py`'yi GitHub'da otomatik çalıştıran zamanlayıcı |

## 1. Site (GitHub Pages)
1. Depoya `index.html`'i yükle.
2. **Settings → Pages → Branch: main, /(root) → Save**.
3. Adres: `https://KULLANICIADIN.github.io/DEPOADI/` — telefonda **Ana ekrana ekle**.

## 2. Telefon bildirimi (ntfy, ücretsiz)
1. Telefona **ntfy** uygulamasını kur (Google Play / App Store).
2. Uygulamada **+ (Subscribe to topic)** → uzun ve tahmin edilmesi zor bir konu adı yaz, örn. `abdullah-hava-7k3q9x`.
   Konu adını bilen herkes bildirimleri görebilir; kimseyle paylaşma.
3. GitHub deposunda **Settings → Secrets and variables → Actions**:
   - **Secrets** sekmesi → **New repository secret** → Ad: `NTFY_TOPIC`, Değer: konu adın.
   - **Variables** sekmesi → **New repository variable** → Ad: `SITE_URL`, Değer: site adresin (bildirime dokununca açılır).
4. `uyari.py`, `uyari_ayar.json` ve `.github/workflows/hava-uyari.yml` dosyalarını depoya ekle.
   Web arayüzünde `.github` klasörü sürüklenemezse: **Add file → Create new file**, ad kutusuna
   `.github/workflows/hava-uyari.yml` yaz, dosyanın içeriğini yapıştır, **Commit**.
5. **Actions** sekmesi → (istenirse "I understand… enable") → **Hava uyarısı → Run workflow → Test bildirimi ✔ → Run**.
   Birkaç saniye içinde telefona "Test bildirimi" gelmeli.

## Ayarlar (`uyari_ayar.json`)
```json
{
  "sehirler": ["Kırşehir", "Ankara"],   // istediğin kadar şehir/ilçe
  "en_dusuk_seviye": "turuncu",          // "sari" yaparsan hafif yağışlar da bildirilir
  "tekrar_saat": 6                        // aynı uyarı en erken kaç saat sonra tekrar gönderilsin
}
```

## Bilinmesi gerekenler
- GitHub zamanlanmış görevleri yoğun saatlerde birkaç dakika gecikebilir; bildirim anlık değil, en fazla ~30-40 dk gecikmeli gelir.
- Herkese açık depolarda 60 gün hiç değişiklik yapılmazsa GitHub zamanlayıcıyı durdurur; e-posta gelir, **Actions** sekmesinden tekrar etkinleştirilir.
- Uyarılar model verisinden otomatik üretilir, resmî değildir. Resmî uyarılar: mgm.gov.tr
