import base64
import zipfile
import shutil
import tempfile
from pathlib import Path
from openai import OpenAI
from playwright.sync_api import sync_playwright
from colorama import Fore
from config import Config

client = OpenAI(base_url=Config.AI_BASE_URL, api_key=Config.AI_API_KEY)

def load_prompt(key):
    """Carrega um prompt específico do arquivo prompts.txt."""
    try:
        prompt_file = Path(__file__).parent.parent / "prompts.txt"
        if not prompt_file.exists():
            return f"Erro: Arquivo {prompt_file} não encontrado."
        
        with open(prompt_file, "r", encoding="utf-8") as f:
            content = f.read()
            
        start_tag = f"[{key}]"
        if start_tag not in content:
            return f"Erro: Tag {start_tag} não encontrada no arquivo de prompts."
            
        parts = content.split(start_tag)
        prompt_part = parts[1].split("[")[0].strip()
        return prompt_part
    except Exception as e:
        return f"Erro ao carregar prompt: {str(e)}"

def check_visual_layout(epub_path, max_items=3):
    """
    Analisa layout visual.
    max_items: Número máximo de elementos para analisar (None para todos/Full scan).
    """
    results = [] # Lista de dicts: {analysis, image_url, location}
    
    try:
        epub_stem = Path(epub_path).stem
        img_dir = Path(f"reports/screenshots/{epub_stem}")
        img_dir.mkdir(parents=True, exist_ok=True)



        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            with zipfile.ZipFile(epub_path, 'r') as z:
                z.extractall(temp_path)
            
            html_files = sorted([f for f in temp_path.rglob("*") if f.suffix in ('.xhtml', '.html') and 'nav' not in f.name.lower()])
            
            if not html_files:
                return [{"analysis": "Aviso: Nenhum arquivo de conteúdo HTML encontrado.", "image_url": None}]

            processed_count = 0

            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page()
                page.set_viewport_size({"width": 800, "height": 1000})
                
                for html_file in html_files:
                    if max_items is not None and processed_count >= max_items:
                        break

                    file_url = html_file.as_uri()
                    page.goto(file_url)
                    page.wait_for_load_state("networkidle")
                    
                    # Encontra elementos complexos (excluindo listas wrapper padrão .limitador)
                    # Selector logic:
                    # - table: sempre complexo
                    # - div:not(.limitador) > ul: listas aninhadas em divs que NÃO sejam a wrapper padrão
                    # - div:not(.limitador) > ol: idem
                    elements = page.locator("table, div:not(.limitador) > ul, div:not(.limitador) > ol").all()
                    
                    # Se não tiver elementos complexos, tira um print da página genérica (apenas para o primeiro arquivo)
                    if not elements and processed_count == 0:
                         img_name = f"view_general_{html_file.stem}.png"
                         img_path = img_dir / img_name
                         page.screenshot(path=str(img_path))
                         
                         analysis, ai_model = analyze_image_with_ai(img_path, load_prompt("GENERAL_LAYOUT"))
                         results.append({
                             "location": html_file.name,
                             "type": "General Layout",
                             "image_url": f"screenshots/{epub_stem}/{img_name}",
                             "analysis": analysis,
                             "ai_model": ai_model
                         })
                         processed_count += 1
                         continue

                    for i, el in enumerate(elements):
                        if max_items is not None and processed_count >= max_items:
                            break
                        
                        if not el.is_visible(): continue

                        img_name = f"view_{html_file.stem}_{i}.png"
                        img_path = img_dir / img_name
                        
                        # Style tweak para melhor captura
                        page.evaluate("el => { el.style.padding = '20px'; el.style.backgroundColor = 'white'; }", el.element_handle())
                        el.screenshot(path=str(img_path))
                        
                        analysis, ai_model = analyze_image_with_ai(img_path, load_prompt("COMPLEX_STRUCTURE"))
                        
                        results.append({
                            "location": f"{html_file.name} (Elemento {i+1})",
                            "type": "Complex Structure",
                            "image_url": f"screenshots/{epub_stem}/{img_name}",
                            "analysis": analysis,
                            "ai_model": ai_model
                        })
                        processed_count += 1

                browser.close()
        
        if not results:
             return [{"analysis": "Nenhuma estrutura complexa relevante encontrada para análise.", "image_url": None}]

        return results

    except Exception as e:
        print(f"{Fore.RED}    [!] Erro na visão: {e}")
        return [{"analysis": f"Erro técnico: {str(e)}", "image_url": None}]

