import zipfile
from lxml import etree
from colorama import Fore
import re
import os
import posixpath

def check_toc_and_pagelist(epub_path):
    logs = []
    try:
        with zipfile.ZipFile(epub_path, 'r') as z:
            internal_files = [f.lower() for f in z.namelist()]
            internal_files_original = z.namelist()
            nav_file = next((f for f in z.namelist() if 'nav.xhtml' in f.lower()), None)
            ncx_file = next((f for f in z.namelist() if 'toc.ncx' in f.lower()), None)
            
            # Se não achou nav.xhtml, tenta encontrar qualquer arquivo que pareça ser um Nav EPUB 3
            if not nav_file:
                for f_name in z.namelist():
                    if f_name.lower().endswith(('.xhtml', '.html')):
                        with z.open(f_name) as f:
                            head = f.read(1024).decode('utf-8', errors='ignore').lower()
                            if '<nav' in head:
                                nav_file = f_name
                                break

            # Procura também o sumário visual (priorizando sumario.xhtml)
            names_to_check = ['sumario.xhtml', 'sumário.xhtml']
            visual_toc_file = next((f for f in z.namelist() if any(name in f.lower() for name in names_to_check)), None)
            
            # Se não achou sumário, tenta outros nomes comuns
            if not visual_toc_file:
                visual_toc_file = next((f for f in z.namelist() if any(name in f.lower() for name in ['toc.xhtml', 'contents.xhtml'])), None)

            links_to_check = []
            pages_data = [] # Lista de dicionários {"label": str, "href": str, "source": str}
            toc_type = ""

            # Prioriza Nav (EPUB 3)
            if nav_file:
                with z.open(nav_file) as f:
                    try:
                        tree = etree.parse(f)
                        links_to_check = tree.xpath('//*[local-name()="nav" and (contains(@*[local-name()="type"], "toc") or contains(@role, "toc"))]//*[local-name()="a"]')
                        pages_nodes = tree.xpath('//*[local-name()="nav" and (contains(@*[local-name()="type"], "page-list") or contains(@role, "pagelist"))]//*[local-name()="a"]')
                        for p in pages_nodes:
                            pages_data.append({
                                "label": "".join(p.xpath('.//text()')).strip(),
                                "href": p.get('href', ''),
                                "source": nav_file
                            })
                        toc_type = "Nav (EPUB 3)"
                        if links_to_check:
                            logs.append(f"📚 <strong>Sumário Técnico:</strong> {toc_type}")
                            logs.append(f"   └─ Arquivo: <code>{nav_file}</code>")
                            print(f"    [      PASSOU      ] Sumário Nav detectado.")
                    except:
                        pass

            # Se não achou links no Nav, tenta NCX (EPUB 2)
            if not links_to_check and ncx_file:
                with z.open(ncx_file) as f:
                    tree = etree.parse(f)
                    links_to_check = tree.xpath('//*[local-name()="navPoint"]')
                    if not pages_data:
                        pages_nodes = tree.xpath('//*[local-name()="pageTarget"]')
                        for p in pages_nodes:
                            label = "".join(p.xpath('.//*[local-name()="navLabel"]//*[local-name()="text"]/text()')).strip()
                            href = p.xpath('.//*[local-name()="content"]/@src')
                            pages_data.append({
                                "label": label,
                                "href": href[0] if href else "",
                                "source": ncx_file
                            })
                    toc_type = "NCX (EPUB 2)"
                    logs.append(f"📚 <strong>Sumário Técnico:</strong> {toc_type}")
                    logs.append(f"   └─ Arquivo: <code>{ncx_file}</code>")
                    print(f"    [      PASSOU      ] Sumário NCX detectado.")
            
            # Se não achou PageList no Nav ou NCX, tenta no Sumário Visual (EPUB 3 structure)
            if not pages_data and visual_toc_file:
                with z.open(visual_toc_file) as f:
                    tree = etree.HTML(f.read())
                    pages_nodes = tree.xpath('//*[(@*[contains(local-name(), "type") and .="page-list"] or contains(@role, "pagelist"))]//*[local-name()="a"]')
                    for p in pages_nodes:
                        pages_data.append({
                            "label": "".join(p.xpath('.//text()')).strip(),
                            "href": p.get('href', ''),
                            "source": visual_toc_file
                        })

            # Fallback Brute-force: Escaneia todos os arquivos em busca de marcadores de página individuais
            if not pages_data:
                for f_name in z.namelist():
                    if f_name.lower().endswith(('.xhtml', '.html')):
                        with z.open(f_name) as f:
                            content = f.read().decode('utf-8', errors='ignore')
                            # Busca por marcadores e seus atributos
                            # Regex para pegar o marcador e tentar extrair id e label/text
                            marker_matches = re.finditer(r'<[^>]+(?:epub:type|role)=["\'](?:doc-)?pagebreak["\'][^>]*>', content, re.IGNORECASE)
                            for match in marker_matches:
                                tag_full = match.group(0)
                                pid = re.search(r'id=["\']([^"\']+)["\']', tag_full, re.IGNORECASE)
                                label = re.search(r'aria-label=["\']([^"\']+)["\']', tag_full, re.IGNORECASE) or re.search(r'title=["\']([^"\']+)["\']', tag_full, re.IGNORECASE)
                                
                                pages_data.append({
                                    "label": label.group(1) if label else (pid.group(1) if pid else "?"),
                                    "href": f"{f_name}#{pid.group(1)}" if pid else f_name,
                                    "source": "Scan Bruto"
                                })
                if pages_data:
                    logs.append(f"📄 <strong>PageList detectada via Scan de Marcadores:</strong> {len(pages_data)} encontrados.")

            def resolve_epub_path(base_file, target_href):
                clean_target = target_href.split('#')[0]
                base_dir = posixpath.dirname(base_file)
                if base_dir:
                    full = posixpath.join(base_dir, clean_target)
                else:
                    full = clean_target
                return posixpath.normpath(full).replace('\\', '/')

            # Validação real dos links com detalhamento
            broken = 0
            valid_links = []
            broken_links = []
            
            for link in links_to_check:
                href = link.get('href') or link.xpath('.//*[local-name()="content"]/@src')
                label = "".join(link.xpath('.//text()')).strip()[:100]  # Texto do link (max 100 chars)
                
                if href:
                    original_href = href[0] if isinstance(href, list) else href
                    # O base_file para o sumário técnico (Nav/NCX) é o próprio nav_file ou ncx_file
                    source_file = nav_file if nav_file and links_to_check in tree.xpath('//*[local-name()="nav" and (contains(@*[local-name()="type"], "toc") or contains(@role, "toc"))]//*[local-name()="a"]') else ncx_file
                    # Na verdade, links_to_check vem de um dos dois. Vamos simplificar:
                    base_for_tech = nav_file if nav_file else ncx_file
                    
                    full_path = resolve_epub_path(base_for_tech, original_href)
                    
                    # Verifica se o arquivo existe dentro do zip (busca flexível)
                    if any(full_path.lower() == f.lower() for f in internal_files):
                        valid_links.append({"label": label, "href": original_href, "target": full_path})
                    else:
                        broken += 1
                        broken_links.append({"label": label, "href": original_href, "target": full_path})
            
            # Logs detalhados dos links do sumário técnico
            logs.append(f"")
            logs.append(f"📖 <strong>Links do Sumário Técnico:</strong> {len(links_to_check)} itens")
            
            if broken > 0:
                msg = f"{broken} links do sumário estão quebrados ou órfãos."
                logs.append(f"   └─ <span style='font-family:monospace; font-weight:bold; color:#c0392b;'>[ FALHOU ]</span> └─ {msg}")
                for bl in broken_links:
                    logs.append(f"      <span style='font-family:monospace; color:#c0392b;'>[ FALHOU ]</span> \"{bl['label']}\" → <code>{bl['target']}</code> (NÃO ENCONTRADO)")
                print(f"{Fore.RED}    [      FALHOU      ] {msg}")
            else:
                msg = f"{len(links_to_check)} links validados com sucesso."
                logs.append(f"   └─ <span style='font-family:monospace; font-weight:bold; color:#27ae60;'>[ PASSOU ]</span> └─ {msg}")
                for vl in valid_links:
                    logs.append(f"      <span style='font-family:monospace; color:#27ae60;'>[ PASSOU ]</span> \"{vl['label']}\" → <code>{vl['target']}</code>")
                print(f"{Fore.GREEN}    [      PASSOU      ] {msg}")
            
            # ===== VALIDAÇÃO DO SUMÁRIO VISUAL (HTML) =====
            if visual_toc_file:
                logs.append(f"")
                logs.append(f"📑 <strong>Sumário Visual (HTML):</strong>")
                logs.append(f"   └─ Arquivo: <code>{visual_toc_file}</code>")
                print(f"    [      PASSOU      ] Sumário visual detectado: {visual_toc_file}")
                
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
                        
                        # Encontra o caminho correto do arquivo resolve relativo ao visual_toc_file
                        full_path = resolve_epub_path(visual_toc_file, href)
                        
                        file_exists = any(full_path.lower() == f.lower() for f in internal_files)
                        
                        if file_exists:
                            content_status = " ⏳" # Default status
                            
                            # Busca o arquivo real (mantendo camelcase se necessário)
                            actual_file_in_zip = next((f for f in internal_files_original if full_path.lower() in f.lower()), None)
                            
                            if actual_file_in_zip:
                                with z.open(actual_file_in_zip) as tf:
                                    target_content_bytes = tf.read()
                                    target_tree = etree.HTML(target_content_bytes)
                                    
                                    # Coleta texto de todos os nós de texto (preserva ordem e resolve aninhamento)
                                    all_text = " ".join(target_tree.xpath('//body//text()'))
                                    # Também coleta atributos que podem conter o título (comum em Secad)
                                    attr_texts = " ".join(target_tree.xpath('//body//@title | //body//@aria-label | //body//@alt'))
                                    
                                    target_text_all = (all_text + " " + attr_texts).lower()
                                    
                                    # 1. Verifica se o texto do link existe no destino (ignora se for muito curto como "Cap 1")
                                    if len(text_inside_a) > 2:
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
                                        
                                        if not found:
                                            # Tenta remover prefixos (Capítulo X, Parte Y, etc.)
                                            # Palavra + Número + Pontuadores opcionais
                                            prefix_pattern = r'^(cap[ií]tulo|cap|parte|item|seç[aã]o|secao|unidade|ap[eê]ndice|apendice|t[óo]pico)\s+\d+[\s\.\-—–]*'
                                            shorter = re.sub(prefix_pattern, '', clean_label)
                                            if shorter != clean_label and shorter.strip():
                                                found = shorter.strip() in clean_target

                                        if found:
                                            content_status = "<span style='font-family:monospace; color:#27ae60;'>[ PASSOU ]</span> (Conteúdo verificado) "
                                        else:
                                            content_status = "<span style='font-family:monospace; color:#e74c3c;'>[ FALHOU ]</span> (⚠️ Texto não encontrado!) "
                                            label_content_errors.append({
                                                "label": text_inside_a,
                                                "file": actual_file_in_zip  # Mantém a correção do log (nome do arquivo)
                                            })
                                    else:
                                        content_status = "<small style='color:#bdc3c7'>(Texto curto, conteúdo ignorado)</small> "

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
                    
                    # Filtra termos técnicos comuns que não são títulos de verdade
                    ignore_terms = ['contents', 'landmarks', 'sumário', 'sumario', 'índice', 'indice', 'page list', 'tabela de conteúdos']
                    if any(term in unlinked.lower() for term in ignore_terms) and len(unlinked) < 50:
                        unlinked = ""
                    
                    # Log dos resultados do sumário visual
                    logs.append(f"")
                    logs.append(f"📖 <strong>Links do Sumário Visual:</strong> {len(visual_valid) + len(visual_broken)} itens")
                    
                    if visual_broken:
                        logs.append(f"   └─ <span style='font-family:monospace; font-weight:bold; color:#c0392b;'>[ FALHOU ]</span> {len(visual_broken)} links quebrados")
                        for bl in visual_broken:
                            logs.append(f"      <span style='font-family:monospace; color:#c0392b;'>[ FALHOU ]</span> \"{bl['label']}\" → <code>{bl['target']}</code> (NÃO ENCONTRADO)")
                        print(f"{Fore.RED}    [      FALHOU      ] Sumário visual: {len(visual_broken)} links quebrados")
                    else:
                        logs.append(f"   └─ <span style='font-family:monospace; font-weight:bold; color:#27ae60;'>[ PASSOU ]</span> {len(visual_valid)} links validados")
                        print(f"{Fore.GREEN}    [      PASSOU      ] Sumário visual: {len(visual_valid)} links validados")
                    
                    # Mostra todos os links do sumário visual com status de verificação
                    for vl in visual_valid:
                        logs.append(f"      {vl['status']} \"{vl['label']}\" → <code>{vl['target']}</code>")
                    
                    # Relatório de duplicados
                    dups = [h for h, c in duplicate_links.items() if c > 1]
                    if dups:
                        logs.append(f"")
                        logs.append(f"🔄 <strong>Links Duplicados:</strong> {len(dups)} detectados")
                        for d in dups:
                            logs.append(f"   └─ <code>{d}</code> aparece {duplicate_links[d]} vezes")

                    # Inconsistência de Conteúdo (Texto do link não achado no destino)
                    if label_content_errors:
                        logs.append(f"")
                        logs.append(f"❓ <strong>Inconsistência de Conteúdo:</strong>")
                        for lce in label_content_errors:
                            logs.append(f"   └─ <span style='font-family:monospace; color:#f39c12;'>[      AVISO       ]</span> Texto <code>\"{lce['label']}\"</code> não encontrado em <code>{lce['file']}</code>")
                        print(f"{Fore.YELLOW}    [      AVISO       ] {len(label_content_errors)} títulos não encontrados no conteúdo de destino")

                    # Texto sem link
                    if len(unlinked) > 10:
                        logs.append(f"")
                        logs.append(f"⚠️ <strong>Texto sem link detectado no Sumário:</strong>")
                        logs.append(f"   └─ <span style='font-family:monospace; color:#f39c12;'>[      AVISO       ]</span> <em>\"{unlinked[:100]}...\"</em>")
                        print(f"{Fore.YELLOW}    [      AVISO       ] Texto sem link detectado no sumário visual")

                    # Warnings sobre títulos parcialmente fora do <a>
                    if title_warnings:
                        logs.append(f"")
                        logs.append(f"⚠️ <strong>Títulos parcialmente fora do &lt;a&gt;:</strong>")
                        for tw in title_warnings:
                            logs.append(f"   └─ \"{tw['title']}...\" tem texto fora: <code>{tw['outside']}</code>")
                        print(f"{Fore.YELLOW}    [!] {len(title_warnings)} títulos com texto fora do link")
                    
                    # Erros de âncoras não encontradas
                    if anchor_errors:
                        logs.append(f"")
                        logs.append(f"❌ <strong>Âncoras não encontradas:</strong>")
                        for ae in anchor_errors:
                            logs.append(f"   └─ <span style='font-family:monospace; color:#c0392b;'>[ FALHOU ]</span> <code>#{ae['anchor']}</code> não existe em <code>{ae['file']}</code>")
                        print(f"{Fore.RED}    [      FALHOU      ] {len(anchor_errors)} âncoras não encontradas nos arquivos destino")
            
            # Validação Modular da PageList
            if pages_data:
                pl_ok, pl_logs = validate_pagelist_integrity(z, pages_data)
                logs.extend(pl_logs)
            else:
                logs.append("ℹ️ Nenhuma PageList encontrada (opcional para EPUB 3).")
                print(f"{Fore.YELLOW}    [      AVISO       ] Nenhuma PageList encontrada.")

            return True, logs
    except Exception as e:
        msg = f"Erro estrutural crítico: {e}"
        logs.append(f"<span style='font-family:monospace; color:#c0392b;'>[      FALHOU      ]</span> {msg}")
        print(f"{Fore.RED}    [      FALHOU      ] {msg}")
        return False, logs

