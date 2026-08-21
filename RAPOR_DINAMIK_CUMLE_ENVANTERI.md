# RaporPro Dinamik Cümle Envanteri

Bu belge, Word veri raporuna proje verilerinden otomatik olarak yazılabilen deterministik metinleri listeler.

- `{...}` içindeki alanlar proje verileriyle doldurulur.
- Bir alana birden fazla seçenek yazılmışsa program veriye uyan seçeneği kullanır.
- Tablo başlıkları, hücre değerleri, dosya adları ve arayüz uyarıları bu listeye dahil değildir.
- Kullanıcının serbestçe yazdığı ek açıklamalar otomatik cümle değildir; program yalnızca boşlukları düzenleyip gerekirse sonuna nokta ekler.
- Yapay zeka ile Rapor Revizyon Merkezi'nde oluşturulan metinler serbest üretim olduğu için önceden sonlu bir cümle listesi yoktur.

## 1. Mevcut dahili Word şablonunda aktif ana metin alanları

Dahili şablonda aşağıdaki 18 ana metin etiketi kullanılmaktadır:

`[ETUT_AMAC_KAPSAM]`, `[RAPOR_KAPSAM]`, `[PARSEL_TANITIM]`,
`[IMAR_PLANI_ACIKLAMA]`, `[IMAR_ADASI_ACIKLAMA]`,
`[SONDAJ_ARAZI_GIRIS]`, `[JEOFIZIK_ARAZI_GIRIS]`, `[VP_ACIKLAMA]`,
`[MASW_SONUC_ACIKLAMA]`, `[MT_REZONANS_ACIKLAMA]`,
`[SONDAJ_BOLUM_GIRIS]`, `[LAB_FIZIK_GIRIS]`, `[LAB_MEKANIK_GIRIS]`,
`[KESIT_GIRIS]`, `[SONUC_GIRIS]`, `[SONUC_KONUM]`, `[SONUC_IMAR]`,
`[SONUC_AFET]`.

Bunlara ek olarak jeoloji, hidrojeoloji, litoloji dağılımı, zemin özeti,
PMT, karot, jeofizik sonuç ve YASS önerisi özel motorlarla dinamik üretilir.

## 2. Projenin amacı ve rapor kapsamı

### Sondaj özeti

- `Sahada sondaj çalışması yapılmamıştır.`
- `Sahada toplam {SONDAJ_ADEDI} adet sondaj kuyusu ({SK-1: 15 m, SK-2: 20 m, ...}) açılmıştır.`

### Etüdün amacı ve kapsamı

- `Bu çalışma, {KONUM} konumundaki {PROJE_ADI} için zemin koşullarının belirlenmesi ve geoteknik değerlendirmelere esas oluşturacak arazi, laboratuvar ve jeofizik verilerinin sunulması amacıyla hazırlanmıştır.`
- Konum yoksa aynı cümlede `{KONUM} konumundaki` yerine `inceleme alanındaki` kullanılır.

### Rapor kapsamı

- Çalışma yoksa:
  `Bu veri raporu, proje kapsamında mevcut arazi ve büro verilerinin değerlendirilmesi amacıyla hazırlanmıştır.`
- Çalışma varsa:
  `Bu veri raporu kapsamında {CALISMALAR} gerçekleştirilmiş; elde edilen bulgular parsel bazında değerlendirilmiştir. Arazi, laboratuvar ve büro çalışmalarının sonuçları ilgili bölüm, tablo ve eklerde sunulmuştur.`
- `{CALISMALAR}` listesine veri varsa şu ifadeler girer:
  `sondaj çalışmaları`, `SPT deneyleri`, `presiyometre deneyleri`,
  `karot değerlendirmeleri`, `sismik kırılma ve MASW ölçümleri`,
  `mikrotremör ölçümleri`, `laboratuvar deneyleri`.

## 3. Parsel ve çevre tanıtımı

- `İnceleme alanı {KONUM} sınırlarında yer almaktadır.`
- Koordinatlar varsa:
  `İnceleme alanı {KONUM} sınırlarında ve Enlem: {ENLEM}, Boylam: {BOYLAM} (WGS84) koordinatlarındadır.`
- Konum yoksa:
  `İnceleme alanının konum bilgileri proje künyesinde tanımlanmamıştır.`
- `Parsel alanı yaklaşık {PARSEL_ALANI} m²'dir.`
- `İnceleme alanının ortalama kotu {ORTALAMA_KOT} m'dir.`
- `En düşük kot {MIN_KOT} m, en yüksek kot {MAKS_KOT} m'dir.`
- `Çalışma alanında eğim {EGIM} olarak belirlenmiştir.`
- `Çalışma alanında eğim yönü {EGIM_YONU} olarak belirlenmiştir.`
- `Çalışma alanında eğim {EGIM}, eğim yönü {EGIM_YONU} olarak belirlenmiştir.`
- Parsel tipi ve yol bilgileri birleştirilerek doğal bir cümle üretilir:
  `Parsel, {YOL_CEPHELERI} {PARSEL_TIPI} niteliğinde olup ...`
- Sayısal komşu bilgisi bağlama göre `9 numaralı parsele komşudur` biçiminde
  yazılır; tam cümle girilmiş değerler etiket eklenmeden korunur.
- `Boş` yakın çevre yapısı için `Komşu parsellerde mevcut yapı bulunmamaktadır.`;
  `Boş` parsel kullanımı için `Parsel hâlihazırda boş durumdadır.` yazılır.
