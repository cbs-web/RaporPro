# RaporPro

RaporPro; zemin etüdü proje verilerini düzenleyen, mühendislik kontrolleri
çalıştıran ve Word/PDF/Excel çıktıları üreten Windows masaüstü uygulamasıdır.

## Kurulum ve çalıştırma

Desteklenen çalışma zamanı Python 3.11'dir.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\RaporPro_Baslat.bat
```

Başlatıcı önce `.venv` ortamını, sonra kullanıcıya ait Python 3.11 kurulumunu
arar. Uygulamanın tek giriş noktası `main.py` dosyasıdır.

## Kullanıcı verileri

Kalıcı ayarlar, günlükler, otomatik kayıtlar ve uygulama tarafından üretilen
geçici içerikler varsayılan olarak şu dizinde tutulur:

```text
%LOCALAPPDATA%\RaporPro
```

Eski `%APPDATA%\RaporPro` ayarları ve ihtiyaç duyulan veri dosyaları,
başlangıcı büyük önbelleklerle yavaşlatmadan, gerektikçe güvenli biçimde
kopyalanır. Kurumsal veya taşınabilir kurulumlarda konum
`RAPORPRO_DATA_DIR` ortam değişkeniyle değiştirilebilir. Projeye ait asıl JSON
ve çıktı dosyaları ise kullanıcının seçtiği konumda kalır.

## Dış yapay zekâ servisleri

`OpenAI`, `Google Gemini` veya `Groq` seçildiğinde ilgili not ya da rapor metni
dış hizmete gönderilebilir. Arayüz aktarım öncesinde kullanıcı onayı ister.
Veriyi cihaz dışına çıkarmadan çalışmak için `kural` motoru seçilmelidir.
API anahtarları ve hassas alanlar günlük kayıtlarında maskelenir.

## Testler

Hızlı geliştirme döngüsü:

```powershell
python -m pytest -m "not slow" -q
```

Teslim öncesi tam doğrulama:

```powershell
python -m pytest -q
```

`slow` işaretli testler gerçek render veya çok sayfalı dosya üretimi yaptığı
için daha uzun sürer.

## Kod haritası

- `main.py`: bağımlılık kontrolü, hata günlüğü ve uygulama başlangıcı
- `arayuz.py` ve `ui_*.py`: Tkinter arayüzü ve ekran akışları
- `proje_*.py`: proje şeması, paketleme, sürüm ve arşiv işlemleri
- `motor*.py`, `*_motoru.py`: hesaplama ve çıktı motorları
- `raporlama*.py`: Word raporu ve rapor tabloları
- `tutarlilik_*.py`, `kalite_kontrol.py`: veri ve çıktı kontrolleri
- `tests/`: birim, entegrasyon ve güvenlik regresyon testleri

Üretim kodu sahte hesaplama sonucuna sessizce düşmez; zorunlu bir modül
yüklenemiyorsa başlangıç denetimi gerçek hatayı gösterir.