def validate_pagelist_integrity(z, pages_data):
    """
    Função dedicada para validar a integridade da lista de páginas.
    Verifica sequência numérica e existência de IDs.
    """
    logs = []
    if not pages_data:
        return True, []

    logs.append(f"📄 <strong>Validando PageList:</strong> {len(pages_data)} itens detectados.")
    
    # 1. Validação de Sequência Numérica
    sequence_errors = []
    last_val = 0
    duplicate_pages = {}
    
    for i, p in enumerate(pages_data):
        label = p.get('label', '')
        # Extrai o primeiro número encontrado no label
        nums = re.findall(r'\d+', label)
        if nums:
            current_val = int(nums[0])
            if last_val != 0 and current_val != last_val + 1:
                # Se for o mesmo número, é duplicado
                if current_val == last_val:
                    duplicate_pages[current_val] = duplicate_pages.get(current_val, 0) + 1
                else:
                    sequence_errors.append(f"Salto: {last_val} → {current_val} (Item {i+1})")
            last_val = current_val

    if sequence_errors:
        logs.append(f"   └─ <span style='font-family:monospace; color:#f39c12;'>[ AVISO  ]</span> ⚠️ Sequência numérica com saltos: {', '.join(sequence_errors)}")
    if duplicate_pages:
        dup_list = [str(k) for k in duplicate_pages.keys()]
        logs.append(f"   └─ <span style='font-family:monospace; color:#c0392b;'>[ FALHOU ]</span> Páginas repetidas detectadas: {', '.join(dup_list)}")

    # 2. Validação de Existência de IDs (Âncoras)
    broken_ids = []
    internal_files = [f.lower() for f in z.namelist()]
    
    # Cache de arquivos já verificados para performance
    content_cache = {}

    for p in pages_data:
        href = p.get('href', '')
        if not href: continue
        
        target_file = href.split('#')[0]
        anchor = href.split('#')[1] if '#' in href else None
        
        # Resolve caminho relativo (se o source for em subpasta)
        source_file = p.get('source', '')
        if source_file and '/' in source_file and not target_file.startswith(('/', '..')):
            toc_dir = "/".join(source_file.split('/')[:-1])
            full_path = f"{toc_dir}/{target_file}".replace('//', '/').lower()
        else:
            full_path = target_file.lower()

        # Verifica se o arquivo existe
        actual_file = next((f for f in z.namelist() if full_path in f.lower()), None)
        if not actual_file:
            broken_ids.append(f"Arquivo não localizado: <code>{target_file}</code>")
            continue

        # Verifica ID se houver
        if anchor:
            if actual_file not in content_cache:
                with z.open(actual_file) as f:
                    content_cache[actual_file] = f.read().decode('utf-8', errors='ignore')
            
            content = content_cache[actual_file]
            if f'id="{anchor}"' not in content and f"id='{anchor}'" not in content:
                broken_ids.append(f"ID <code>#{anchor}</code> não encontrado em <code>{actual_file}</code>")

    if broken_ids:
        logs.append(f"   └─ <span style='font-family:monospace; color:#c0392b;'>[ FALHOU ]</span> Erros de destino ({len(broken_ids)}):")
        for error in broken_ids:
            logs.append(f"      <span style='font-family:monospace; color:#c0392b;'>[ FALHOU ]</span> {error}")
    else:
        logs.append(f"   └─ <span style='font-family:monospace; color:#27ae60;'>[ PASSOU ]</span> Todos os destinos (arquivos e IDs) foram validados.")

    # Status final da PageList
    overall_ok = len(broken_ids) == 0 and not duplicate_pages
    return overall_ok, logs

# Lógica para validar se o ID do link existe no destino
def validate_anchor(zip_ref, href):
    if '#' not in href: return True # Link para o arquivo todo
    file_part, anchor = href.split('#')
    # Abre o arquivo de destino e procura o ID
    with zip_ref.open(file_part) as f:
        content = f.read().decode('utf-8')
        return f'id="{anchor}"' in content or f"id='{anchor}'" in content



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

def check_filenames(epub_path):
    """
    Verifica se os nomes de arquivos dentro do EPUB seguem as restrições da plataforma:
    A-Z, a-z, 0-9, _, - (e o ponto para extensões e barra para diretórios)
    """
    invalid_files = []
    # Regex para permitir apenas Alfanuméricos, Underscore, Dash, Ponto e Barra
    # Nota: A mensagem da plataforma não citou ponto nem barra explicitamente, 
    # mas são essenciais para caminhos e extensões de arquivos.
    pattern = re.compile(r'^[A-Za-z0-9_\-\./]+$')
    
    try:
        with zipfile.ZipFile(epub_path, 'r') as z:
            for file_info in z.infolist():
                if not pattern.match(file_info.filename):
                    invalid_files.append(file_info.filename)
        
        return invalid_files
    except Exception:
        return []