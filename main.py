import os
import time
import glob
import json
import subprocess
import shutil
import zipfile
from pathlib import Path
from colorama import init, Fore

# Importação dos seus módulos (certifique-se que os nomes batem com os arquivos na pasta modules)
from modules.structural import check_toc_and_pagelist, get_typesetting_credit
from modules.css_checker import validate_css_rules, validate_limitador_and_structures
from modules.vision_ai import check_visual_layout, get_ai_tech_advice
import asyncio
from modules.link_validator import validate_external_links
from modules.interactivity import validate_activities

# CONFIGURAÇÕES
ENABLE_VISION_AI = False # Desativado por padrão

init(autoreset=True)

def run_epubcheck(epub_path):
    jar_path = "epubcheck-5.1.0/epubcheck.jar"
    report_json = Path(f"reports/{Path(epub_path).stem}_check.json")
    command = ["java", "-jar", jar_path, epub_path, "--json", str(report_json)]
    subprocess.run(command, check=False, capture_output=True)
    
    summary = {"FATAL": 0, "ERROR": 0, "WARNING": 0, "USAGE": 0, "messages": []}
    if report_json.exists():
        with open(report_json, 'r', encoding='utf-8') as f:
            data = json.load(f)
            msgs = data.get('messages', [])
            
            # Cache de arquivos para não ler repetidamente o mesmo arquivo do zip
            file_cache = {}

            for m in msgs:
                sev = m.get('severity', 'UNKNOWN')
                # A contagem será feita por localização para bater com a tabela
                
                locations = m.get('locations', [])
                if locations:
                    for loc in locations:
                        file_path = loc.get('path', 'N/A')
                        line_no = loc.get('line', -1)
                        col = loc.get('column', -1)
                        
                        # Tenta extrair o conteúdo da linha se houver localização
                        line_snippet = ""
                        if file_path != 'N/A' and line_no > 0:
                            try:
                                if file_path not in file_cache:
                                    with zipfile.ZipFile(epub_path, 'r') as z:
                                        # Normaliza busca no zip (ignora case e caminhos parciais)
                                        # EPubCheck costuma retornar caminhos relativos à raiz do zip
                                        zip_file_name = next((f for f in z.namelist() if file_path.replace("\\", "/").lower() in f.lower()), None)
                                        if zip_file_name:
                                            with z.open(zip_file_name) as zf:
                                                file_cache[file_path] = zf.read().decode('utf-8', errors='ignore').splitlines()
                                
                                if file_path in file_cache:
                                    lines = file_cache[file_path]
                                    if 0 < line_no <= len(lines):
                                        line_snippet = lines[line_no-1].strip()
                            except:
                                pass

                        # Tenta extrair o ID do fragmento se for erro de fragmento
                        error_text = m.get('message', '')
                        if line_snippet and ("fragment" in error_text.lower() or "fragmento" in error_text.lower()):
                            import re
                            # Busca o que vem depois do # até a aspa
                            fid_match = re.search(r'#([^"\'>\s]*)', line_snippet)
                            if fid_match:
                                error_text += f" (ID: <strong style='color:#c0392b;'>#{fid_match.group(1)}</strong>)"

                        # Formatar localização de forma legível
                        if line_no > 0 and col > 0:
                            loc_str = f"{file_path} (linha {line_no}, coluna {col})"
                        elif line_no > 0:
                            loc_str = f"{file_path} (linha {line_no})"
                        else:
                            loc_str = file_path
                        
                        if sev in summary: summary[sev] += 1
                        summary['messages'].append({
                            "severity": sev,
                            "location": loc_str,
                            "text": error_text,
                            "snippet": line_snippet
                        })
                else:
                    if sev in summary: summary[sev] += 1
                    summary['messages'].append({
                        "severity": sev,
                        "location": m.get('fileName', 'N/A'),
                        "text": m.get('message', ''),
                        "snippet": ""
                    })
    return summary