- Diğer serbest metinler bağlama uygun cümleye dönüştürülür; `Parselin yol
  cepheleri: ...` gibi mekanik etiketler üretilmez.
- `Bitki örtüsü: {BITKI_ORTUSU}.`
- `Altyapı durumu: {ALTYAPI_DURUMU}.`
- `Drenaj durumu: {DRENAJ_DURUMU}.`
- `Ulaşım durumu: {ULASIM_DURUMU}.`
- `İnceleme alanı yer bulduru haritası Şekil 1'de verilmiştir.`

`Çevre ek açıklaması` alanındaki metin de bu paragrafın sonuna kullanıcı metni olarak eklenir.

`Parsel çevresi özeti` alanı doluysa parsel tipi, yol cephesi, komşu parsel,
mevcut yapılar ve mevcut kullanım için ayrı mekanik cümleler yazılmaz; bu alan
tek bir kullanıcı kontrollü paragraf olarak kullanılır. Alan boşsa eski proje
davranışı korunur.

## 4. İmar planı ve imar adası

### İmar planı

- Girilen alanlar birleştirilerek:
  `İnceleme alanı {PLAN_ONAY_TARIHI} tarihli {KARAR_NO} sayılı karar {ONAY_IDARESI} tarafından onaylanan {PLAN_ADI} kapsamında değerlendirilmektedir.`
- Plan bilgisi yerine yalnız imar alanı varsa:
  `İnceleme alanı {IMAR_ALANI} içinde bulunmaktadır.`
- `İmar planına esas jeolojik-jeoteknik etüt kapsamında {IMAR_DURUMU} olarak değerlendirilmiştir.`
- `İnceleme alanı için Afete Maruz Bölge kararı bulunmadığı belirtilmiştir.`
- `İnceleme alanı için Afete Maruz Bölge kararı bulunduğu belirtilmiştir.`
- `Proje verilerinde yapı yasağı bulunmadığı belirtilmiştir.`
- `Proje verilerinde yapı yasağı bulunduğu belirtilmiştir.`
- `İmar durum belgesi {EK_NO}'de verilmiştir.`
- Hiç veri yoksa:
  `İnceleme alanına ait imar ve plan kararı bilgileri proje verilerinde tanımlanmamıştır.`

`İmar ek açıklaması` alanındaki metin de kullanıcı metni olarak eklenir.

### İmar adası

- `Çalışma alanı {IMAR_ALANI} içinde bulunmaktadır.`
- `Yol ve cephe durumu: {YOL_CEPHELERI}.`
- `Komşu parseller: {KOMSU_PARSELLER}.`
- `Ulaşım: {ULASIM_DURUMU}.`
- `Altyapı: {ALTYAPI_DURUMU}.`
- `Drenaj: {DRENAJ_DURUMU}.`
- Hiç veri yoksa:
  `İmar adasının yol, komşuluk ve altyapı bilgileri proje verilerinde tanımlanmamıştır.`

## 5. İklim, don, afet ve aktif tektonik

Bu bölümdeki motor cümleleri kodda bulunmaktadır; ancak ilgili 16 eski ana etiket
mevcut dahili şablonda kullanılmadığı için cümlelerin bir kısmı yalnız özel/eski
şablonlarda devreye girer.

### İklim

- `{IL} çevresinde {IKLIM_TIPI} özellikleri görülmektedir.`
- `İklim değerlendirmesinde {METEOROLOJI_ISTASYONU} verileri esas alınmıştır.`
- `İklim değerlendirmesinde {METEOROLOJI_ISTASYONU} ({OLCUM_DONEMI} ölçüm dönemi) verileri esas alınmıştır.`
- `İklim verisi kaynağı: {IKLIM_KAYNAGI}.`
- Hiç veri yoksa:
  `İnceleme alanına ilişkin iklim verileri proje bilgilerinde tanımlanmamıştır.`

### Don durumu

- `Proje alanı için don penetrasyon derinliği {DON_DERINLIGI} cm olarak alınmıştır.`
- `Don koşulları bakımından çalışmaya uygun olmayan dönem {DON_DONEMI} olarak belirtilmiştir.`
- Hiç veri yoksa:
  `Don derinliği ve çalışma dönemi bilgileri proje verilerinde tanımlanmamıştır.`

### Doğal afetler

Aşağıdaki `{TEHLIKE}` alanı `heyelan tehlikesi`, `kaya düşmesi tehlikesi`,
`çığ tehlikesi` veya `çökme tehlikesi` olabilir:

- `Mevcut proje verilerinde {TEHLIKE} belirlenmemiştir.`
- `Mevcut proje verilerinde {TEHLIKE} bulunduğu belirtilmiştir.`
- `Mevcut veriler kapsamında inceleme alanını etkileyen taşkın riski belirlenmemiştir.`
- `İnceleme alanında taşkın riski bulunduğu belirtilmiştir.`
- `Türkiye Deprem Tehlike Haritasına göre çalışma alanı için PGA475={PGA} g olarak alınmıştır.`
- Hiç veri yoksa:
  `Doğal afet tehlikelerine ilişkin parsel bazlı değerlendirme proje verilerinde tanımlanmamıştır.`

`Afet ek açıklaması` alanındaki metin de kullanıcı metni olarak eklenir.

### Aktif tektonik ve faylar

- Fay kaydı varsa:
  `Çalışma alanının aktif tektonik özellikleri güncel diri fay verileri kullanılarak değerlendirilmiş; yakın faylar aşağıdaki tabloda sunulmuştur.`
- Fay kaydı yoksa:
  `Aktif tektonik ve yakın diri fay bilgileri proje verilerinde tanımlanmamıştır.`
