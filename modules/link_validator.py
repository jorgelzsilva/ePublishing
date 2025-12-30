import httpx
import asyncio
import zipfile
import re
import warnings

# Suprimir avisos de SSL inseguro (já que estamos bypassando verificação para links externos)
warnings.filterwarnings("ignore", category=UserWarning) 
# Nota: httpx pode não emitir InsecureRequestWarning do urllib3, mas sim seus próprios logs.

async def check_url(client, url):
    retries = 3
    for i in range(retries):
        try:
            # Tenta HEAD primeiro
            response = await client.head(url, timeout=10.0)
            if response.status_code == 200:
                return {"url": url, "status": response.status_code}
            
            # Se falhar (ex: 405 Method Not Allowed ou 403), tenta GET
            response = await client.get(url, timeout=10.0)
            if response.status_code == 200:
                return {"url": url, "status": response.status_code}
                
        except Exception as e:
            if i == retries - 1:
                return {"url": url, "status": f"Erro: {str(e)}"}
            await asyncio.sleep(1) # Espera 1s antes de tentar novamente
            
    return {"url": url, "status": "Erro (Retries Esgotados)"}

from lxml import etree

async def validate_external_links(epub_path):
    """Extrai links http/https de tags <a> dentro do <body> e testa o status 200."""
    urls = set()
    with zipfile.ZipFile(epub_path, 'r') as z:
        for file in z.namelist():
            if file.lower().endswith(('.xhtml', '.html')):
                with z.open(file) as f:
                    content_bytes = f.read()
                    try:
                        tree = etree.HTML(content_bytes)
                        if tree is not None:
                            # XPath para pegar apenas hrefs de tags <a> dentro do body
                            found_hrefs = tree.xpath('//body//a/@href')
                            for href in found_hrefs:
                                if href.startswith(('http://', 'https://')):
                                    urls.update([href])
                    except Exception:
                        continue # Ignora erros de parsing em arquivos individuais

    if not urls: return []

    # Headers mais próximos de um navegador real
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Accept-Language": "en-US,en;q=0.9,pt-BR;q=0.8,pt;q=0.7",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1"
    }

    # Desabilitamos http2 para evitar fingerprints comuns de bots em http2
    async with httpx.AsyncClient(headers=headers, follow_redirects=True, http2=False, verify=False) as client:
        tasks = [check_url(client, url) for url in urls]
        print(f"    [INFO] Testando {len(urls)} links externos...")
        results = await asyncio.gather(*tasks)
        return results