def generate_html_report(epub_name, data):
    report_path = Path(f"reports/REPORT_{epub_name}.html")
    eb = data['epubcheck']
    
    error_rows = ""
    for m in eb['messages']:
        color = "#e74c3c" if m['severity'] in ['FATAL', 'ERROR'] else "#f39c12" if m['severity'] == 'WARNING' else "#3498db"
        snippet_html = f"<div style='background:#f9f9f9; border-left:4px solid {color}; padding:8px; margin-top:5px; font-family:monospace; font-size:0.85em; color:#333; overflow-x:auto;'><code>{m.get('snippet', '')}</code></div>" if m.get('snippet') else ""
        error_rows += f"<tr><td style='color:{color}; font-weight:bold;'>{m['severity']}</td><td>{m['location']}</td><td>{m['text']}{snippet_html}</td></tr>"

    # Sort external links: errors (non-200) first, then alphabetical by URL
    sorted_links = sorted(data.get('external_links', []), key=lambda x: (x['status'] == 200, x['url']))

    # Gerar tabela de links externos
    ext_links_rows = ""
    for link in sorted_links:
        status_color = "green" if link['status'] == 200 else "red"
        ext_links_rows += f"<tr><td>{link['url']}</td><td style='color:{status_color}'>{link['status']}</td></tr>"

    # Lista de ficheiros sem limitador
    missing_divs = data.get('limitador_missing', [])
    missing_html = "".join([f"<li>{item}</li>" for item in missing_divs]) if missing_divs else "<li>✅ Todos os ficheiros estão OK.</li>"

    html = f"""
    <html>
    <head>
        <title>Relatório {epub_name}</title>
        <style>
            body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 40px; background: #f4f7f6; color: #333; }}
            .card {{ background: white; padding: 25px; border-radius: 12px; box-shadow: 0 4px 15px rgba(0,0,0,0.05); margin-bottom: 25px; }}
            h1, h2 {{ color: #2c3e50; border-bottom: 2px solid #eee; padding-bottom: 10px; }}
            table {{ width: 100%; border-collapse: collapse; margin-top: 15px; }}
            th {{ background: #f8f9fa; text-align: left; padding: 12px; border-bottom: 2px solid #dee2e6; }}
            td {{ padding: 10px; border-bottom: 1px solid #eee; font-size: 0.9em; }}
            .screenshot-thumb {{ width: 300px; cursor: zoom-in; border: 4px solid #fff; border-radius: 8px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); transition: transform 0.2s; }}
            .screenshot-thumb:hover {{ transform: scale(1.02); }}
            .badge {{ padding: 6px 12px; border-radius: 20px; color: white; font-weight: bold; margin-right: 10px; }}
            
            /* Modal Lightbox */
            .lightbox {{ display: none; position: fixed; z-index: 1000; left: 0; top: 0; width: 100%; height: 100%; background-color: rgba(0,0,0,0.9); }}
            .lightbox-content {{ margin: auto; display: block; max-width: 90%; max-height: 90vh; border-radius: 5px; position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); }}
            .close {{ position: absolute; top: 20px; right: 35px; color: #f1f1f1; font-size: 40px; font-weight: bold; cursor: pointer; }}
        </style>
        <script>
            function openModal(src) {{
                var modal = document.getElementById("myModal");
                var modalImg = document.getElementById("img01");
                modal.style.display = "block";
                modalImg.src = src;
            }}
            function closeModal() {{
                document.getElementById("myModal").style.display = "none";
            }}
            // Close on outside click
            window.onclick = function(event) {{
                var modal = document.getElementById("myModal");
                if (event.target == modal) {{
                    modal.style.display = "none"; 
                }}
            }}
        </script>

    </head>
    <body>
        <div class="card">
            <h1>E-book: {epub_name}</h1>
            <p>
                <span class="badge" style="background:#e74c3c">Erros: {eb['FATAL'] + eb['ERROR']}</span>
                <span class="badge" style="background:#f39c12">Avisos: {eb['WARNING']}</span>
                <span class="badge" style="background:#3498db">Alertas: {eb['USAGE']}</span>
            </p>
            <p style="margin-top: 10px; font-size: 0.9em; color: #7f8c8d;">
                <strong>Créditos:</strong> {data.get('typesetter', 'Não identificado')}
            </p>
        </div>

        <div class="card">
            <h2>1. Detalhes do ePubCheck</h2>
            <table>
                <thead><tr><th>Gravidade</th><th>Arquivo / Local</th><th>Mensagem de Erro</th></tr></thead>
                <tbody>{error_rows if error_rows else "<tr><td colspan='3'>Nenhum erro encontrado.</td></tr>"}</tbody>
            </table>
        </div>

        {f'''
        <div class="card">
            <h2>2. Sugestões de Correção da IA <small style="color: #7f8c8d; font-size: 0.6em; font-weight: normal;">(Modelo: {data.get('ai_advice_model', 'N/A')})</small></h2>
            <div style="background: #f8f9fa; padding: 20px; border-radius: 8px; border-left: 5px solid #3498db; font-size: 0.95em; line-height: 1.6;">
                {data.get('ai_advice', 'Nenhum erro crítico para análise.')}
            </div>
        </div>
        ''' if data.get('ai_advice') else ""}

        <div class="card">
            <h2>3. Atividades Interativas (Exercícios e Gabarito)</h2>
            <div style="background: white; padding: 15px; border-radius: 5px; border: 1px solid #eee;">
                {''.join([f'<div style="margin-bottom: 8px; font-size: 0.9em;">{log}</div>' for log in data.get('interactivity_logs', [])]) if data.get('interactivity_logs') else "<p>Nenhuma atividade interativa detectada ou erro no processamento.</p>"}
            </div>
            {f"<div style='margin-top:15px; padding:10px; background:#fdf2f2; border-left:4px solid #e74c3c; color:#c0392b;'><strong>Falhas detectadas:</strong> {len(data['interactivity_issues'])} itens inconsistentes.</div>" if data.get('interactivity_issues') else ""}
        </div>

        {f'''
        <div class="card">
            <h2>4. Análise Visual (IA Qwen3 VL)</h2>
            {''.join([f"""
            <div style="margin-bottom: 30px; border-bottom: 1px solid #eee; padding-bottom: 20px;">
                <h3>📍 {item.get('location', 'N/A')} <span class="badge" style="background:#8e44ad">{item.get('type', 'Geral')}</span> <small style="color: #7f8c8d; font-size: 0.8em; font-weight: normal;">(IA: {item.get('ai_model', 'N/A')})</small></h3>
                <p><strong>Parecer da IA:</strong> {item.get('analysis', 'Sem análise')}</p>
                {f'<img src="{item["image_url"]}" class="screenshot-thumb" onclick="openModal(this.src)">' if item.get('image_url') else '<p><em>Sem captura de tela.</em></p>'}
            </div>
            """ for item in data.get('vision_results', [])])}
        </div>
        ''' if ENABLE_VISION_AI else ""}

        <div class="card">
            <h2>5. CSS e Estrutura</h2>
            <p>Classe .limitador (40em): {"✅ OK" if data['css_rules']['limitador_ok'] else "❌ NÃO ENCONTRADA"}</p>
            <p>Estrutura Geral: {"✅ OK" if data['structure_ok'] else "❌ AVISOS"}</p>
        </div>


        <div class="card">
            <h2>6. Ficheiros sem a div .limitador</h2>
            <ul style="color: {'red' if missing_divs else 'green'}">
                {missing_html}
            </ul>
        </div>
        
        <div class="card">
            <h2>7. Verificação de Links Externos</h2>
            <table>
                <thead><tr><th>URL</th><th>Status</th></tr></thead>
                <tbody>{ext_links_rows if ext_links_rows else "<tr><td colspan='2'>Nenhum link externo encontrado.</td></tr>"}</tbody>
            </table>
            
            <div style="margin-top:20px; text-align:right;">
                <p><em>Links 200 (OK): {sum(1 for l in data.get('external_links', []) if l['status'] == 200)}</em></p>
            </div>
        </div>

        <div class="card">
            <h2>8. Logs Detalhados de Validação</h2>
            <div style="background: #2c3e50; color: #ecf0f1; padding: 15px; border-radius: 5px; font-family: monospace; max-height: 400px; overflow-y: auto;">
                {''.join([f'<div style="margin-bottom: 5px; border-bottom: 1px solid #34495e; padding-bottom: 2px;">{log}</div>' for log in data.get('structure_logs', [])])}
            </div>
        </div>

        <div class="card">
            <h2>9. Tempos de Processamento</h2>
            <table style="width: auto; min-width: 300px;">
                <tr><td><strong>1. EPubCheck:</strong></td><td>{data['timings'].get('epubcheck', 0):.2f}s</td></tr>
                <tr><td><strong>2. Estrutura (TOC/NCX):</strong></td><td>{data['timings'].get('structure', 0):.2f}s</td></tr>
                <tr><td><strong>3. Análise de CSS:</strong></td><td>{data['timings'].get('css_analysis', 0):.2f}s</td></tr>
                <tr><td><strong>4. Análise XHTML:</strong></td><td>{data['timings'].get('xhtml_analysis', 0):.2f}s</td></tr>
                <tr><td><strong>5. Links Externos:</strong></td><td>{data['timings'].get('external_links', 0):.2f}s</td></tr>
                <tr><td><strong>6. Visão IA:</strong></td><td>{data['timings'].get('vision_ai', 0):.2f}s</td></tr>
                <tr><td><strong>IA (Conselhos):</strong></td><td>{data['timings'].get('ai_advice', 0):.2f}s</td></tr>
                <tr><td><strong>7. Interatividade:</strong></td><td>{data['timings'].get('interactivity', 0):.2f}s</td></tr>
                <tr style="border-top: 2px solid #eee; font-size: 1.1em;">
                    <td><strong>TEMPO TOTAL:</strong></td>
                    <td style="color: #27ae60; font-weight: bold;">{data['timings'].get('total', 0):.2f}s</td>
                </tr>
            </table>
        </div>
    
    <div id="myModal" class="lightbox">
        <span class="close" onclick="closeModal()">&times;</span>
        <img class="lightbox-content" id="img01">
    </div>

    </body>
    </html>
    """
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(html)
    return report_path