- Aktif fay giriş tablosu varsa:
  `Çalışma alanına yakın aktif faylara ilişkin proje bazlı bilgiler aşağıdaki tabloda verilmiştir.`
- Aktif fay giriş tablosu yoksa:
  `Yakın aktif fay mesafeleri proje verilerinde tanımlanmamıştır.`

Kullanıcı `aktif tektonik açıklaması` yazarsa ilk iki otomatik seçenek yerine bu metin kullanılır.

## 6. Sondaj ve arazi çalışmaları

### Arazi çalışmaları giriş paragrafı

- Sondaj yoksa:
  `Sahada sondaj çalışması yapılmamıştır.`
- Sondaj varsa önce sondaj özeti yazılır ve ardından:
  `Sondaj çalışmaları TS EN ISO 22475-1 standardı esas alınarak yürütülmüştür.`
- SPT varsa:
  `SPT deneyleri TS EN ISO 22476-3 standardına göre değerlendirilmiştir.`
- PMT varsa, PMT kaydı bulunan sondajlar doğal sırayla listelenir:
  `SK-2 ve SK-4 sondajlarında presiyometre deneyi yapılmıştır.`
- TCR/SCR/RQD genel cümlesi yazılmaz. Gerçek karot yüzdesi açıklaması ve karot
  tablosu, veri bulunduğunda kendi rapor bölümünde korunur.

### Sondaj bölümü giriş paragrafı

- Sondaj yoksa:
  `Proje verilerinde sondaj kaydı bulunmamaktadır.`
- Sondaj varsa:
  `Sahada toplam {SONDAJ_ADEDI} adet sondaj kuyusu ({SONDAJLAR_VE_DERINLIKLER}) açılmıştır. Sondaj profilleri, koordinatları ve arazi deneyleri ilgili tablo, şekil ve eklerde sunulmuştur.`

### SPT

- SPT yoksa:
  `Proje verilerinde SPT deney kaydı bulunmamaktadır.`
- SPT varsa:
  `Çalışma alanındaki sondajlarda toplam {SPT_ADEDI} SPT deney kaydı bulunmaktadır. Deneyler TS EN ISO 22476-3 standardına göre değerlendirilmiş ve sonuçlar aşağıdaki tabloda verilmiştir.`
- Teknik bilgiler varsa:
  `SPT deneylerinde sondaj kuyu çapı {DELGI_CAPI}, kuyu üzerinde kalan tij boyu {TIJ_BOYU} m, deney düzeneği {SAHMERDAN}, enerji oranı %{ENERJI_ORANI}, {NUMUNE_ALICI} kullanılmıştır.`
- Teknik alanların yalnız dolu olanları cümleye alınır.
- Hiçbiri yoksa:
  `SPT deney düzeneğinin teknik özellikleri proje verilerinde tanımlanmamıştır.`

## 7. Jeofizik arazi çalışmaları ve yöntemler

### Jeofizik arazi çalışması

- Veri yoksa:
  `Proje verilerinde jeofizik arazi çalışması kaydı bulunmamaktadır.`
- Yalnız sismik varsa:
  `Jeofizik çalışmalar kapsamında {TARIH} tarihinde {SERIM_ADEDI} sismik serim üzerinde Sismik Kırılma ve MASW ölçümleri gerçekleştirilmiştir. Ölçüm sonuçları ilgili tablo ve eklerde sunulmuştur.`
- Yalnız mikrotremör varsa:
  `Jeofizik çalışmalar kapsamında {TARIH} tarihinde {MT_ADEDI} noktada Mikrotremör ölçümleri gerçekleştirilmiştir. Ölçüm sonuçları ilgili tablo ve eklerde sunulmuştur.`
- Her ikisi varsa:
  `Jeofizik çalışmalar kapsamında {TARIH} tarihinde {SERIM_ADEDI} sismik serim üzerinde Sismik Kırılma ve MASW ve {MT_ADEDI} noktada Mikrotremör ölçümleri gerçekleştirilmiştir. Ölçüm sonuçları ilgili tablo ve eklerde sunulmuştur.`

Tarih boşsa `{TARIH} tarihinde` bölümü yazılmaz.

### Sismik kırılma

- `Sismik kırılma ölçümleri {KANAL_SAYISI} kanallı {SISMIK_CIHAZ} ile gerçekleştirilmiştir. Çalışmada tabakaların P dalgası hızlarının ve dinamik özelliklerinin belirlenmesi amaçlanmıştır. Sismik kaynak olarak {SISMIK_KAYNAK} kullanılmıştır. Ölçüm parametreleri ilgili tabloda verilmiştir.`
- Kanal sayısı ve kaynak boşsa ilgili parçalar yazılmaz; cihaz boşsa `sismik ölçü sistemi` kullanılır.
- `Sismik kırılma kayıtlarından belirlenen P dalgası hızları aşağıdaki tabloda verilmiştir.`

### MASW

- `MASW yöntemi ile Rayleigh dalgası dispersiyon eğrileri elde edilmiş ve ters çözüm sonucunda S dalgası hız modeli oluşturulmuştur. Ölçümler {SISMIK_CIHAZ} ile gerçekleştirilmiştir. Veri toplamada {JEOFON_BILGISI} jeofonlar ve {SISMIK_KAYNAK} kullanılmıştır.`
- Jeofon veya kaynak yoksa yalnız bulunan bilgi yazılır; ikisi de yoksa son cümle yazılmaz.
- `MASW ölçümlerinden elde edilen dispersiyon değerlendirmeleri ve hesaplanan Vs30 değerleri ilgili şekil, tablo ve eklerde sunulmuştur.`

