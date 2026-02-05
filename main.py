import os
import time
import glob
import json
import subprocess
import shutil
import zipfile
from lxml import etree
from pathlib import Path
from colorama import init, Fore
from config import Config
from modules.structural import check_toc_and_pagelist, get_typesetting_credit, check_filenames
from modules.css_checker import validate_css_rules, validate_limitador_and_structures
from modules.vision_ai import check_visual_layout, get_ai_tech_advice
import asyncio
from modules.link_validator import validate_external_links
from modules.interactivity import validate_activities
from modules.image_validator import validate_image_sizes

init(autoreset=True)

def run_epubcheck(epub_path):
    jar_path = Config.EPUBCHECK_JAR
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
    is_secad = data.get('is_secad', False)
    
    # Helper para numeração dinâmica
    class SectionCounter:
        def __init__(self): self.count = 0
        def next(self):
            self.count += 1
            return f"{self.count:02d}"
    
    counter = SectionCounter()

    error_rows = ""
    for m in eb['messages']:
        color = "var(--error)" if m['severity'] in ['FATAL', 'ERROR'] else "var(--warning)" if m['severity'] == 'WARNING' else "var(--info)"
        snippet_html = f"<div class='snippet'><code>{m.get('snippet', '')}</code></div>" if m.get('snippet') else ""
        error_rows += f"<tr><td><span class='badge' style='background:{color}'>{m['severity']}</span></td><td>{m['location']}</td><td>{m['text']}{snippet_html}</td></tr>"

    # Sort external links: errors (non-200) first, then alphabetical by URL
    sorted_links = sorted(data.get('external_links', []), key=lambda x: (x['status'] == 200, x['url']))

    # Gerar tabela de links externos
    ext_links_rows = ""
    for link in sorted_links:
        status_color = "green" if link['status'] == 200 else "red"
        ext_links_rows += f"<tr><td>{link['url']}</td><td style='color:{status_color}'>{link['status']}</td></tr>"

    # Lista de ficheiros sem limitador
    missing_divs = data.get('limitador_missing', [])
    marker_pass = "<span style='font-family:monospace; font-weight:bold; color:#27ae60;'>[      PASSOU      ]</span>"
    marker_fail = "<span style='font-family:monospace; font-weight:bold; color:#c0392b;'>[      FALHOU      ]</span>"
    marker_info = "<span style='font-family:monospace; color:var(--text-muted);'>[      INFO        ]</span>"
    marker_aviso = "<span style='font-family:monospace; font-weight:bold; color:#f39c12;'>[      AVISO       ]</span>"

    missing_html = "".join([f"<li>{marker_fail} {item}</li>" for item in missing_divs]) if missing_divs else f"<li>{marker_pass} Todos os arquivos estão OK.</li>"

    # Riscos estruturais Binpar
    binpar_risks = data.get('binpar_structural_risks', [])
    binpar_html = "".join([f"<li style='color:#f39c12'>{marker_aviso} {item}</li>" for item in binpar_risks]) if binpar_risks else f"<li>{marker_pass} Nenhuma estrutura crítica detectada.</li>"

    # Lista de ficheiros com nomes inválidos
    invalid_filenames = data.get('invalid_filenames', [])
    filenames_html = "".join([f"<li style='color:var(--error)'>{marker_fail} {item}</li>" for item in invalid_filenames]) if invalid_filenames else f"<li>{marker_pass} Todos os nomes de arquivos estão OK.</li>"

    # Lista de imagens com tamanho excedido
    invalid_images = data.get('invalid_images', [])
    images_html = "".join([f"<li style='color:var(--error)'>{marker_fail} {item['path']} ({item['width']}x{item['height']} = {item['pixels']:,}px)</li>" for item in invalid_images]) if invalid_images else f"<li>{marker_pass} Todas as imagens estão dentro do limite.</li>"

    # Filtro de Terminal Logs
    filtered_logs = []
    for log in data.get('structure_logs', []):
        if is_secad:
            if ".limitador" in log or "PageList" in log or "Página" in log:
                continue
        filtered_logs.append(log)

    header_credit = f"<span class='stat-label'>Créditos: Secad</span>" if is_secad else f"<span class='stat-label'>Créditos: {data.get('typesetter', 'Não identificado')}</span>"

    html = f"""
    <!DOCTYPE html>
    <html lang="pt-br">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Relatório de Validação | {epub_name}</title>
        <link rel="preconnect" href="https://fonts.googleapis.com">
        <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
        <link href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,700&family=Outfit:wght@300;400;600&display=swap" rel="stylesheet">
        <style>
            :root {{
                --bg: #fdfdfc;
                --surface: #ffffff;
                --text: #1a1a1b;
                --text-muted: #626264;
                --accent: #1b4332;
                --border: #e8e8e6;
                --error: #c0392b;
                --warning: #d35400;
                --info: #2980b9;
                --shadow: 0 10px 30px -10px rgba(0,0,0,0.05);
            }}

            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            
            body {{ 
                font-family: 'Outfit', sans-serif; 
                background: var(--bg); 
                color: var(--text); 
                line-height: 1.6;
                padding: 40px 20px;
                -webkit-font-smoothing: antialiased;
            }}

            .container {{ 
                max-width: 1100px; 
                margin: 0 auto; 
            }}

            header {{
                margin-bottom: 60px;
                border-bottom: 4px solid var(--text);
                padding-bottom: 30px;
                display: flex;
                flex-direction: column;
                gap: 20px;
            }}

            h1 {{ 
                font-family: 'Bricolage Grotesque', sans-serif;
                font-size: clamp(2.5rem, 8vw, 4.5rem);
                line-height: 0.95;
                letter-spacing: -0.04em;
                text-transform: uppercase;
                color: var(--text);
            }}

            .header-meta {{
                display: flex;
                flex-wrap: wrap;
                align-items: center;
                gap: 20px;
                font-weight: 600;
            }}

            h2 {{ 
                font-family: 'Bricolage Grotesque', sans-serif;
                font-size: 1.8rem;
                margin-bottom: 25px;
                letter-spacing: -0.02em;
                display: flex;
                align-items: baseline;
                gap: 10px;
            }}
            
            h2 small {{ font-size: 0.5em; color: var(--text-muted); font-weight: normal; }}

            .card {{ 
                background: var(--surface); 
                padding: 40px; 
                border: 1px solid var(--border);
                margin-bottom: 40px; 
                box-shadow: var(--shadow);
            }}

            table {{ 
                width: 100%; 
                border-collapse: collapse; 
                margin-top: 10px; 
            }}

            th {{ 
                text-align: left; 
                padding: 15px 10px; 
                border-bottom: 2px solid var(--text);
                font-size: 0.75rem;
                text-transform: uppercase;
                letter-spacing: 0.1em;
                color: var(--text-muted);
            }}

            td {{ 
                padding: 15px 10px; 
                border-bottom: 1px solid var(--border); 
                font-size: 0.95rem;
                vertical-align: top;
            }}

            .badge {{ 
                display: inline-block;
                padding: 4px 12px; 
                font-size: 0.7rem;
                text-transform: uppercase;
                letter-spacing: 0.05em;
                border-radius: 2px; 
                color: white; 
                font-weight: 700; 
            }}
            
            .snippet {{
                background: #f8f8f8;
                border-left: 3px solid var(--text);
                padding: 12px;
                margin-top: 10px;
                font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
                font-size: 0.8rem;
                color: #444;
                overflow-x: auto;
            }}

            .ai-advice-container {{
                background: #f0f4f2;
                padding: 30px;
                border: 1px solid #d1dbd4;
                font-size: 1.1rem;
                line-height: 1.6;
                color: #1b4332;
            }}

            .screenshot-thumb {{ 
                width: 100%;
                max-width: 400px;
                cursor: zoom-in; 
                border: 1px solid var(--border);
                margin-top: 15px;
                filter: grayscale(0.2);
                transition: filter 0.3s;
            }}
            
            .screenshot-thumb:hover {{ filter: grayscale(0); }}

            .log-console {{
                background: #1a1a1b;
                color: #e0e0e0;
                padding: 25px;
                font-family: monospace;
                font-size: 0.85rem;
                max-height: 500px;
                overflow-y: auto;
                border: 1px solid #333;
            }}

            .log-line {{
                padding: 4px 0;
                border-bottom: 1px solid #2a2a2b;
            }}

            /* Modal Lightbox */
            .lightbox {{ display: none; position: fixed; z-index: 1000; left: 0; top: 0; width: 100%; height: 100%; background-color: rgba(255,255,255,0.95); cursor: zoom-out; }}
            .lightbox-content {{ margin: auto; display: block; max-width: 90%; max-height: 90vh; position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); box-shadow: 0 30px 60px rgba(0,0,0,0.1); border: 1px solid var(--border); }}
            .close {{ position: absolute; top: 30px; right: 40px; color: var(--text); font-size: 3rem; font-weight: 300; cursor: pointer; }}
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
        </script>
    </head>
    <body>
        <div class="container">
            <header>
                <h1>{epub_name}</h1>
                <div class="header-meta">
                    {header_credit}
                </div>
            </header>

            <section class="card">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:25px;">
                    <h2 style="margin-bottom:0">{counter.next()}. Relatório EPubCheck</h2>
                    <div class="badge-group">
                        <span class="badge" style="background:var(--error)">{eb['FATAL'] + eb['ERROR']} Erros</span>
                        <span class="badge" style="background:var(--warning)">{eb['WARNING']} Avisos</span>
                        <span class="badge" style="background:var(--info)">{eb['USAGE']} Alertas</span>
                    </div>
                </div>
                <table>
                    <thead>
                        <tr>
                            <th>Status</th>
                            <th>Localização</th>
                            <th>Mensagem</th>
                        </tr>
                    </thead>
                    <tbody>
                        {error_rows if error_rows else "<tr><td colspan='3'>Nenhum erro encontrado.</td></tr>"}
                    </tbody>
                </table>
            </section>

            <section class="card">
                <h2>{counter.next()}. IA Technical Advice <small>(Modelo: {data.get('ai_advice_model', 'N/A')})</small></h2>
                <div class="ai-advice-container">
                    {data.get('ai_advice') if data.get('ai_advice') else f'{marker_pass} Nenhum erro crítico detectado para análise da IA.'}
                </div>
            </section>
    """

    if is_secad:
        html += f"""
            <section class="card">
                <h2>{counter.next()}. Atividades Interativas</h2>
                <div style="border-left: 2px solid var(--accent); padding-left: 20px;">
                    {''.join([f'<div style="margin-bottom: 12px; font-size: 0.95rem;">{log}</div>' for log in data.get('interactivity_logs', [])]) if data.get('interactivity_logs') else "<p>Nenhuma atividade detectada.</p>"}
                </div>
                {f"<div style='margin-top:25px; padding:15px; background:#fff5f5; border:1px solid #feb2b2; color:#c53030; font-weight:600;'>{marker_fail} Falhas detectadas: {len(data['interactivity_issues'])} itens inconsistentes.</div>" if data.get('interactivity_issues') else ""}
            </section>
        """

    if Config.ENABLE_VISION_AI and data.get('vision_results'):
        html += f"""
            <section class="card">
                <h2>{counter.next()}. Análise Visual <small>(IA Qwen3 VL)</small></h2>
                {''.join([f'''
                <div style="margin-bottom: 40px; padding-bottom: 30px; border-bottom: 1px solid var(--border);">
                    <div style="display:flex; justify-content:space-between; align-items:baseline; margin-bottom:15px;">
                        <h3 style="font-family:'Bricolage Grotesque';">{item.get('location', 'N/A')}</h3>
                        <span class="badge" style="background:var(--text)">{item.get('type', 'Geral')}</span>
                    </div>
                    <p style="color:var(--text-muted); margin-bottom:20px;">{item.get('analysis', 'Sem análise')}</p>
                    {f'<img src="{item["image_url"]}" class="screenshot-thumb" onclick="openModal(this.src)">' if item.get('image_url') else '<p><em>Sem captura de tela.</em></p>'}
                </div>
                ''' for item in data.get('vision_results')])}
            </section>
        """

    # Seção: Estrutura & CSS (com filtros condicionais)
    limitador_li = ""
    if not is_secad:
        limitador_li = f"""
            <li style="display:flex; justify-content:space-between; border-bottom: 1px solid var(--border); padding-bottom: 10px;">
                <span>Classe .limitador (40em)</span>
                <span style="font-weight:700; color:{'#27ae60' if data['css_rules']['limitador_ok'] else '#c0392b'}">
                    {"[      PASSOU      ]" if data['css_rules']['limitador_ok'] else "[      FALHOU      ]"}
                </span>
            </li>
        """

    structure_title = "Estrutura E-book"
    if is_secad:
        structure_title = "Sumário & Links"

    # Coluna da Direita (Layout de 2 colunas)
    right_column_content = ""
    if is_secad:
        # Para Secad, a coluna da direita pode ficar vazia ou ter outra info, mas removemos Riscos Binpar
        right_column_content = f"""
                <section class="card">
                    <h4 style="font-size: 0.8rem; text-transform: uppercase; color: var(--text-muted); margin-bottom: 10px;">Informações Adicionais</h4>
                    <p style="font-size: 0.9rem; color: var(--text-muted);">Validação de estrutura Secad concluída.</p>
                </section>
        """
    else:
        right_column_content = f"""
                <section class="card">
                    <h4 style="font-size: 0.8rem; text-transform: uppercase; color: var(--text-muted); margin-bottom: 10px;">Limitadores Ausentes (.limitador)</h4>
                    <div style="max-height: 400px; overflow-y: auto; font-size: 0.85rem;">
                        <ul style="list-style: none; color: {'var(--error)' if missing_divs else '#27ae60'}">
                            {missing_html}
                        </ul>
                    </div>
                    <div style="margin-top:20px;">
                        <h4 style="font-size: 0.8rem; text-transform: uppercase; color: var(--text-muted); margin-bottom: 10px;">Riscos Estruturais Binpar</h4>
                        <ul style="list-style: none;">
                            {binpar_html}
                        </ul>
                    </div>
                </section>
        """

    html += f"""
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 40px;">
                <section class="card">
                    <h2>{counter.next()}. Estrutura & CSS</h2>
                    <ul style="list-style: none; display: flex; flex-direction: column; gap: 15px;">
                        {limitador_li}
                        <li style="display:flex; justify-content:space-between; border-bottom: 1px solid var(--border); padding-bottom: 10px;">
                            <span>Nomenclatura de Arquivos</span>
                            <span style="font-weight:700; color:{'#27ae60' if not invalid_filenames else '#c0392b'}">
                                {"[      PASSOU      ]" if not invalid_filenames else f"[      FALHOU      ] ({len(invalid_filenames)})"}
                            </span>
                        </li>
                        <li style="display:flex; justify-content:space-between; border-bottom: 1px solid var(--border); padding-bottom: 10px;">
                            <span>Tamanho das Imagens (Máx 5.6M px)</span>
                            <span style="font-weight:700; color:{'#27ae60' if not invalid_images else '#c0392b'}">
                                {"[      PASSOU      ]" if not invalid_images else f"[      FALHOU      ] ({len(invalid_images)})"}
                            </span>
                        </li>
                        <li style="display:flex; justify-content:space-between; border-bottom: 1px solid var(--border); padding-bottom: 10px;">
                            <span>{structure_title}</span>
                            <span style="font-weight:700; color:{'#27ae60' if data['structure_ok'] else '#f39c12'}">
                                {"[      PASSOU      ]" if data['structure_ok'] else "[      AVISO       ]"}
                            </span>
                        </li>
                    </ul>

                    <div style="margin-top: 25px;">
                        <h4 style="font-size: 0.8rem; text-transform: uppercase; color: var(--text-muted); margin-bottom: 10px;">Arquivos com Nomes Inválidos</h4>
                        <div style="max-height: 120px; overflow-y: auto; font-size: 0.85rem; border: 1px solid var(--border); padding: 10px; background: #fffcfc; margin-bottom: 15px;">
                            <ul style="list-style: none;">
                                {filenames_html}
                            </ul>
                        </div>

                        <h4 style="font-size: 0.8rem; text-transform: uppercase; color: var(--text-muted); margin-bottom: 10px;">Imagens Excedendo Limite</h4>
                        <div style="max-height: 120px; overflow-y: auto; font-size: 0.85rem; border: 1px solid var(--border); padding: 10px; background: #fffcfc;">
                            <ul style="list-style: none;">
                                {images_html}
                            </ul>
                        </div>
                    </div>
                </section>
                {right_column_content}
            </div>

            <section class="card">
                <h2>{counter.next()}. Verificação de Links</h2>
                <table>
                    <thead><tr><th>URL</th><th>Status</th></tr></thead>
                    <tbody>{ext_links_rows if ext_links_rows else "<tr><td colspan='2'>Nenhum link externo encontrado.</td></tr>"}</tbody>
                </table>
            </section>

            <section class="card">
                <h2>{counter.next()}. Terminal Logs</h2>
                <div class="log-console">
                    {''.join([f'<div class="log-line">{log}</div>' for log in filtered_logs])}
                </div>
            </section>

            <section class="card" style="margin-bottom: 100px;">
                <h2>{counter.next()}. Performance</h2>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 40px;">
                    <div style="display: flex; flex-direction: column; gap: 8px;">
                        <div style="display:flex; justify-content:space-between; border-bottom: 1px solid var(--border); padding-bottom: 4px;">
                            <span style="font-size: 0.9rem; color: var(--text-muted);">EPubCheck:</span>
                            <span style="font-weight:600;">{data['timings'].get('epubcheck', 0):.2f}s</span>
                        </div>
                        <div style="display:flex; justify-content:space-between; border-bottom: 1px solid var(--border); padding-bottom: 4px;">
                            <span style="font-size: 0.9rem; color: var(--text-muted);">Estrutura:</span>
                            <span style="font-weight:600;">{data['timings'].get('structure', 0):.2f}s</span>
                        </div>
                        <div style="display:flex; justify-content:space-between; border-bottom: 1px solid var(--border); padding-bottom: 4px;">
                            <span style="font-size: 0.9rem; color: var(--text-muted);">Análise CSS:</span>
                            <span style="font-weight:600;">{data['timings'].get('css_analysis', 0):.2f}s</span>
                        </div>
                        <div style="display:flex; justify-content:space-between; border-bottom: 1px solid var(--border); padding-bottom: 4px;">
                            <span style="font-size: 0.9rem; color: var(--text-muted);">Links Externos:</span>
                            <span style="font-weight:600;">{data['timings'].get('external_links', 0):.2f}s</span>
                        </div>
                        <div style="display:flex; justify-content:space-between; border-bottom: 1px solid var(--border); padding-bottom: 4px;">
                            <span style="font-size: 0.9rem; color: var(--text-muted);">Nomenclatura:</span>
                            <span style="font-weight:600;">{data['timings'].get('filenames', 0):.2f}s</span>
                        </div>
                    </div>
                    <div style="display: flex; flex-direction: column; gap: 8px;">
                        <div style="display:flex; justify-content:space-between; border-bottom: 1px solid var(--border); padding-bottom: 4px;">
                            <span style="font-size: 0.9rem; color: var(--text-muted);">Visão IA:</span>
                            <span style="font-weight:600;">{data['timings'].get('vision_ai', 0):.2f}s</span>
                        </div>
                        <div style="display:flex; justify-content:space-between; border-bottom: 1px solid var(--border); padding-bottom: 4px;">
                            <span style="font-size: 0.9rem; color: var(--text-muted);">Conselhos IA:</span>
                            <span style="font-weight:600;">{data['timings'].get('ai_advice', 0):.2f}s</span>
                        </div>
                        <div style="display:flex; justify-content:space-between; border-bottom: 1px solid var(--border); padding-bottom: 4px;">
                            <span style="font-size: 0.9rem; color: var(--text-muted);">Imagens:</span>
                            <span style="font-weight:600;">{data['timings'].get('image_sizes', 0):.2f}s</span>
                        </div>
                        {f'''
                        <div style="display:flex; justify-content:space-between; border-bottom: 1px solid var(--border); padding-bottom: 4px;">
                            <span style="font-size: 0.9rem; color: var(--text-muted);">Interatividade:</span>
                            <span style="font-weight:600;">{data['timings'].get('interactivity', 0):.2f}s</span>
                        </div>
                        ''' if is_secad else ''}
                        <div style="display:flex; justify-content:space-between; border-bottom: 1px solid var(--border); padding-bottom: 4px;">
                            <span style="font-size: 0.9rem; color: var(--text-muted);">Tokens IA:</span>
                            <span style="font-weight:700; color:var(--accent)">{data.get('total_tokens', 0)}</span>
                        </div>
                        <div style="display:flex; justify-content:space-between; border-top: 2px solid var(--text); padding-top: 10px; margin-top: 5px;">
                            <span style="font-weight:700; text-transform: uppercase;">Total:</span>
                            <span style="font-weight:700; color: #27ae60; font-size: 1.1rem;">{data['timings'].get('total', 0):.2f}s</span>
                        </div>
                    </div>
                </div>
            </section>
        </div>

        <div id="myModal" class="lightbox">
            <span class="close" onclick="closeModal()">&times;</span>
            <img class="lightbox-content" id="img01">
        </div>
    </body>
    </html>
    """
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(html)
    return report_path

