# RaporPro Ürün Gereksinimleri

Güncelleme: 12 Ağustos 2026

## Ürün Tanımı

RaporPro, zemin ve temel etüdü veri raporu hazırlayan jeoloji/jeofizik ekiplerinin proje
verisini tek yerde toplamasını, denetlemesini ve belediyeye sunulabilir Word, PDF, log,
kesit, harita ve ek çıktıları üretmesini sağlayan Windows masaüstü uygulamasıdır.

Ana ürünün odağı **veri raporudur**. Geoteknik tasarım kararlarının ve imzalı mühendislik
onayının yerine geçmez; kaynak veriyi düzenler, hesapları izlenebilir biçimde uygular ve
çıktı üretimini otomatikleştirir.

## Kullanıcılar ve İhtiyaçlar

- Jeoloji mühendisi: sondaj, litoloji, SPT, PMT, karot ve yeraltı suyu verisini hızlı girer.
- Jeofizik mühendisi: sismik serim ve jeofizik parametrelerini tablo veya Excel ile aktarır.
- Rapor hazırlayan ekip: proje evraklarını, haritaları, laboratuvarı ve Word şablonunu birleştirir.
- Kontrol sorumlusu: eksik/uyumsuz veriyi rapor üretilmeden önce görür ve kaynağına gider.

## Temel İş Akışı

1. Proje oluşturulur; klasör yapısı ve künye bilgileri hazırlanır.
2. Bina, arazi, sondaj, litoloji ve deney verileri girilir veya çalışma sayfalarından aktarılır.
3. SPT fotoğrafları, LAB/jeofizik Excel verileri ve proje evrakları işlenir.
4. Araştırma noktaları haritası, mühendislik jeolojisi haritası, log ve kesit üretilir.
5. Proje sağlığı ve final kontrol çalıştırılır.
6. Veri raporu, tutanaklar, taahhütnameler ve ekler bağımsız veya teslim paketi olarak alınır.

## Mevcut Kapsam

- Sürümlemeli ve eski projelerle uyumlu proje JSON modeli.
- Excel benzeri Workbook, LAB Sheet ve Jeofizik Sheet veri girişi.
- SPT Merkezi: çoklu fotoğraf kuyruğu, yapay zekâ okuma, doğrulama ve kaynak izi.
- LAB/SPT/renk destekli manuel litoloji korelasyonu ve 0,50 m sınır düzenleme.
- Sondaj logu, çoklu sondaj kesiti, mercek, YASS ve baskı/kayıt seçenekleri.
- KML, TKGM, uydu/ortofoto, koordinat seçimi ve pafta üretimi.
- Dahili Word şablonu, etiket bazlı raporlama, revizyon, önizleme ve çıktı merkezi.
- Evrak okuma, yönetmelik merkezi, sondaj derinliği hesabı ve proje arşivi.
- Otomatik kayıt, geri alma, görev merkezi, performans/hata günlükleri ve güvenli atomik kayıt.

## Kullanılabilirlik İlkeleri

- İlk ekranda gerçek çalışma alanı açılır; pazarlama/karşılama ekranı kullanılmaz.
- Birincil komut tek vurgu rengiyle, silme gibi riskli komutlar yalnızca gerektiğinde kırmızıyla gösterilir.
- Yeşil, turuncu ve kırmızı proje durumları gerçek doğrulama sonucunu taşır; dekorasyon değildir.
- Pencereler ve sayfalar 120–240 ms arası kısa, iptal edilebilir giriş/çıkış geçişi kullanır.
- Animasyon ayarlardan kapatılabilir ve hiçbir hareket uygulama durumunu değiştirmez.
- Veri tablolarında klavye navigasyonu, sağ tık işlemleri ve açık hata açıklaması korunur.

## Performans Hedefleri

| Akış | Hedef | Güncel ölçüm |
|---|---:|---:|
| Uygulama modüllerini yükleme | <= 2,20 sn | 2,113 sn |
| Paket/log açılış ön kontrolü | <= 0,10 sn | 0,075 sn |
| 18 sondaj / 1.080 hücre litoloji korelasyonu | <= 1,00 sn | 0,696 sn |
| 5.000 satır SPT Excel okuma | <= 0,55 sn ve <= 8 MiB | 0,502 sn ve 7,69 MiB |
| Dashboard sağlık özeti | <= 10 ms | 2,78 ms |
| 8 sondajlı Word raporu | <= 4,20 sn | 3,900 sn |

Ölçüm komutu: `python benchmarks/benchmark_performans.py`.

## Kalite ve Kabul Ölçütleri

- Güncel otomatik doğrulama: **438 test geçti, 1 test atlandı, 13 alt test geçti**.
- Performans değişikliği aynı deterministik veri ve çıktı koşullarıyla önce/sonra ölçülür.
- Hedef akışta en az `%10` süre kazanımı veya belirgin bellek azalması aranır.
- Word çıktısında etiket, tablo, görsel, metadata ve atomik kayıt davranışı korunur.
- Eski proje açma/kaydetme ve kullanıcıya ait dosya yolları geriye dönük uyumlu kalır.

## Kill AI Slop Denetimi

Denetim aracı: `yetone/kill-ai-slop` (yerel Codex skill kurulumu).

Doğrulanan ve giderilenler:

- Eski uygulama planındaki dekoratif emoji ve trafik ışığı başlıkları kaldırıldı.
- Eski harita araçlarındaki emoji düğmeleri ve ilgisiz mor/turuncu/yeşil komut paleti sadeleştirildi.
- Birincil/ikincil/riskli komut hiyerarşisi ortak ürün renklerine bağlandı.

Bilinçli olarak korunanlar:

- Dashboard sağlık renkleri ölçülmüş veri durumunu temsil eder.
- SPT ve harita listelerindeki onay işareti gerçek seçim/tamamlanma durumudur.
- Yoğun mühendislik ekranlarındaki çerçeveli bilgi grupları tarama ve karşılaştırma içindir.

## İlerleme

| Alan | Durum | Sonraki kabul noktası |
|---|---|---|
| Çekirdek veri ve raporlama | Kullanımda | Çıktı regresyon testlerini büyüt |
| SPT/LAB/litoloji | Kullanımda | Gerçek saha örnekleriyle doğruluk seti oluştur |
| Log/kesit/harita | Kullanımda | Görsel altın örnek testlerini artır |
| Performans | Ölçüldü ve iyileştirildi | Büyük proje stres eşiğini CI'a ekle |
| Arayüz hareketi | Ana pencere, sayfa ve işlem pencerelerinde tamamlandı | Yeni Toplevel'lar ortak hazırlayıcıyı kullanmalı |
| Erişilebilirlik | Kısmi | Klavye odağı ve kontrast denetimini otomatikleştir |

## Riskler ve Sınırlar

- TKGM, harita altlıkları ve yapay zekâ servisleri ağ/servis kotasına bağlıdır.
- Gerçek Word sayfa yerleşimi Microsoft Word sürücüsü ve yüklü yazı tiplerinden etkilenebilir.
- 15 MB dahili şablon rapor açma/kaydetme süresinin alt sınırını belirler.
- Yapay zekâ sonucu kaynak görüntü ve kullanıcı doğrulaması olmadan kesin veri sayılmaz.