### Mikrotremör

- `Mikrotremör ölçümleri {MT_CIHAZI} kullanılarak, arazi koşullarını temsil edecek noktalarda gerçekleştirilmiştir.`
- Cihaz boşsa `{MT_CIHAZI}` yerine `üç bileşenli sismometre` kullanılır.
- Kayıt süresi ve yazılım varsa:
  `Ölçüm noktalarında yaklaşık {KAYIT_SURESI} dakikalık üç bileşenli kayıtlar alınmış ve kayıtlar {YAZILIM} yazılımı ile değerlendirilmiştir. Değerlendirme sonucunda baskın frekans, baskın periyot ve H/V oranları belirlenmiştir.`
- Kayıt süresi yoksa `yaklaşık {KAYIT_SURESI} dakikalık` bölümü yazılmaz.
- Yazılım yoksa `kayıtlar spektral oran yöntemiyle değerlendirilmiştir` kullanılır.
- `Mikrotremör ölçümlerinden belirlenen baskın periyot değerleri, yapı periyotlarıyla birlikte geoteknik rapor kapsamında değerlendirilmelidir.`

## 8. Araştırma çukuru

- `Çalışma alanında araştırma çukuru çalışması yapılmıştır.`
- `Çalışma alanında araştırma çukuru kazılmamıştır.`
- Durum belirtilmemişse:
  `Araştırma çukuru çalışmasına ilişkin bilgi proje verilerinde tanımlanmamıştır.`

Kullanıcı araştırma çukuru açıklaması yazarsa bu otomatik seçeneklerin yerine o metin kullanılır.

## 9. Laboratuvar

- Laboratuvar verisi yoksa:
  `Proje verilerinde laboratuvar deney sonucu bulunmamaktadır.`
- Laboratuvar adı varsa:
  `Sondajlardan alınan numuneler üzerinde gerekli deneyler {LABORATUVAR_ADI} laboratuvarında gerçekleştirilmiştir.`
- Laboratuvar adı yok fakat veri varsa:
  `Sondajlardan alınan numuneler üzerinde gerekli deneyler yetkili laboratuvarda gerçekleştirilmiştir.`
- `Laboratuvar sonuçları {EK_NO}'de sunulmuştur.`
- `Laboratuvar sonuçlarında bulunan indeks ve fiziksel özellik deneyleri birim bazında değerlendirilmiştir.`
- `Laboratuvar sonuçlarında bulunan mekanik özellik deneyleri birim bazında değerlendirilmiştir.`

`Laboratuvar yetki açıklaması` alanındaki metin kullanıcı metni olarak araya eklenir.

## 10. Zemin özeti

SPT ile bulunan kıvam/sıkılık sınıfları ve laboratuvar yüzdeleri kullanılarak:

- İnce daneli birimde SPT durumu varsa:
  `{BIRIM} birimleri {KIVAMLAR} olup, laboratuvar sonuçlarına göre içeriğinde ortalama olarak %{CAKIL} Çakıl, %{KUM} Kum ve %{SILT_KIL} Silt-Kil barındırmaktadır.`
- İri daneli birimde SPT durumu varsa:
  `{BIRIM} birimleri sıkılığı {SIKILIKLAR} olup, laboratuvar sonuçlarına göre içeriğinde ortalama olarak %{CAKIL} Çakıl, %{KUM} Kum ve %{SILT_KIL} Silt-Kil barındırmaktadır.`
- SPT durumu bulunamazsa:
  `{BIRIM} birimleri, laboratuvar sonuçlarına göre içeriğinde ortalama olarak %{CAKIL} Çakıl, %{KUM} Kum ve %{SILT_KIL} Silt-Kil barındırmaktadır.`
- Laboratuvar verisi yoksa:
  `Laboratuvar verisi girilmediği için zemin özeti oluşturulamadı.`

Kıvam seçenekleri: `çok yumuşak`, `yumuşak`, `orta katı`, `katı`, `çok katı`, `sert`.

Sıkılık seçenekleri: `çok gevşek`, `gevşek`, `orta sıkı`, `sıkı`, `çok sıkı`.

Birden fazla durum varsa `orta katı - katı` örneğindeki gibi sıralanır.

## 11. Litoloji dağılımı

Her bulunan birim için şu kalıp kullanılır:

- `{BIRIM} birimleri {SK-1}'de {BASLANGIC-BITIS}m, {SK-2}'de {BASLANGIC-BITIS}m derinlikleri arasında gözlenmiştir.`

Bu cümleyi üretebilen birimler:

`Çakıl`, `Siltli Çakıl`, `Killi Çakıl`, `Çakıllı Kum`, `Çakıllı Killi Kum`,
`Çakıllı Siltli Kum`, `Siltli Kum`, `Kum`, `Killi Kum`, `Kil`, `Kumlu Kil`,
`Çakıllı Kil`, `Kumlu Silt`, `Kumlu Siltli Killi Çakıl`.

## 12. PMT ve karot cümleleri

### Presiyometre

- Tek sondaj:
  `Çalışma alanında {SK_NO} sondajında presiyometre deneyi yapılmıştır. Deneyler TS EN ISO 22476-4 ve ASTM D4719-00 standartlarına uygun olarak yapılmıştır. Presiyometre deney sonuçları Tablo {13/14}'te verilmiştir.`
