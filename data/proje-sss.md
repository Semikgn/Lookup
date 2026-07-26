# RAG Router TR — Sıkça Sorulan Sorular

## Bu proje nedir?

RAG Router TR, Microsoft Azure Foundry Local yaz okulu kapsamında geliştirilen,
tamamen çevrimdışı çalışan Türkçe odaklı bir yapay zekâ asistanıdır. Üç ana
bileşeni vardır: yerel dokümanlardan soru cevaplayan RAG katmanı, soruyu uygun
yerel modele yönlendiren akıllı router ve router'ın kararlarını besleyen Türkçe
benchmark/leaderboard sistemi.

## Router nasıl karar veriyor?

Gelen soru önce türüne göre sınıflandırılır: kod sorusu mu, doküman (RAG) sorusu
mu, yoksa genel bilgi/muhakeme sorusu mu? Ardından `bench/leaderboard.json`
dosyasındaki skorlara bakılır ve o kategoride en başarılı olan yerel model
seçilir. Seçim elle yazılmış sabit kurallarla değil, ölçülmüş benchmark
sonuçlarıyla yapılır. Seçilen model kullanılamıyorsa daha küçük bir yedek
modele düşülür (fallback).

## Hangi modeller kullanılıyor?

Donanım kısıtları nedeniyle küçük modeller tercih edilir: hızlı cevaplar için
qwen2.5-0.5b, genel sorular ve muhakeme için qwen3-4b, kod soruları için
qwen2.5-coder-1.5b, embedding için qwen3-embedding-0.6b. Tüm modeller Foundry
Local üzerinden, internet olmadan çalışır.

## Benchmark neyi ölçüyor?

Türkçe hazırlanmış yaklaşık 36 soruluk bir test seti üç kategoride (RAG, kod,
genel muhakeme) her modeli puanlar. Doğruluk, cevapta beklenen anahtar
ifadelerin geçip geçmediğine bakılarak; hız ise cevap gecikmesi (latency)
ölçülerek değerlendirilir. Sonuçlar `leaderboard.json` dosyasına yazılır.

## Neden vektör veritabanı yok?

Projedeki doküman sayısı küçük olduğu için embedding'ler SQLite'ta saklanır ve
arama NumPy ile kaba kuvvet kosinüs benzerliğiyle yapılır. Bu ölçekte ek bir
vektör veritabanı kurulum ve bakım yükü getirir ama ölçülebilir fayda sağlamaz.

## Proje kaç fazdan oluşuyor?

Dört fazdan: (1) Zemin — Foundry client ve CLI, (2) Offline RAG, (3) Türkçe
benchmark ve leaderboard, (4) Router ve web arayüzü. Her faz sonunda çalışan,
demo edilebilir bir çıktı hedeflenir.
