import zipfile
from lxml import etree
from colorama import Fore
import re

def check_toc_and_pagelist(epub_path):
    logs = []
    try:
        with zipfile.ZipFile(epub_path, 'r') as z:
            internal_files = [f.lower() for f in z.namelist()]
            internal_files_original = z.namelist()
            nav_file = next((f for f in z.namelist() if 'nav.xhtml' in f.lower()), None)
            ncx_file = next((f for f in z.namelist() if 'toc.ncx' in f.lower()), None)
            
            # Procura também o sumário visual (sumario.xhtml, toc.xhtml, contents.xhtml)
            visual_toc_file = next((f for f in z.namelist() if any(name in f.lower() for name in ['sumario.xhtml', 'toc.xhtml', 'contents.xhtml', 'sumário.xhtml'])), None)
            
            links_to_check = []
            pages_count = 0
            toc_type = ""

            # Prioriza Nav (EPUB 3)
            if nav_file:
                with z.open(nav_file) as f:
                    tree = etree.parse(f)
                    links_to_check = tree.xpath('//*[local-name()="nav" and contains(@*[local-name()="type"], "toc")]//*[local-name()="a"]')
                    pages = tree.xpath('//*[local-name()="nav" and contains(@*[local-name()="type"], "page-list")]//*[local-name()="li"]')
                    pages_count = len(pages)
                    toc_type = "Nav (EPUB 3)"
                    logs.append(f"📚 <strong>Sumário Técnico:</strong> {toc_type}")
                    logs.append(f"   └─ Arquivo: <code>{nav_file}</code>")
                    print(f"    [OK] Sumário Nav detectado.")

            # Se não achou links no Nav, tenta NCX (EPUB 2)
            if not links_to_check and ncx_file:
                with z.open(ncx_file) as f:
                    tree = etree.parse(f)
                    links_to_check = tree.xpath('//*[local-name()="navPoint"]')
                    pages = tree.xpath('//*[local-name()="pageTarget"]')
                    pages_count = len(pages)
                    toc_type = "NCX (EPUB 2)"
                    logs.append(f"📚 <strong>Sumário Técnico:</strong> {toc_type}")
                    logs.append(f"   └─ Arquivo: <code>{ncx_file}</code>")
                    print(f"    [OK] Sumário NCX detectado.")

            # Validação real dos links com detalhamento
            broken = 0
            valid_links = []
            broken_links = []
            
            for link in links_to_check:
                href = link.get('href') or link.xpath('.//*[local-name()="content"]/@src')
                label = "".join(link.xpath('.//text()')).strip()[:100]  # Texto do link (max 100 chars)
                
                if href:
                    clean_href = href[0].split('#')[0] if isinstance(href, list) else href.split('#')[0]
                    original_href = href[0] if isinstance(href, list) else href
                    
                    # Verifica se o arquivo existe dentro do zip (busca flexível)
                    if any(clean_href.lower() in f for f in internal_files):
                        valid_links.append({"label": label, "href": original_href, "target": clean_href})
                    else:
                        broken += 1
                        broken_links.append({"label": label, "href": original_href, "target": clean_href})
            
            # Logs detalhados dos links do sumário técnico
            logs.append(f"")
            logs.append(f"📖 <strong>Links do Sumário Técnico:</strong> {len(links_to_check)} itens")
            
            if broken > 0:
                msg = f"❌ {broken} links do sumário estão quebrados ou órfãos."
                logs.append(f"   └─ <span style='color:#e74c3c'>{msg}</span>")
                for bl in broken_links[:5]:
                    logs.append(f"      ⚠️ \"{bl['label']}\" → <code>{bl['target']}</code> (NÃO ENCONTRADO)")
                print(f"{Fore.RED}    [X] {msg}")
            else:
                msg = f"✅ {len(links_to_check)} links validados com sucesso."
                logs.append(f"   └─ <span style='color:#27ae60'>{msg}</span>")
                for vl in valid_links:
                    logs.append(f"      ✓ \"{vl['label']}\" → <code>{vl['target']}</code>")
                print(f"{Fore.GREEN}    [OK] {msg}")
            
            # ===== VALIDAÇÃO DO SUMÁRIO VISUAL (HTML) =====
            if visual_toc_file:
                logs.append(f"")
                logs.append(f"📑 <strong>Sumário Visual (HTML):</strong>")
                logs.append(f"   └─ Arquivo: <code>{visual_toc_file}</code>")
                print(f"    [OK] Sumário visual detectado: {visual_toc_file}")
                
                with z.open(visual_toc_file) as f:
                    content_bytes = f.read()
                    tree = etree.HTML(content_bytes)
                    
                    # Busca todos os links do sumário visual
                    visual_links = tree.xpath('//a[@href]')
                    
                    visual_valid = []
                    visual_broken = []
                    title_warnings = []
                    anchor_errors = []
                    label_content_errors = []
                    duplicate_links = {} # href -> count
                    
                    # Para detectar texto sem link, vamos coletar nós de texto fora de <a>
                    body = tree.xpath('//body')[0] if tree.xpath('//body') else tree
                    
                    for a_tag in visual_links:
                        href = a_tag.get('href', '')
                        
                        # Ignora links externos
                        if href.startswith('http') or href.startswith('mailto:'):
                            continue
                        
                        # Texto dentro da tag <a>
                        text_inside_a = "".join(a_tag.xpath('.//text()')).strip()
                        
                        # Detecção de duplicados
                        duplicate_links[href] = duplicate_links.get(href, 0) + 1
                        
                        # Verifica se o arquivo de destino existe
                        clean_href = href.split('#')[0]
                        anchor = href.split('#')[1] if '#' in href else None
                        
                        # Encontra o caminho correto do arquivo
                        toc_dir = "/".join(visual_toc_file.split('/')[:-1])
                        if toc_dir:
                            full_path = f"{toc_dir}/{clean_href}".replace('//', '/')
                        else:
                            full_path = clean_href
                        
                        file_exists = any(full_path.lower() in f.lower() for f in internal_files)
                        
                        if file_exists:
                            content_status = " ⏳" # Default status
                            
                            # Busca o arquivo real (mantendo camelcase se necessário)
                            actual_file_in_zip = next((f for f in internal_files_original if full_path.lower() in f.lower()), None)
                            
                            if actual_file_in_zip:
                                with z.open(actual_file_in_zip) as tf:
                                    target_content_bytes = tf.read()
                                    target_tree = etree.HTML(target_content_bytes)
                                    target_text_all = " ".join(target_tree.xpath('//body//text()')).lower()
                                    
                                    # 1. Verifica se o texto do link existe no destino (ignora se for muito curto como "Cap 1")
                                    if len(text_inside_a) > 5:
                                        # Normalização robusta: remove pontuação, espaços especiais e converte para minúsculo
                                        def norm(txt):
                                            t = re.sub(r'\s+', ' ', txt) # Normaliza espaços
                                            return re.sub(r'[^\w\s]', '', t).lower().strip()

                                        def norm_extreme(txt):
                                            # Remove absolutamente tudo que não for letra ou número
                                            return re.sub(r'[^\w]', '', txt).lower()

                                        clean_label = norm(text_inside_a)
                                        clean_target = norm(target_text_all)
                                        
                                        # Busca exata (normalizada)
                                        found = clean_label in clean_target
                                        
                                        # Se não achar, tenta remover prefixos como "Capítulo 1", "Parte 1", etc.
                                        if not found:
                                            # Remove prefixo: Palavra + Número + Pontuadores opcionais (suporta acentos)
                                            prefix_pattern = r'^(cap[ií]tulo|cap|parte|item|seç[aã]o|secao|unidade|ap[eê]ndice|apendice)\s+\d+[\s\.\-—–]*'
                                            shorter = re.sub(prefix_pattern, '', clean_label)
                                            if shorter != clean_label and shorter.strip():
                                                found = shorter.strip() in clean_target
                                            
                                            # Terceira tentativa: Normalização extrema (sem espaços)
                                            # Resolve problemas de palavras cortadas em múltiplos <span> (ex: <span>d</span><span>e</span>)
                                            if not found:
                                                found = norm_extreme(text_inside_a) in norm_extreme(target_text_all)

                                        if found:
                                            content_status = " <small style='color:#27ae60'>(Conteúdo verificado)</small>"
                                        else:
                                            content_status = " <small style='color:#e74c3c'>(⚠️ Texto não encontrado no conteúdo!)</small>"
                                            label_content_errors.append({
                                                "label": text_inside_a,
                                                "file": clean_href
                                            })
                                    else:
                                        content_status = " <small style='color:#bdc3c7'>(Texto curto, conteúdo ignorado)</small>"

                                    # 2. Verifica se a âncora existe no arquivo de destino
                                    if anchor:
                                        target_content = target_content_bytes.decode('utf-8', errors='ignore')
                                        if f'id="{anchor}"' not in target_content and f"id='{anchor}'" not in target_content:
                                            anchor_errors.append({"href": href, "anchor": anchor, "file": clean_href})
                            
                            visual_valid.append({
                                "label": text_inside_a[:100], 
                                "href": href, 
                                "target": clean_href,
                                "status": content_status
                            })
                        else:
                            visual_broken.append({"label": text_inside_a[:100], "href": href, "target": clean_href})
                    
                    # Detecção de texto solto no sumário (não vinculado a <a>) usando XPath
                    unlinked_nodes = body.xpath('.//text()[not(ancestor::a)]')
                    unlinked_text_parts = [re.sub(r'\s+', ' ', str(n)).strip() for n in unlinked_nodes if str(n).strip()]
                    unlinked = " ".join(unlinked_text_parts)
                    unlinked = re.sub(r'[\d\s\.\-–—\•\|]+', ' ', unlinked).strip()
                    
                    # Log dos resultados do sumário visual
                    logs.append(f"")
                    logs.append(f"📖 <strong>Links do Sumário Visual:</strong> {len(visual_valid) + len(visual_broken)} itens")
                    
                    if visual_broken:
                        logs.append(f"   └─ <span style='color:#e74c3c'>❌ {len(visual_broken)} links quebrados</span>")
                        for bl in visual_broken:
                            logs.append(f"      ⚠️ \"{bl['label']}\" → <code>{bl['target']}</code> (NÃO ENCONTRADO)")
                        print(f"{Fore.RED}    [X] Sumário visual: {len(visual_broken)} links quebrados")
                    else:
                        logs.append(f"   └─ <span style='color:#27ae60'>✅ {len(visual_valid)} links validados</span>")
                        print(f"{Fore.GREEN}    [OK] Sumário visual: {len(visual_valid)} links validados")
                    
                    # Mostra todos os links do sumário visual com status de verificação
                    for vl in visual_valid:
                        logs.append(f"      ✓ \"{vl['label']}\" → <code>{vl['target']}</code>{vl['status']}")
                    
                    # Relatório de duplicados
                    dups = [h for h, c in duplicate_links.items() if c > 1]
                    if dups:
                        logs.append(f"")
                        logs.append(f"🔄 <strong>Links Duplicados:</strong> {len(dups)} detectados")
                        for d in dups[:5]:
                            logs.append(f"   └─ <code>{d}</code> aparece {duplicate_links[d]} vezes")

                    # Inconsistência de Conteúdo (Texto do link não achado no destino)
                    if label_content_errors:
                        logs.append(f"")
                        logs.append(f"❓ <strong>Inconsistência de Conteúdo:</strong>")
                        for lce in label_content_errors[:10]:
                            logs.append(f"   └─ Texto <code>\"{lce['label']}\"</code> não encontrado em <code>{lce['file']}</code>")
                        print(f"{Fore.YELLOW}    [!] {len(label_content_errors)} títulos não encontrados no conteúdo de destino")

                    # Texto sem link
                    if len(unlinked) > 10:
                        logs.append(f"")
                        logs.append(f"⚠️ <strong>Texto sem link detectado no Sumário:</strong>")
                        logs.append(f"   └─ <em>\"{unlinked[:100]}...\"</em>")
                        print(f"{Fore.YELLOW}    [!] Texto sem link detectado no sumário visual")

                    # Warnings sobre títulos parcialmente fora do <a>
                    if title_warnings:
                        logs.append(f"")
                        logs.append(f"⚠️ <strong>Títulos parcialmente fora do &lt;a&gt;:</strong>")
                        for tw in title_warnings[:10]:
                            logs.append(f"   └─ \"{tw['title']}...\" tem texto fora: <code>{tw['outside']}</code>")
                        print(f"{Fore.YELLOW}    [!] {len(title_warnings)} títulos com texto fora do link")
                    
                    # Erros de âncoras não encontradas
                    if anchor_errors:
                        logs.append(f"")
                        logs.append(f"❌ <strong>Âncoras não encontradas:</strong>")
                        for ae in anchor_errors[:10]:
                            logs.append(f"   └─ <code>#{ae['anchor']}</code> não existe em <code>{ae['file']}</code>")
                        print(f"{Fore.RED}    [X] {len(anchor_errors)} âncoras não encontradas nos arquivos destino")
            
            # PageList
            if pages_count > 0:
                msg = f"✅ PageList detectada e validada ({pages_count} páginas)."
                logs.append(f"")
                logs.append(f"📄 <strong>PageList:</strong> {pages_count} páginas mapeadas")
                print(f"{Fore.GREEN}    [OK] {msg}")
            else:
                logs.append(f"")
                logs.append("ℹ️ Nenhuma PageList encontrada (opcional para EPUB 3).")

            return True, logs
    except Exception as e:
        msg = f"❌ Erro estrutural crítico: {e}"
        logs.append(msg)
        print(f"{Fore.RED}    [!] {msg}")
        return False, logs