- Birden fazla sondaj:
  `Çalışma alanında {SK-1, SK-3 ve SK-5} sondajlarında presiyometre deneyi yapılmıştır. Deneyler TS EN ISO 22476-4 ve ASTM D4719-00 standartlarına uygun olarak yapılmıştır. Presiyometre deney sonuçları Tablo {13/14}'te verilmiştir.`
- Karot tablosu varsa PMT tablosu 14, karot tablosu yoksa 13 numara olur.
- Geçerli PMT verisi yoksa PMT başlığı, cümlesi ve tablosu kaldırılır.

### Karot

- Tek TCR değeri varsa:
  `Çalışma alanında yapılan sondajlarda karot yüzdeleri %{TCR}'dir. Kesilen birimlerin çakıl içeriği, basınçlı sondaj suyu ile temas ettiğinde dağılma ve erime özelliği göstermesinin karot yüzdesinin düşmesine neden olduğu düşünülmektedir.`
- TCR aralığı varsa:
  `Çalışma alanında yapılan sondajlarda karot yüzdeleri %{MIN_TCR}-%{MAKS_TCR} arasındadır. Kesilen birimlerin çakıl içeriği, basınçlı sondaj suyu ile temas ettiğinde dağılma ve erime özelliği göstermesinin karot yüzdesinin düşmesine neden olduğu düşünülmektedir.`
- Geçerli karot verisi yoksa karot başlığı, cümlesi ve tablosu kaldırılır.

## 13. Jeoloji cümle motoru

### Birimin cümle içindeki ifade biçimleri

- Rezidüel: `{BIRIM_ADI} ({KOD}) birimine ait rezidüel zeminler`
- Ana kaya: `{BIRIM_ADI} ({KOD}) ana kaya birimi`
- Alüvyon: `{BIRIM_ADI} ({KOD}) çökelleri`
- Dolgu: `{BIRIM_ADI} ({KOD}) dolgu birimi`
- Durum belirtilmemiş: `{BIRIM_ADI} ({KOD}) birimi`
- Yaş bilgisi gereken yerde başına `{YAS} yaşlı` eklenir.

### Bölgesel ve mühendislik jeolojisi

- Birim yoksa:
  `İnceleme alanının literatür jeolojisi proje verilerinde tanımlanmamıştır.`
- Bölgesel harita cümlesi:
  `Bölgenin genel jeoloji haritası Şekil 5'te verilmiştir.`
- Birim hem çalışma alanı hem yakın çevredeyse:
  `İnceleme alanı ve yakın çevresinde literatür verilerine göre {BIRIMLER} bulunmaktadır.`
- Birim yalnız çalışma alanındaysa:
  `İnceleme alanında literatür verilerine göre {BIRIMLER} bulunmaktadır.`
- Birim yalnız yakın çevredeyse:
  `İnceleme alanının yakın çevresinde literatür verilerine göre {BIRIMLER} yüzeylenmektedir.`

### Jeolojik kesit

- Kesitte kullanılacak birim varsa, birim başlıkları ve ayrıntılı açıklamaları
  yazılır; ayrıca otomatik bir “esas alınmıştır” giriş cümlesi eklenmez.
- Birim yoksa:
  `Jeolojik kesitte kullanılacak literatür birimi proje verilerinde tanımlanmamıştır.`

### Jeoloji sonucu ve mikrotremör birim metni

- `İnceleme alanında literatür verilerine göre {YASLI_BIRIMLER} bulunmaktadır.`
- Birim yoksa:
  `İnceleme alanının literatür jeolojisi proje verilerinde tanımlanmamıştır.`
- Çalışma alanı birimi varsa:
  `İnceleme alanında yapılan mikrotremör ölçümlerinde {BIRIMLER} için ölçülen değerler Tablo 9'da verilmiştir.`
- Birim yoksa:
  `İnceleme alanında yapılan mikrotremör ölçümlerinden elde edilen değerler Tablo 9'da verilmiştir.`

### Seçilen formasyona göre eklenen katalog paragrafları

#### Alüvyon (Qal)

`Akarsu yataklarında, eski çukurluklar üzerinde ve kıyı kuşaklarındaki düzlükler üzerinde gelişmiş çakıl, kum ve çamur çökelleridir.`

#### Alçıtepe Üyesi (Tmal)

`Biga Yarımadası'nda İntepe-Çanakkale arasındaki yükseltilerde, Gelibolu Yarımadası'nda ise Eceabat güneyinde yüzeylenen ve başlıca kireçtaşlarından oluşan litoloji topluluğu ilk olarak Druitt (1961) tarafından Alçıtepe birimi olarak tanımlanmıştır. Bu çalışmada da Alçıtepe üyesi adı kabul edilmiştir.`

`Alçıtepe üyesinin tip kesit yeri, Umurbey kasabası güneyindeki Tekkedere ile Çardakbayırı Tepe arasındadır. Ayrıca Kuzgunkaya Tepe'de de referans kesiti bulunmaktadır.`

`Alçıtepe üyesi stromatolit yapılı kireçtaşlarından, oolitlerden, kalkarenitlerden, fosilli kireçtaşları ile silttaşı ve marnlardan oluşur. Yaşı Geç Miyosen (orta-geç Panoniyen) olarak saptanmıştır (Atabey ve diğerleri, 2004). Alçıtepe üyesi gelgit ortamında çökelen karbonat fasiyeslerini yansıtır.`

#### Çamrakdere Üyesi (Tmçd)