def process_single_epub(epub_path):
    import time # Added import for time module
    start_total = time.time()
    epub_name = Path(epub_path).name
    report_data = {'timings': {}} 

    print(f"\n{Fore.MAGENTA}{'='*50}\nVALIDANDO: {epub_name}\n{'='*50}")

    # 1. Validador Oficial (ePubCheck)
    print(f"{Fore.YELLOW}[1/7] Executando EPubCheck (validador W3C)...")
    s1 = time.time()
    report_data['epubcheck'] = run_epubcheck(epub_path)
    report_data['typesetter'] = get_typesetting_credit(epub_path)
    report_data['timings']['epubcheck'] = time.time() - s1
    
    eb = report_data['epubcheck']
    total_errors = eb['FATAL'] + eb['ERROR']
    if total_errors > 0:
        print(f"{Fore.RED}    [!] EPubCheck: {total_errors} erro(s), {eb['WARNING']} aviso(s), {eb['USAGE']} alerta(s)")
    else:
        print(f"{Fore.GREEN}    [OK] EPubCheck: 0 erros, {eb['WARNING']} aviso(s), {eb['USAGE']} alerta(s)")

    # 2. Estrutura (TOC, NCX, PageList)
    print(f"{Fore.YELLOW}[2/7] Validando TOC, PageList e Âncoras internas...")
    s2 = time.time()
    structure_ok, structure_logs = check_toc_and_pagelist(epub_path)
    report_data['timings']['structure'] = time.time() - s2
    report_data['structure_ok'] = structure_ok
    report_data['structure_logs'] = structure_logs

    # 3. Análise de CSS
    print(f"{Fore.YELLOW}[3/7] Analisando regras nos arquivos CSS...")
    s3 = time.time()
    report_data['css_rules'] = validate_css_rules(epub_path)
    report_data['timings']['css_analysis'] = time.time() - s3

    # 4. Análise de Arquivos XHTML (.limitador e estruturas)
    print(f"{Fore.YELLOW}[4/7] Verificando aplicação da div .limitador e riscos Binpar...")
    s4 = time.time()
    xhtml_analysis = validate_limitador_and_structures(epub_path) # Retorna dict com logs agora
    report_data['timings']['xhtml_analysis'] = time.time() - s4
    report_data['css'] = xhtml_analysis # Store the full dictionary
    report_data['structure_logs'].extend(report_data['css'].get('detailed_logs', []))
    report_data['limitador_missing'] = xhtml_analysis["missing_limitador"]
    report_data['binpar_structural_risks'] = xhtml_analysis["binpar_complex_warnings"]

    # 5. Links Externos (Status 200) - Parte ASSÍNCRONA
    print(f"{Fore.YELLOW}[5/7] Testando links externos (Status 200)...")
    s5 = time.time()
    from modules.link_validator import validate_external_links
    report_data['external_links'] = asyncio.run(validate_external_links(epub_path))
    report_data['timings']['external_links'] = time.time() - s5

    # 6. Visão Computacional (IA Qwen3 VL)
    s6 = time.time()
    report_data['total_prompt_tokens'] = 0
    report_data['total_completion_tokens'] = 0
    report_data['total_tokens'] = 0

    if ENABLE_VISION_AI:
        print(f"{Fore.YELLOW}[6/7] Executando análise de visão computacional (Amostragem)...")
        raw_vision_results = check_visual_layout(epub_path, max_items=3)
        vision_processed = []
        for v in raw_vision_results:
            if isinstance(v, dict) and "usage" in v:
                u = v["usage"]
                report_data['total_prompt_tokens'] += u.get("prompt_tokens", 0)
                report_data['total_completion_tokens'] += u.get("completion_tokens", 0)
                report_data['total_tokens'] += u.get("total_tokens", 0)
                v["tokens"] = u.get("total_tokens", 0)
                v["analysis"] = v["content"] # No dict, content é o texto
            vision_processed.append(v)
        report_data['vision_results'] = vision_processed
    else:
        print(f"{Fore.WHITE}[6/7] Análise visual desativada.")
        report_data['vision_results'] = []
    report_data['timings']['vision_ai'] = time.time() - s6
    
    # Adicional: Conselhos da IA para erros técnicos
    print(f"{Fore.BLUE}[IA] Consultando IA para conselhos técnicos sobre o EPubCheck...")
    print(f"{Fore.WHITE}    [DEBUG] Enviando {len(report_data['epubcheck']['messages'])} mensagens para análise.")
    s_ia = time.time()
    ia_res = get_ai_tech_advice(report_data['epubcheck']['messages'])
    raw_advice = ia_res.get("content", "")
    advice_model = ia_res.get("model", "N/A")
    usage = ia_res.get("usage")
    
    if usage:
        report_data['total_prompt_tokens'] += usage.get("prompt_tokens", 0)
        report_data['total_completion_tokens'] += usage.get("completion_tokens", 0)
        report_data['total_tokens'] += usage.get("total_tokens", 0)
        report_data['advice_tokens'] = usage.get("total_tokens", 0)

    report_data['ai_advice_model'] = advice_model
    if raw_advice:
        import re
        import html
        # Escapa caracteres HTML para que tags sugeridas pela IA não quebrem o layout do relatório
        escaped_advice = html.escape(raw_advice)
        # Converte **texto** (que pode conter aspas internas vindo da IA) para <b>texto</b>
        # A IA foi instruída a colocar aspas dentro do negrito
        advice_html = re.sub(r'\*\*([^\*]+)\*\*', r"<b>\1</b>", escaped_advice)
        # Converte quebras de linha em <br> 
        report_data['ai_advice'] = advice_html.replace("\n", "<br>")
    else:
        report_data['ai_advice'] = ""
    report_data['timings']['ai_advice'] = time.time() - s_ia

    # 7. Atividades Interativas e Gabarito
    print(f"{Fore.YELLOW}[7/7] Validando exercícios interativos e Gabarito...")
    s7 = time.time()
    inter_ok, inter_logs, inter_issues = validate_activities(epub_path)
    report_data['timings']['interactivity'] = time.time() - s7
    report_data['interactivity_logs'] = inter_logs
    report_data['interactivity_issues'] = inter_issues
    report_data['structure_logs'].extend(inter_logs)

    # Tempo total
    report_data['timings']['total'] = time.time() - start_total


    # 8. Geração do Relatório Final
    report_file = generate_html_report(epub_name, report_data)
    
    print(f"\n{Fore.GREEN}✔ Processo concluído para: {epub_name}")
    print(f"{Fore.CYAN}👉 Relatório: {report_file}")

def main():
    print(Fore.CYAN + "=== INICIANDO PROCESSO DE VALIDAÇÃO AUTOMÁTICA ===")
    
    # Limpa capturas de sessões anteriores
    img_dir = Path("reports/screenshots")
    if img_dir.exists():
        shutil.rmtree(img_dir)
    img_dir.mkdir(parents=True, exist_ok=True)

    epubs = glob.glob("input/*.epub")
    if not epubs:
        print(Fore.RED + "Coloque arquivos .epub na pasta /input.")
        return
    for epub in epubs:
        process_single_epub(epub)

if __name__ == "__main__":
    main()