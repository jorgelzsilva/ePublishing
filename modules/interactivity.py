import zipfile
import re
from lxml import etree
from colorama import Fore

def validate_activities(epub_path):
    """
    Valida atividades interativas (múltipla escolha e dissertativas).
    Verifica se os IDs no onclick existem e se as respostas batem com o gabarito.
    """
    logs = []
    issues_found = []
    file_gabaritos = {}
    
    try:
        with zipfile.ZipFile(epub_path, 'r') as z:
            xhtml_files = [f for f in z.namelist() if f.lower().endswith(('.xhtml', '.html'))]
            
            # --- PASSO 1: Coleta Local de Gabaritos ---
            for file_path in xhtml_files:
                with z.open(file_path) as f:
                    content_bytes = f.read()
                    tree = etree.HTML(content_bytes)
                    
                    all_p = tree.xpath('//p')
                    for i, p_node in enumerate(all_p):
                        text = "".join(p_node.xpath('.//text()')).strip()
                        # Regex para identificar o início de uma resposta (Ex: "Atividade 1" ou "QUESTÃO 5")
                        match = re.search(r'(?:Atividade|QUESTÕES?|QUESTÃO)\s+(\d+)', text, re.IGNORECASE)
                        
                        if match:
                            num = match.group(1)
                            ans_full = ""
                            target_node = p_node
                            
                            # Se o próprio nó não tem "Resposta:", busca nos próximos 2 irmãos
                            found_res = "Resposta:" in text
                            if not found_res:
                                for offset in [1, 2]:
                                    if i + offset < len(all_p):
                                        next_text = "".join(all_p[i+offset].xpath('.//text()')).strip()
                                        if "Resposta:" in next_text:
                                            text = next_text
                                            target_node = all_p[i+offset]
                                            found_res = True
                                            break
                            
                            if found_res:
                                ans_label = text.split("Resposta:")[-1].strip().replace("//", "").strip()
                                
                                # Coleta comentário nos próximos 2 parágrafos
                                extra_text = ""
                                siblings = target_node.xpath('following-sibling::p')
                                for sib in siblings[:2]:
                                    sib_text = "".join(sib.xpath('.//text()')).strip()
                                    sib_class = (sib.get('class') or '').lower()
                                    if "comentário" in sib_text.lower() or "corpo" in sib_class or "resposta" in sib_class:
                                        extra_text = sib_text.replace("Comentário:", "").strip()
                                        break
                                
                                if not ans_label:
                                    sib = target_node.xpath('following-sibling::*[1]')
                                    if sib:
                                        if sib[0].tag == 'table': ans_full = "Tabela"
                                        elif sib[0].xpath('.//img'): ans_full = "Figura"
                                else:
                                    if len(ans_label) <= 4 and extra_text:
                                        ans_full = f"{ans_label}: {extra_text}"
                                    else:
                                        ans_full = ans_label if ans_label else extra_text
                            
                            if ans_full:
                                file_gabaritos.setdefault(file_path, {})[num] = ans_full

            # --- PASSO 2: Validação das Atividades ---
            for file_path in xhtml_files:
                with z.open(file_path) as f:
                    content_bytes = f.read()
                    tree = etree.HTML(content_bytes)
                    enunciados = tree.xpath('//p[contains(@class, "Atividade-Enunciado")]')
                    
                    if enunciados:
                        logs.append(f"<span style='font-family:monospace; color:var(--text-muted);'>[      INFO        ]</span> <strong>Atividades detectadas em <code>{file_path}</code></strong>")
                    
                    current_gabarito = file_gabaritos.get(file_path, {})
                    if not current_gabarito:
                        for g_path, g_content in file_gabaritos.items():
                            if "gabarito" in g_path.lower() or "respostas" in g_path.lower():
                                current_gabarito = g_content
                    
                    for enunciando in enunciados:
                        question_full_text = "".join(enunciando.xpath('.//text()')).strip()
                        num_match = re.search(r'(\d+)', question_full_text)
                        num = num_match.group(1) if num_match else None
                        q_snippet = f'"{question_full_text[:20]}..."' if len(question_full_text) > 20 else f'"{question_full_text}"'
                        
                        context_elements = enunciando.xpath('following-sibling::*')
                        is_multiple_choice = False
                        correct_option_found = None
                        
                        for el in context_elements:
                            if "Atividade-Enunciado" in (el.get('class') or ''): break
                            
                            inputs = el.xpath('.//input[@type="radio"]')
                            if inputs:
                                is_multiple_choice = True
                                for item in inputs:
                                    onclick = item.get('onclick')
                                    if onclick and 'showMe' in onclick:
                                        args = re.findall(r"'(.*?)'", onclick)
                                        if args and args[0].endswith('C'):
                                            correct_option_found = (item.get('value') or '').upper()
                                            break
                            if is_multiple_choice and correct_option_found: break
                            
                            # Tenta detectar se há botões A), B), C) mesmo sem radio
                            text_el = "".join(el.xpath('.//text()')).strip()
                            if re.match(r'^[A-E]\)', text_el):
                                is_multiple_choice = True

                        if num in current_gabarito:
                            expected = current_gabarito[num]
                            ans_snippet = f'"{expected[:30]}..."' if len(expected) > 30 else f'"{expected}"'
                            
                            if is_multiple_choice and correct_option_found:
                                exp_label = expected[0].upper() if expected and expected[0].isalpha() else ""
                                if correct_option_found == exp_label:
                                    logs.append(f"      <span style='font-family:monospace; font-weight:bold; color:#27ae60;'>[      PASSOU      ]</span> {q_snippet} Resposta {correct_option_found}: {ans_snippet}")
                                else:
                                    msg = f"Divergência: HTML marca <strong>{correct_option_found}</strong>, mas Gabarito diz <strong>{expected}</strong>"
                                    logs.append(f"      <span style='font-family:monospace; font-weight:bold; color:#c0392b;'>[      FALHOU      ]</span> {q_snippet} └─ {msg}")
                                    issues_found.append(f"Atividade {num}: {msg}")
                            else:
                                confira_text = ""
                                for el in context_elements:
                                    if "Atividade-Enunciado" in (el.get('class') or ''): break
                                    cl = (el.get('class') or '')
                                    if cl and ("Confira" in cl or "questaoConfira" in cl):
                                        confira_text = "".join(el.xpath('.//text()')).strip()
                                        break
                                    sub = el.xpath('.//*[contains(@class, "Confira") or contains(@class, "questaoConfira")]')
                                    if sub:
                                        confira_text = "".join(sub[0].xpath('.//text()')).strip()
                                        break
                                
                                match_discursive = False
                                if confira_text:
                                    clean_c = re.sub(r'\s+', ' ', confira_text).lower()
                                    clean_g = re.sub(r'\s+', ' ', expected).lower()
                                    if clean_g[:40] in clean_c or clean_c[:40] in clean_g:
                                        match_discursive = True
                                
                                if match_discursive or expected in ["Tabela", "Figura"]:
                                    logs.append(f"      <span style='font-family:monospace; font-weight:bold; color:#27ae60;'>[      PASSOU      ]</span> {q_snippet} Resposta: {ans_snippet}")
                                elif expected:
                                    msg = f"Conteúdo divergente ou interatividade não encontrada para Atividade {num}"
                                    logs.append(f"      <span style='font-family:monospace; font-weight:bold; color:#c0392b;'>[      FALHOU      ]</span> {q_snippet} └─ {msg}")
                                    issues_found.append(f"Atividade {num}: {msg}")
    
        return True, logs, issues_found
    except Exception as e:
        return False, [f"Erro ao processar atividades: {e}"], [str(e)]