def analyze_image_with_ai(img_path, prompt):
    try:
        with open(img_path, "rb") as image_file:
            img_b64 = base64.b64encode(image_file.read()).decode('utf-8')

        print(f"{Fore.BLUE}    [IA] Enviando captura para análise visual...")
        response = client.chat.completions.create(
            model=Config.AI_MODEL, 
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}}
                ]
            }]
        )
        
        content = response.choices[0].message.content
        usage = {
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
            "total_tokens": response.usage.total_tokens
        }
        
        if not content:
            print(f"{Fore.RED}    [DEBUG] Resposta da IA vazia para análise visual.")
        else:
            print(f"{Fore.GREEN}    [OK] Análise visual concluída. Uso: {usage['prompt_tokens']} prompt, {usage['completion_tokens']} resposta.")
            
        return {
            "content": content,
            "model": response.model,
            "usage": usage
        }
    except Exception as e:
        print(f"{Fore.RED}    [DEBUG] Erro na API de IA (Visual): {e}")
        return {
            "content": f"Erro na API de IA: {e}",
            "model": "Erro/Desconhecido",
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        }

def get_ai_tech_advice(errors):
    """
    Envia lista de erros do EPubCheck para a IA e retorna diagnóstico e correção.
    """
    if not errors:
        print(f"{Fore.RED}    [DEBUG] Nenhuma mensagem recebida do EPubCheck.")
        return {"content": "", "model": "N/A", "usage": None}
    
    # DEBUG: Ver as severidades disponíveis
    severities = set(e.get('severity') for e in errors)
    print(f"{Fore.WHITE}    [DEBUG] Severidades encontradas nos logs: {severities}")

    # Filtra apenas erros importantes para não sobrecarregar
    critical_errors = [e for e in errors if e.get('severity', '').upper() in ['FATAL', 'ERROR']]
    print(f"{Fore.WHITE}    [DEBUG] Erros críticos após filtragem: {len(critical_errors)}")

    if not critical_errors:
        return {"content": "", "model": "N/A", "usage": None}

    error_summary = ""
    for idx, e in enumerate(critical_errors, 1):
        error_summary += f"ERRO {idx}:\n"
        error_summary += f"Local: {e['location']}\n"
        error_summary += f"Mensagem: {e['text']}\n"
        if e.get('snippet'):
            error_summary += f"Snippet: {e['snippet']}\n"
        error_summary += "-"*10 + "\n"

    system_prompt = load_prompt("AI_TECH_ADVICE")
    user_content = f"--- LOGS DO EPUBCHECK ---\n{error_summary}\n--- FIM DOS LOGS ---"

    print(f"{Fore.CYAN}    [DEBUG] Erros enviados para IA:\n{error_summary}")

    try:
        print(f"{Fore.BLUE}    [IA] Enviando logs para conselhos técnicos...")
        
        response = client.chat.completions.create(
            model=Config.AI_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            temperature=0.3
        )
        
        content = response.choices[0].message.content
        usage = {
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
            "total_tokens": response.usage.total_tokens
        }

        if not content:
            print(f"{Fore.RED}    [DEBUG] Resposta da IA vazia para conselhos técnicos.")
            # Se a resposta vier vazia mas houver erros, algo no modelo local falhou ou o prompt barrou tudo.
            content = "A IA não retornou sugestões para os erros fornecidos. Verifique se o modelo está carregado corretamente ou se os logs contêm caracteres que impedem a análise."
        else:
            print(f"{Fore.GREEN}    [OK] Conselhos técnicos recebidos. Uso: {usage['prompt_tokens']} prompt, {usage['completion_tokens']} resposta.")

        return {
            "content": content,
            "model": response.model,
            "usage": usage
        }
    except Exception as ex:
        print(f"{Fore.RED}    [DEBUG] Erro na API de IA (Conselhos): {ex}")
        return {
            "content": "",
            "model": "Erro/Desconhecido",
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        }