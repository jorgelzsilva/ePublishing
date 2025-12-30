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
    
    try:
        with zipfile.ZipFile(epub_path, 'r') as z:
            xhtml_files = [f for f in z.namelist() if f.lower().endswith(('.xhtml', '.html'))]
            
            for file_path in xhtml_files:
                with z.open(file_path) as f:
                    content_bytes = f.read()
                    tree = etree.HTML(content_bytes)
                    
                    # 1. Extração do Gabarito (Answer Key) no final do arquivo
                    # Estrutura: p._1-Corpo (Atividade X) -> p._11-Corpo-sem-espacos (Resposta: Y)
                    gabarito = {}
                    atividade_headers = tree.xpath('//p[contains(@class, "_1-Corpo") and contains(text(), "Atividade")]')
                    for header in atividade_headers:
                        text = "".join(header.xpath('.//text()')).strip()
                        match = re.search(r'Atividade\s+(\d+)', text, re.IGNORECASE)
                        if match:
                            num = match.group(1)
                            # Pega os parágrafos seguintes para achar "Resposta:"
                            next_ps = header.xpath('following-sibling::p[contains(@class, "_11-Corpo-sem-espacos")]')
                            for p in next_ps:
                                p_text = "".join(p.xpath('.//text()')).strip()
                                if p_text.startswith("Resposta:"):
                                    ans = p_text.replace("Resposta:", "").strip()
                                    gabarito[num] = ans
                                    break
                    
                    # 2. Localiza Enunciados de Atividades
                    enunciados = tree.xpath('//p[contains(@class, "_c-Atividade-Enunciado")]')
                    
                    if enunciados:
                        logs.append(f"🛠️ <strong>Validando atividades em <code>{file_path}</code></strong>")
                        print(f"    [INFO] Validando atividades em {file_path}")
                    
                    all_ids = set(tree.xpath('//@id'))
                    
                    for enunciando in enunciados:
                        question_text = "".join(enunciando.xpath('.//text()')).strip()
                        num_match = re.match(r'^(\d+)', question_text)
                        num = num_match.group(1) if num_match else None
                        
                        logs.append(f"   🔹 Atividade {num or '?'}: \"{question_text[:60]}...\"")
                        
                        # Coleta contexto (elementos até o próximo enunciado)
                        context_elements = enunciando.xpath('following-sibling::*')
                        
                        is_multiple_choice = False
                        correct_option_found = None
                        
                        for el in context_elements:
                            # Se chegamos em outro enunciado, paramos este contexto
                            if el.get('class') == "_c-Atividade-Enunciado":
                                break
                            
                            # Verifica tags <a> ou <div> ou <input> com onclick
                            possible_interactive = [el] + el.xpath('.//input | .//div | .//a')
                            
                            for item in possible_interactive:
                                onclick = item.get('onclick')
                                if onclick and 'showMe' in onclick:
                                    # Extrai IDs do showMe
                                    ids_in_js = re.findall(r"'(.*?)'", onclick)
                                    for target_id in ids_in_js:
                                        if target_id not in all_ids:
                                            msg = f"❌ ID <code>{target_id}</code> não encontrado no arquivo (chamado em <code>showMe</code>)"
                                            logs.append(f"      └─ <span style='color:#e74c3c'>{msg}</span>")
                                            issues_found.append(f"{file_path}: {msg}")
                                    
                                    # Múltipla Escolha: Identifica a opção correta
                                    # O primeiro argumento de showMe é o que será exibido.
                                    # Se ele termina em 'C' (ex: opc2C), esta é a alternativa correta.
                                    if ids_in_js and ids_in_js[0].endswith('C') and item.tag == 'input':
                                        val = item.get('value', '').upper()
                                        if val:
                                            correct_option_found = val
                                            is_multiple_choice = True

                        # Comparação com Gabarito
                        if num in gabarito:
                            expected = gabarito[num]
                            if is_multiple_choice:
                                if correct_option_found == expected:
                                    logs.append(f"      ✅ Resposta ({correct_option_found}) bate com o Gabarito.")
                                else:
                                    msg = f"❌ Divergência: HTML marca <strong>{correct_option_found}</strong>, mas Gabarito diz <strong>{expected}</strong>"
                                    logs.append(f"      └─ <span style='color:#e74c3c'>{msg}</span>")
                                    issues_found.append(f"Atividade {num}: {msg}")
                            else:
                                # Dissertativa: Busca questaoConfira
                                confira_div = enunciando.xpath('following-sibling::div[contains(@id, "R")]//following-sibling::div[contains(@class, "questaoConfira")]')
                                # Como a estrutura pode variar, vamos buscar qualquer div questaoConfira no contexto
                                if not confira_div:
                                    for el in context_elements:
                                        if el.get('class') == "_c-Atividade-Enunciado": break
                                        if el.get('class') == "questaoConfira":
                                            confira_div = [el]
                                            break
                                
                                if confira_div:
                                    text_confira = "".join(confira_div[0].xpath('.//text()')).strip()
                                    # Compara os primeiros 50 chars para evitar problemas de formatação
                                    clean_c = re.sub(r'\s+', ' ', text_confira).lower()
                                    clean_g = re.sub(r'\s+', ' ', expected).lower()
                                    if clean_g[:50] in clean_c[:100] or clean_c[:50] in clean_g[:100]:
                                        logs.append(f"      ✅ Conteúdo 'Confira' validado com o Gabarito.")
                                    else:
                                        msg = f"❌ Conteúdo divergente no Gabarito da Atividade {num}"
                                        logs.append(f"      └─ <span style='color:#e74c3c'>{msg}</span>")
                                        issues_found.append(f"Atividade {num}: {msg}")
    
        return True, logs, issues_found
    except Exception as e:
        return False, [f"Erro ao processar atividades: {e}"], [str(e)]
