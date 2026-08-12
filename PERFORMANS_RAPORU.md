# RaporPro Performans Raporu

Tarih: 12 Ağustos 2026

Başlangıç kontrol noktası: `6a0140d`

## Yöntem

- Aynı Windows bilgisayar ve Python 3.11.9 kullanıldı.
- Ağ ve yapay zekâ API çağrıları ölçümlere dahil edilmedi.
- Her vaka ısındırıldı; medyan, p95 ve ayrı `tracemalloc` tepe belleği kaydedildi.
- Her örnek sondaj, hücre, kayıt ve çıktı dosyası değişmezleriyle doğrulandı.
- Ham sonuçlar `benchmarks/results` altında tutulur.

## Önce ve Sonra

| Akış | Önce | Sonra | Değişim | Bellek önce | Bellek sonra |
|---|---:|---:|---:|---:|---:|
| Açılış paket/log ön kontrolü | 1,123 sn | 0,075 sn | `%93,4` daha kısa | - | - |
| Litoloji korelasyonu (18 sondaj, 1.080 hücre) | 36,489 sn | 0,696 sn | `%98,1` daha kısa | 2,346 MiB | 2,306 MiB |
| SPT Excel (5.000 satır) | 0,516 sn | 0,502 sn | `%2,8` daha kısa | 17,805 MiB | 7,692 MiB (`%56,8` azalma) |
| Word raporu (8 sondaj) | 5,163 sn | 3,900 sn | `%24,4` daha kısa | 53,222 MiB | 41,415 MiB (`%22,2` azalma) |

Güncel destek ölçümleri: başlangıç modül yükleme `2,113 sn`, proje sağlık özeti `2,78 ms`.

## Darboğazlar ve Düzeltmeler

### Açılış ön kontrolü

`motor_log.py` sağlık kontrolü çizim motorunu gerçekten çalıştırdığı için Matplotlib ve NumPy
paketlerini arayüzden önce yüklüyordu. Köprü ve kaynak imzaları artık dosyalar çalıştırılmadan
AST üzerinden doğrulanıyor. Tam dinamik denetim açık API olarak korundu. Doğrudan köprü
kontrolü medyanı ayrıca `964,9 ms`den `10,3 ms`ye indi.

### Litoloji korelasyonu

Profil, eksik `litoloji_renk_motoru` importunun her aday için yeniden denendiğini gösterdi:
86.400 import araması, yaklaşık 691 bin dosya `stat` çağrısı ve 69,1 saniyelik profilli çalışma.
Renk motoru tamamlandı; kaynak CIELAB değerleri bir kez, hedef değer hücre başına bir kez
hesaplandı ve bütün adayları sıralamak yerine yalnız en iyi aday tutuldu. Eşit puanda ilk
kaydı seçen kararlı davranış testle korunuyor.

### SPT Excel ve fotoğraf sırası

Excel dosyası `read_only=True` ile akış halinde okunuyor ve dosya tutamacı `finally` ile
kapatılıyor. Fotoğraf sırası için tekrar `realpath` çözümü ve O(n²) `list.index` kaldırıldı.

### Word kayıt yolu

DOCX daha önce kaydedildikten sonra yalnız extended metadata temizliği için ikinci kez
tamamen açılıp ZIP olarak sıkıştırılıyordu. `app.xml` bellekte temizlenip belge tek kez
kaydediliyor; atomik değiştirme, `Company/Manager` temizliği ve Word uyumluluğu korunuyor.

## Doğrulama

- `python -m pytest -q`: **438 geçti, 1 atlandı, 13 alt test geçti**.
- Metadata, dosya kapatma, eşit puan bağlayıcısı ve renk önhesabı için regresyon testleri eklendi.
- Statik köprü kontrolünün modül çalıştırmadığı, imzaları doğruladığı ve dinamik API'yi koruduğu test edildi.
- Benchmark doğruluk koşulları tüm ölçümlerde geçti.
- Ana pencere DPI-farkındalıklı `1920x1001` gerçek Tk yakalamasında taşma olmadan doğrulandı.