`Çanakkale Boğazı'nın her iki kıyısında yüzeylenen ve çamurtaşı, silttaşı, kumtaşı ve çakılcıklı konglomera ile kalkarenitten oluşan kayaç topluluğu ilk defa Şentürk ve Karaköse (1987) tarafından Çanakkale formasyonunun Çamrakdere üyesi olarak adlandırılmıştır. Bu çalışmada da Çanakkale formasyonunun bir üyesi olarak tanımlanan aynı kayaç toplulukları Çamrakdere üyesi olarak tanımlanmıştır.`

`Çamrakdere üyesi çamurtaşı, silttaşı, kumtaşı ve çakılcıklı konglomera ile kalkarenitten oluşmaktadır. Gri-yeşil renkli çamurtaşları, bol miktarda fosil ya da kırılmış kavkı parçası içerirler. Bunun yanı sıra kömürleşmiş bitki sap-kök izleri ile kaliş yumruları da çamurtaşları içinde gözlenmektedir. Çamurtaşları içinde genelde birkaç mm-cm kalınlıkta lentiküler tabakalı kumtaşları yer almaktadır. Kumtaşları düzlemsel paralel katmanlı ve ripıl çapraz katmanlı olarak gözlenmektedir. Bu kumtaşları flaser ve dalgalı çamurtaşları ile ardalanmalı olarak bulunmaktadır. Bol miktarda kırılmış kavkı parçası içeren kumtaşları ve çakılcıklı konglomeralar, çamurtaşları ve kumtaşları üzerinde erozyonal taban yüzeyli olarak düzlemsel eğimli tabakalanmalar şeklinde dirsek barı çökellerini oluştururlar. Genelde ince tabakalı olarak gözlenen kalkarenitler, fosil ve kavkı parçalarınca zengindir.`

`Çamrakdere üyesi yanal yönde Kirazlı üyesi ve düşey yönde ise Alçıtepe üyesine ait kayaçlarla geçişlidir. Altında yer alan Gazhanedere formasyonu ile paralel uyumsuzdur ve üyenin yaşı Geç Miyosen (orta-geç Panoniyen) olarak saptanmıştır (Atabey ve diğerleri, 2004).`

#### Kirazlı Üyesi (Tmki)

`Gazhanedere formasyonu üzerinde yer alan ve egemen olarak ufak-kaba taneli kumtaşı ile daha az oranda çakılcık-ufak çakıllı konglomera, silttaşı ve çamurtaşından oluşan denizel birim Saltık (1974) tarafından Kirazlı formasyonu olarak tanımlanmıştır. Benzer fasiyes özelliklerine sahip olan kayaç toplulukları Biga ve Gelibolu Yarımadaları'nda da yüzeylenmekte olup Çanakkale formasyonu içinde tanımlanan diğer fasiyes toplulukları ile ardalanmalı olarak bulunmaktadır. Dolayısıyla Çanakkale Boğazı kıyısında yüzeylenen sığ denizel kayaçlar bu çalışmada Çanakkale formasyonunun bir üyesi olarak tanımlanmış ve birimin tanımlandığı ilk isme atfen Kirazlı üyesi adı kabul edilmiştir.`

`Kirazlı üyesi Çanakkale güneyinde yaygın olarak Güzelyalı, İntepe, Kumkale arasındaki kıyı şeridinde, Gelibolu Yarımadası'nda ise Üre Dağı batısı ile Çamaltı-Palamut Burnu arasında yüzeylenmektedir. Biga Yarımadası'nda üyenin tip kesit yeri Güzelyalı ile İntepe arasında kalan karayolu yarmasıdır.`

#### Çanakkale Formasyonu (Tmçk)

`Biga ve Gelibolu Yarımadaları'nda Çanakkale Boğazı'nın her iki kıyısı boyunca yüzeylenen Geç Miyosen yaşlı denizel çökeller ilk kez Şentürk ve Karaköse (1987) tarafından Çanakkale formasyonu olarak tanımlanmıştır. Çanakkale formasyonu çakıltaşı, kumtaşı, silttaşı, çamurtaşı, marn, kalkarenit ve oolitik kireçtaşlarından oluşur.`

`Çanakkale formasyonu olarak adlandırılan Geç Miyosen yaşlı denizel kayaçlar Trakya ve Gelibolu Yarımadası'nda değişik araştırmacılar tarafından pek çok farklı ad altında tanımlanmıştır. Çanakkale formasyonu Holmes (1966)'un Ergene formasyonu; Ünal (1967)'ın Ergene Grubu, Büyük Anafartalar formasyonu; Kellog (1973)'un Anafartalar ve Kilitbahir formasyonu; Saltık (1974)'ın Gelibolu formasyonu; Önem (1974)'in Eceabat formasyonu karşılığıdır.`

Formasyona yazılan `özel açıklama` ayrıca kullanıcı metni olarak eklenir.

## 14. Hidrojeoloji cümle motoru

### Akar ve kuru dere

- İkisi de yoksa:
  `İnceleme alanı ve yakın çevresinde akar veya kuru dere bulunmamaktadır.`
- Yalnız akar dere yoksa:
  `İnceleme alanı ve yakın çevresinde akar dere bulunmamaktadır.`
- Yalnız kuru dere yoksa:
  `İnceleme alanı ve yakın çevresinde kuru dere bulunmamaktadır.`
- Akar dere varsa:
  `İnceleme alanının {KONUM_IFADESI} akar dere bulunmaktadır.`
- Kuru dere varsa:
  `İnceleme alanının {KONUM_IFADESI} kuru dere yatağı bulunmaktadır.`

`{KONUM_IFADESI}` şu biçimlerden biri olur:

- `yaklaşık {MESAFE} m {YON}`
- `yaklaşık {MESAFE} m mesafede`
- `{YON}`
- `yakın çevresinde`

Yön ifadeleri: `kuzeyinde`, `kuzeydoğusunda`, `doğusunda`, `güneydoğusunda`,
`güneyinde`, `güneybatısında`, `batısında`, `kuzeybatısında`.

Otomatik sayısal hidrografya analizi yok sonucu verdiyse:

- `Kullanılan sayısal hidrografya verisine göre parselin {YARICAP} m yakın çevrede kayıtlı akar veya kuru dere saptanmamıştır.`
- `Kullanılan sayısal hidrografya verisine göre parselin {YARICAP} m yakın çevrede kayıtlı akar dere saptanmamıştır.`
- `Kullanılan sayısal hidrografya verisine göre parselin {YARICAP} m yakın çevrede kayıtlı kuru dere saptanmamıştır.`
- Yarıçap bilinmiyorsa `{YARICAP} m` yerine yalnız `yakın çevrede` kullanılır.
- KML/parsel sınırı değiştiyse:
  `Parsel sınırı değiştirildiğinden yakın çevredeki akar ve kuru dere durumu güncel sayısal verilerle yeniden doğrulanmalıdır.`

### Taşkın

- Yok:
  `Mevcut veriler ve arazi gözlemleri kapsamında inceleme alanını etkileyen bir taşkın riski belirlenmemiştir.`
- Var:
  `İnceleme alanında taşkın riski bulunduğu değerlendirildiğinden, ilgili kurum görüşleri doğrultusunda gerekli drenaj ve taşkın önlemleri projelendirilmelidir.`
- Belirsiz:
  `Mevcut veriler taşkın riskinin kesin olarak değerlendirilmesi için yeterli olmadığından, ilgili kurum görüşleri ve güncel taşkın haritaları dikkate alınmalıdır.`

### Denize uzaklık

- Mesafe sıfırsa:
  `İnceleme alanı denize kıyı konumundadır.`
- Mesafe varsa:
  `İnceleme alanı denize yaklaşık {MESAFE} m mesafededir.`
- Mesafe girilmemişse deniz cümlesi yazılmaz.

### Yeraltı suyu

- Rastlanmadı:
  `Yapılan sondajlarda yeraltı suyuna rastlanmamıştır.`
- Belirlenemedi:
  `Yapılan çalışmalar kapsamında yeraltı suyu seviyesi kesin olarak belirlenememiştir.`
- Tek seviye varsa:
  `Yapılan sondajlarda {DERINLIK} m derinlikte yeraltı suyuna rastlanmıştır.`
- Birden fazla seviye varsa:
  `Yapılan sondajlarda {MIN_DERINLIK}-{MAKS_DERINLIK} m derinlikleri arasında yeraltı suyuna rastlanmıştır.`
- Rastlandı seçilmiş fakat seviye yoksa:
  `Yapılan sondajlarda yeraltı suyuna rastlanmıştır.`

`Hidrojeoloji ek açıklaması` alanındaki metin paragrafın sonuna kullanıcı metni olarak eklenir.

## 15. Jeofizik sonuç cümlesi

- Yalnız Vs30 varsa:
  `Çalışma alanında yapılan jeofizik çalışmalar sonucunda Vs30={MIN-MAKS} m/sn olarak bulunmuştur.`
- Yalnız hâkim periyot varsa:
  `Çalışma alanında yapılan jeofizik çalışmalar sonucunda zemin hakim titreşim periyodu {MIN-MAKS}sn olarak bulunmuştur.`
- İkisi de varsa motorun mevcut birleşimi:
  `Çalışma alanında yapılan jeofizik çalışmalar sonucunda Vs30={MIN-MAKS} m/sn olarak, zemin hakim titreşim periyodu {MIN-MAKS}sn olarak bulunmuştur.`
- Değerlerin hepsi aynıysa aralık yerine tek değer yazılır.
- İki veri de yoksa cümle boş bırakılır.

## 16. YASS yalıtım ve drenaj önerisi

- YASS yoksa:
  `Yapılan sondaj çalışmaları sonucunda çalışma alanında yeraltı suyuna rastlanmamıştır. Ancak, olası yüzey ve atık sularının yapı temeline ve temelin oturacağı zemine sızarak meydana getirebileceği olumsuz etkiler göz önüne alınarak; su geçirgenliğini önlemek amacıyla standartlara uygun bir yalıtım projelendirilmeli ve suları temelden uzak tutacak etkin bir drenaj sistemi oluşturulmalıdır.`
- Tek YASS seviyesi varsa:
  `Yapılan sondaj çalışmaları sonucunda çalışma alanında -{DERINLIK}m derinlikte yeraltı suyuna rastlanmıştır. Yeraltı, yüzey ve atık sularının yapı temeline ve temelin oturacağı zemine sızarak meydana getirebileceği olumsuz etkiler göz önüne alınarak; su geçirgenliğini önlemek amacıyla standartlara uygun bir yalıtım projelendirilmeli ve suları temelden uzak tutacak etkin bir drenaj sistemi oluşturulmalıdır.`
- YASS aralığı varsa:
  `Yapılan sondaj çalışmaları sonucunda çalışma alanında -{MIN_DERINLIK}m ila -{MAKS_DERINLIK}m derinlikleri arasında yeraltı suyuna rastlanmıştır. Yeraltı, yüzey ve atık sularının yapı temeline ve temelin oturacağı zemine sızarak meydana getirebileceği olumsuz etkiler göz önüne alınarak; su geçirgenliğini önlemek amacıyla standartlara uygun bir yalıtım projelendirilmeli ve suları temelden uzak tutacak etkin bir drenaj sistemi oluşturulmalıdır.`

