# RAG (Retrieval-Augmented Generation) Mimarisi

RAG, büyük dil modelinin cevabını üretmeden önce harici bir bilgi kaynağından
ilgili parçaları getirip (retrieval) prompt'a eklemesi tekniğidir. Böylece model,
eğitim verisinde olmayan güncel ya da özel dokümanlar hakkında da doğru cevap
verebilir ve halüsinasyon riski azalır.

## Bu Projedeki RAG Boru Hattı

1. **Ingest:** `data/` klasöründeki .txt, .md ve .pdf dosyaları paragraf bazlı
   parçalara (chunk) bölünür. Hedef parça boyutu yaklaşık 800 karakterdir.
2. **Embedding:** Her parça, qwen3-embedding-0.6b modeliyle 1024 boyutlu bir
   vektöre dönüştürülür.
3. **Depolama:** Vektörler SQLite veritabanında BLOB olarak saklanır. Bu projede
   bilinçli bir sadelik kararı olarak harici vektör veritabanı (Qdrant, FAISS,
   Chroma vb.) kullanılmaz.
4. **Arama:** Soru vektörü ile tüm parça vektörleri arasında Python/NumPy ile
   kaba kuvvet (brute-force) kosinüs benzerliği hesaplanır; en yüksek skorlu
   ilk k parça seçilir.
5. **Üretim:** Seçilen parçalar Türkçe bir sistem prompt'una bağlam olarak
   eklenir ve cevap yerel chat modelinden istenir.

## Kosinüs Benzerliği

İki vektör arasındaki kosinüs benzerliği, vektörlerin iç çarpımının normlarının
çarpımına bölünmesiyle bulunur. Değer 1'e yaklaştıkça anlamsal benzerlik artar.
Birkaç yüz ila birkaç bin parça için kaba kuvvet arama milisaniyeler içinde
tamamlanır; bu ölçekte vektör veritabanının getireceği ek karmaşıklık gereksizdir.

## Chunk Boyutu Neden Önemli?

Çok küçük parçalar bağlamı koparır, çok büyük parçalar ise gereksiz metinle
prompt'u şişirir ve benzerlik skorunu sulandırır. 500-1000 karakter arası,
paragraf sınırlarına saygılı bölme bu proje için iyi bir dengedir.