def get_publisher(epub_path):
    try:
        with zipfile.ZipFile(epub_path, 'r') as z:
            # Encontra o arquivo OPF
            opf_path = next((f for f in z.namelist() if f.endswith('.opf')), None)
            if opf_path:
                content = z.read(opf_path).decode('utf-8', errors='ignore')
                tree = etree.fromstring(content.encode('utf-8'))
                # DC namespaces
                ns = {'dc': 'http://purl.org/dc/elements/1.1/', 'opf': 'http://www.idpf.org/2007/opf'}
                publisher = tree.xpath('//dc:publisher/text()', namespaces=ns)
                if publisher:
                    return publisher[0].strip()
    except:
        pass
    return "Desconhecido"

def process_single_epub(epub_path):
    import time # Added import for time module
    start_total = time.time()
    epub_name = Path(epub_path).name
    report_data = {'timings': {}} 

    print(f"\n{Fore.MAGENTA}{'='*50}\nVALIDANDO: {epub_name}\n{'='*50}")

    # Detecta Publisher
    publisher = get_publisher(epub_path)
    is_secad = "Artmed Panamericana" in publisher
    report_data['publisher'] = publisher
    report_data['is_secad'] = is_secad
    print(f"{Fore.CYAN}    [ INFO ] Editora detectada: {publisher}")

    step = 1
    # 1. Validador Oficial (ePubCheck)
    print(f"{Fore.YELLOW}[{step}] Executando EPubCheck (validador W3C)...")
    s1 = time.time()
    report_data['epubcheck'] = run_epubcheck(epub_path)
    report_data['typesetter'] = get_typesetting_credit(epub_path)
    report_data['timings']['epubcheck'] = time.time() - s1
    
    eb = report_data['epubcheck']
    total_errors = eb['FATAL'] + eb['ERROR']
    if total_errors > 0:
        print(f"{Fore.RED}    [      FALHOU      ] EPubCheck: {total_errors} erro(s), {eb['WARNING']} aviso(s), {eb['USAGE']} alerta(s)")
    else:
        print(f"{Fore.GREEN}    [      PASSOU      ] EPubCheck: 0 erros, {eb['WARNING']} aviso(s), {eb['USAGE']} alerta(s)")

    step += 1
    # 2. Estrutura (TOC, NCX, PageList)
    print(f"{Fore.YELLOW}[{step}] Validando TOC, PageList e Âncoras internas...")
    s2 = time.time()
    structure_ok, structure_logs = check_toc_and_pagelist(epub_path)
    report_data['timings']['structure'] = time.time() - s2
    report_data['structure_ok'] = structure_ok
    report_data['structure_logs'] = structure_logs
    if structure_ok:
        print(f"    [      PASSOU      ] Estrutura TOC/PageList validada.")
    else:
        print(f"    [      FALHOU      ] Problemas na estrutura detectados.")

    step += 1
    # 3. Análise de CSS
    print(f"{Fore.YELLOW}[{step}] Analisando regras nos arquivos CSS...")
    s3 = time.time()
    report_data['css_rules'] = validate_css_rules(epub_path)
    report_data['timings']['css_analysis'] = time.time() - s3

    step += 1
    # 4. Análise de Arquivos XHTML (.limitador e estruturas)
    if is_secad:
        print(f"{Fore.YELLOW}[{step}] Verificando aplicação da div .limitador...")
    else:
        print(f"{Fore.YELLOW}[{step}] Verificando aplicação da div .limitador e riscos Binpar...")
    s4 = time.time()
    xhtml_analysis = validate_limitador_and_structures(epub_path, is_secad=is_secad)
    report_data['timings']['xhtml_analysis'] = time.time() - s4
    report_data['css'] = xhtml_analysis
    report_data['structure_logs'].extend(report_data['css'].get('detailed_logs', []))
    report_data['limitador_missing'] = xhtml_analysis["missing_limitador"]
    report_data['binpar_structural_risks'] = xhtml_analysis["binpar_complex_warnings"]

    step += 1
    # 5. Links Externos (Status 200) - Parte ASSÍNCRONA
    print(f"{Fore.YELLOW}[{step}] Testando links externos (Status 200)...")
    s5 = time.time()
    from modules.link_validator import validate_external_links
    report_data['external_links'] = asyncio.run(validate_external_links(epub_path))
    links = report_data['external_links']
    broken_links = [l for l in links if l['status'] != 200]
    if broken_links:
        print(f"{Fore.RED}    [      FALHOU      ] {len(broken_links)} links externos quebrados encontrados.")
    else:
        print(f"{Fore.GREEN}    [      PASSOU      ] Todos os links externos estão OK.")
    report_data['timings']['external_links'] = time.time() - s5

    step += 1
    # 6. Validação de Nomes de Arquivos (Plataforma)
    s_filenames = time.time()
    print(f"{Fore.YELLOW}[{step}] Validando nomenclatura de arquivos...")
    invalid_filenames = check_filenames(epub_path)
    report_data['invalid_filenames'] = invalid_filenames
    if invalid_filenames:
        print(f"{Fore.RED}    [      FALHOU      ] Nomes inválidos encontrados: {len(invalid_filenames)} itens")
    else:
        print(f"{Fore.GREEN}    [      PASSOU      ] Todos os nomes de arquivos são válidos.")
    report_data['timings']['filenames'] = time.time() - s_filenames

    # 7. Visão Computacional (Opcional)
    s6 = time.time()
    report_data['total_prompt_tokens'] = 0
    report_data['total_completion_tokens'] = 0
    report_data['total_tokens'] = 0
    report_data['vision_results'] = []

    if Config.ENABLE_VISION_AI:
        step += 1
        print(f"{Fore.YELLOW}[{step}] Executando análise de visão computacional (Amostragem)...")
        raw_vision_results = check_visual_layout(epub_path, max_items=3)
        vision_processed = []
        for v in raw_vision_results:
            if isinstance(v, dict) and "usage" in v:
                u = v["usage"]
                report_data['total_prompt_tokens'] += u.get("prompt_tokens", 0)
                report_data['total_completion_tokens'] += u.get("completion_tokens", 0)
                report_data['total_tokens'] += u.get("total_tokens", 0)
                v["tokens"] = u.get("total_tokens", 0)
                v["analysis"] = v["content"]
            vision_processed.append(v)
        report_data['vision_results'] = vision_processed
    else:
        print(f"{Fore.WHITE}    [ INFO ] Análise visual desativada.")
    report_data['timings']['vision_ai'] = time.time() - s6

    # 8. Conselhos Técnicos da IA
    step += 1
    print(f"{Fore.BLUE}[{step}] Consultando IA para conselhos técnicos sobre o EPubCheck...")
    s_ia = time.time()
    ia_res = get_ai_tech_advice(report_data['epubcheck']['messages'])
    raw_advice = ia_res.get("content", "")
    advice_model = ia_res.get("model", "N/A")
    usage = ia_res.get("usage")
    
    if usage:
        report_data['total_prompt_tokens'] += usage.get("prompt_tokens", 0)
        report_data['total_completion_tokens'] += usage.get("completion_tokens", 0)
        report_data['total_tokens'] += usage.get("total_tokens", 0)

    report_data['ai_advice_model'] = advice_model
    if raw_advice:
        import re
        import html
        escaped_advice = html.escape(raw_advice)
        advice_html = re.sub(r'\*\*([^\*]+)\*\*', r"<b>\1</b>", escaped_advice)
        report_data['ai_advice'] = advice_html.replace("\n", "<br>")
    else:
        report_data['ai_advice'] = ""
    report_data['timings']['ai_advice'] = time.time() - s_ia

    step += 1
    # 7. Validação de Tamanho e Qualidade de Imagens
    print(f"{Fore.YELLOW}[{step}] Validando dimensões e qualidade das imagens...")
    s_images = time.time()
    image_results = validate_image_sizes(epub_path, max_pixels=Config.MAX_IMAGE_PIXELS)
    report_data['invalid_images'] = image_results
    if image_results:
        print(f"{Fore.RED}    [      FALHOU      ] Imagens excedendo limite encontradas: {len(image_results)} itens")
    else:
        print(f"{Fore.GREEN}    [      PASSOU      ] Todas as imagens estão dentro do limite.")
    report_data['timings']['image_sizes'] = time.time() - s_images

    if is_secad:
        step += 1
        # 8. Atividades Interativas e Gabarito
        print(f"{Fore.YELLOW}[{step}] Validando exercícios interativos e Gabarito...")
        s_inter = time.time()
        inter_ok, inter_logs, inter_issues = validate_activities(epub_path)
        report_data['timings']['interactivity'] = time.time() - s_inter
        report_data['interactivity_logs'] = inter_logs
        report_data['interactivity_issues'] = inter_issues
        if inter_issues:
            print(f"{Fore.RED}    [      FALHOU      ] {len(inter_issues)} falhas em atividades interativas.")
        else:
            print(f"{Fore.GREEN}    [      PASSOU      ] Todas as atividades interativas validadas com sucesso.")
    else:
        inter_logs = []
        report_data['interactivity_logs'] = []
        report_data['interactivity_issues'] = []
    report_data['structure_logs'].extend(inter_logs)

    # Tempo total
    report_data['timings']['total'] = time.time() - start_total


    # 8. Geração do Relatório Final
    report_file = generate_html_report(epub_name, report_data)
    
    print(f"\n{Fore.GREEN}✔ Processo concluído para: {epub_name}")
    if image_results:
        print(f"{Fore.LIGHTRED_EX}👉 Alerta: {len(image_results)} imagens excedem o limite de pixels.")
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