## 17. Jeolojik kesit giriş cümlesi

- İki veya daha fazla sondaj varsa:
  `Çalışma alanındaki seçili sondaj noktaları arasında jeolojik kesit oluşturulmuş ve sondaj profillerinde gözlenen birimler korele edilmiştir.`
- Yeterli sondaj yoksa:
  `Jeolojik kesit oluşturmak için yeterli sayıda sondaj kaydı bulunmamaktadır.`

## 18. Sonuç bölümü

### Sonuç girişi

- Konum varsa:
  `{KONUM} konumundaki {PROJE_ADI} için yürütülen zemin ve temel etüdü veri çalışmalarında elde edilen bulgular aşağıda özetlenmiştir.`
- Konum yoksa:
  `{PROJE_ADI} için elde edilen zemin etüdü verileri aşağıda özetlenmiştir.`

### Sonuç konumu

- `İnceleme alanı {KONUM} sınırlarında yer almaktadır.`
- Koordinatlar da varsa:
  `İnceleme alanı {KONUM} sınırlarında ve Enlem: {ENLEM}, Boylam: {BOYLAM} (WGS84) koordinatlarındadır.`
- Konum yoksa:
  `İnceleme alanının konum bilgileri tanımlanmamıştır.`

### Sonuç imar ve afet

`[SONUC_IMAR]`, 4. bölümdeki imar planı cümlelerini yeniden kullanır.

`[SONUC_AFET]`, 5. bölümdeki doğal afet cümlelerini yeniden kullanır.

### Kazı

- Kazı sınıfı ve güçlüğü yoksa:
  `Kazı sınıfı ve kazı güçlüğü, veri raporundaki bulgular kullanılarak geoteknik rapor kapsamında değerlendirilmelidir.`
- Yalnız kazı sınıfı varsa:
  `Çalışma alanı için kazı sınıfı {KAZI_SINIFI} olarak değerlendirilmiştir.`
- Yalnız kazı güçlüğü varsa:
  `Çalışma alanı için kazı güçlüğü {KAZI_GUCLUGU} olarak değerlendirilmiştir.`
- İkisi de varsa:
  `Çalışma alanı için kazı sınıfı {KAZI_SINIFI}, kazı güçlüğü {KAZI_GUCLUGU} olarak değerlendirilmiştir.`
- Kullanıcı kazı açıklaması yazmadıysa önlem cümlesi:
  `Kazı destek sistemi, şev güvenliği, drenaj ve komşu parsel önlemleri geoteknik rapor ve uygulama projesi kapsamında belirlenmelidir.`

Kullanıcının `kazı açıklaması` ve `sonuç ek açıklaması` metinleri otomatik cümle yerine/doğrudan eklenebilir.

## 19. Mevcut dahili şablonda kullanılmayan ama motorda hazır ana cümle alanları

Şu 16 etiket motor tarafından üretilebilir fakat mevcut dahili şablonda bulunmaz:

`[IKLIM_ACIKLAMA]`, `[DON_DURUM_ACIKLAMA]`, `[DOGAL_AFET_ACIKLAMA]`,
`[AKTIF_TEKTONIK_ACIKLAMA]`, `[AKTIF_FAY_GIRIS]`,
`[SISMIK_YONTEM_ACIKLAMA]`, `[MASW_YONTEM_ACIKLAMA]`,
`[MT_YONTEM_ACIKLAMA]`, `[MT_DEGERLENDIRME_ACIKLAMA]`,
`[ARASTIRMA_CUKURU_ACIKLAMA]`, `[SPT_GIRIS]`, `[SPT_TEKNIK_ACIKLAMA]`,
`[LAB_GIRIS]`, `[SONUC_KAZI]`, `[SONUC_KAZI_ONLEM]`,
`[SONUC_EK_ACIKLAMA]`.

Bu nedenle bu etiketlere ait cümlelerin kodda bulunması, mevcut dahili Word
şablonunda mutlaka görünecekleri anlamına gelmez. Kullanıcı tarafından seçilen özel
bir şablonda etiket bulunursa motor cümleyi üretir.

## 20. Cümle sayılmayan dinamik alanlar

Şu alanlar program tarafından doldurulur fakat birer cümle değildir:

- İl, ilçe, mahalle, mevki, pafta, ada, parsel ve proje adı.
- Kategori, zemin kategorisi, PGA, yerel zemin sınıfı.
- Jeofizik tarihi, SS/MT sayısı, kotlar, eğim ve koordinatlar.
- Bina, sondaj, SPT, PMT, kaya, laboratuvar ve jeofizik tablolarının hücreleri.
- Harita ve rapor görselleri.
- Geoteknik teslim paketindeki tablo başlıkları ve proje üst bilgisi.

## 21. Serbest metin üreten veya taşıyan alanlar

Aşağıdakilerin önceden sabit bir cümle listesi yoktur:

- Rapor Revizyon Merkezi'nde yapay zekanın önerdiği cümleler.
- Çevre, imar, afet, hidrojeoloji, aktif tektonik, laboratuvar, araştırma çukuru,
  kazı, sonuç ve jeolojik formasyon için kullanıcı tarafından yazılan ek açıklamalar.

Program bu kullanıcı metinlerini temizleyebilir ve sonuna nokta ekleyebilir; içeriğini
kural tabanlı olarak yeniden yazmaz.
