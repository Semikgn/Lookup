# Foundry Local Nedir?

Foundry Local, Microsoft'un üretken yapay zekâ modellerini tamamen yerel makinede,
internet bağlantısı olmadan çalıştırmaya yarayan aracıdır. Modeller ONNX Runtime
üzerinde çalışır ve donanıma göre CPU, GPU ya da NPU hedefli varyantlar seçilir.

## Kurulum

Windows üzerinde kurulum winget ile yapılır:

    winget install Microsoft.FoundryLocal

Kurulumdan sonra `foundry --version` komutu sürüm numarasını gösterir.

## Servis Mimarisi

Foundry Local, arka planda bir daemon (servis) olarak çalışır. Servis,
OpenAI-uyumlu bir REST API sunar; bu sayede `openai` Python kütüphanesi sadece
`base_url` değiştirilerek yerel modellere yönlendirilebilir. Servisin portu
sabit değildir: her başlatmada değişebilir. Bu yüzden port asla koda gömülmemeli,
`foundry server status` komutunun JSON çıktısındaki `webUrls` alanından dinamik
olarak okunmalıdır.

## Önemli Komutlar

- `foundry server start` — servisi başlatır.
- `foundry server status` — servis durumu, URL ve PID bilgisi verir.
- `foundry model list` — katalogdaki modelleri listeler.
- `foundry model download <ad>` — modeli yerel önbelleğe indirir.
- `foundry model load <ad>` — modeli belleğe yükler.
- `foundry cache` — indirilen modellerin önbelleğini yönetir.

## Model Önbelleği

İndirilen modeller diskte saklanır ve `/v1/models` endpoint'inden sorgulanabilir.
Bir model REST API üzerinden kullanılmadan önce `foundry model load` komutuyla
açıkça belleğe yüklenmelidir; yüklenmemiş modele istek atılırsa servis
"model is not loaded" hatası döndürür. Sınırlı RAM'e sahip makinelerde model
değiştirirken önceki model `foundry model unload` ile bellekten çıkarılmalıdır.