# Lógica para validar se o ID do link existe no destino
def validate_anchor(zip_ref, href):
    if '#' not in href: return True # Link para o arquivo todo
    file_part, anchor = href.split('#')
    # Abre o arquivo de destino e procura o ID
    with zip_ref.open(file_part) as f:
        content = f.read().decode('utf-8')
        return f'id="{anchor}"' in content or f"id='{anchor}'" in content

def validate_pagelist_sequence(pages_nodes):
    """Verifica se a sequência de páginas (ex: 1, 2, 3) está correta."""
    sequence_errors = []
    last_val = 0
    
    for node in pages_nodes:
        # Extrai apenas os números do texto da página (ex: "Página 10" -> 10)
        label = "".join(node.xpath('.//text()')).strip()
        nums = re.findall(r'\d+', label)
        if nums:
            current_val = int(nums[0])
            if current_val != last_val + 1:
                sequence_errors.append(f"Salto detectado: de {last_val} para {current_val}")
            last_val = current_val
    return sequence_errors

def check_internal_integrity(epub_path, links):
    """Verifica se o ID de destino (#ancora) realmente existe no XHTML."""
    broken_anchors = []
    with zipfile.ZipFile(epub_path, 'r') as z:
        for link in links:
            href = link.get('href')
            if href and '#' in href:
                file_path, anchor = href.split('#')
                # Tenta abrir o arquivo de destino e buscar o ID
                try:
                    with z.open(file_path) as f:
                        content = f.read().decode('utf-8', errors='ignore')
                        if f'id="{anchor}"' not in content and f"id='{anchor}'" not in content:
                            broken_anchors.append(href)
                except:
                    continue # Arquivo não encontrado já é pego na validação de arquivo
    return broken_anchors

def get_typesetting_credit(epub_path):
    """
    Procura por arquivos de créditos ou rosto e extrai quem fez a editoração e/ou produção digital.
    """
    try:
        found_credits = []
        with zipfile.ZipFile(epub_path, 'r') as z:
            # Arquivos prováveis de conter créditos
            credit_files = [f for f in z.namelist() if any(name in f.lower() for name in ['credito', 'credit', 'rosto', 'copyright', 'copy'])]
            
            for file_path in credit_files:
                with z.open(file_path) as f:
                    content_bytes = f.read()
                    tree = etree.HTML(content_bytes)
                    
                    # Busca todos os parágrafos
                    paragraphs = tree.xpath('//p')
                    for p in paragraphs:
                        # Pega todo o texto dentro do parágrafo (incluindo spans internos)
                        full_text = "".join(p.xpath('.//text()')).strip()
                        
                        # Procura os termos Editoração ou Produção digital
                        if any(term in full_text for term in ["Editoração", "Produção digital", "Produção Digital"]):
                            if full_text not in found_credits:
                                found_credits.append(full_text)
            
        if found_credits:
            # Retorna os créditos encontrados separados por barra
            return " | ".join(found_credits)
            
        return "Não identificado"
    except Exception:
        return "Erro na extração"