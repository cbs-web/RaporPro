# RaporPro performans kıyaslamaları

Bu klasördeki kıyaslamalar, aynı kullanıcı iş yükünü ve aynı doğruluk kontrollerini
koruyarak performans değişikliklerini karşılaştırır.

```powershell
python benchmarks/benchmark_performans.py --output benchmarks/results/sonuc.json
```

Ölçülen yollar:

- `startup_import`: yeni Python sürecinde ana uygulama modülünün yüklenmesi.
- `dependency_preflight`: yeni Python sürecinde paket ve log motoru ön kontrolü.
- `litoloji_korelasyonu`: 18 sondaj, 30 m derinlik ve 0,50 m hücrelerle korelasyon.
- `spt_excel_okuma`: 5.000 satırlık SPT Excel dosyasının okunması.
- `proje_saglik_ozeti`: dashboard sağlık ve hesap özetinin oluşturulması.
- `rapor_uretimi`: sekiz sondajlı gerçek Word raporunun dahili şablondan üretilmesi.

Her vaka önce ısındırılır. Ana karşılaştırma medyandır; p95 ve tepe bellek de raporlanır.
Hedeflenen vakada en az `%10` medyan iyileşmesi aranır, ilgisiz vakalarda `%5` üzerindeki
gerileme kabul edilmez. Ağ/API çağrısı yapılmaz ve her örnek değişmez sonuç koşullarıyla
doğrulanır.

Darboğaz profili:

```powershell
python benchmarks/benchmark_performans.py --case rapor_uretimi `
  --profile rapor_uretimi --profile-output benchmarks/results/rapor.prof
```
