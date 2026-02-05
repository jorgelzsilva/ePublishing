import zipfile
import re
from colorama import Fore

def validate_css_rules(epub_path):
    """Verifica regras de estilo no CSS: .limitador e riscos de renderização Binpar."""
    results = {"limitador_ok": False, "binpar_risks": []}
    
    try:
        with zipfile.ZipFile(epub_path, 'r') as z:
            css_files = [f for f in z.namelist() if f.endswith('.css')]
            
            for css_file in css_files:
                with z.open(css_file) as f:
                    content = f.read().decode('utf-8', errors='ignore')
                    
                    # Busca robusta por .limitador { width: 40em; } (suporta espaços e variações)
                    if re.search(r'\.limitador\s*\{[^}]*width\s*:\s*40em', content, re.IGNORECASE):
                        results["limitador_ok"] = True
                    
                    # Detecta counters e pseudo-elementos (Problemas comuns na Binpar)
                    counters = re.findall(r'counter-(?:reset|increment)\s*:', content)
                    pseudos = re.findall(r'::before|::after', content)
                    
                    if counters or pseudos:
                        results["binpar_risks"].append({
                            "file": css_file,
                            "has_counters": len(counters) > 0,
                            "has_pseudos": len(pseudos) > 0
                        })
        return results
    except Exception as e:
        print(f"{Fore.RED}    [      FALHOU      ] Erro ao analisar arquivos CSS: {e}")
        return results

def validate_limitador_and_structures(epub_path, is_secad=False):
    """
    Varredura nos XHTMLs:
    1. Verifica ausência da div .limitador (exceto para Secad).
    2. Detecta estruturas complexas que quebram na Binpar (listas em tabelas/divs).
    """
    analysis_results = {
        "missing_limitador": [],
        "binpar_complex_warnings": [],
        "detailed_logs": []
    }
    
    try:
        with zipfile.ZipFile(epub_path, 'r') as z:
            # Filtra apenas arquivos de conteúdo, ignorando navegação
            html_files = [f for f in z.namelist() if f.endswith(('.xhtml', '.html')) and 'nav' not in f.lower()]
            
            for html in html_files:
                with z.open(html) as f:
                    content = f.read().decode('utf-8', errors='ignore')
                    
                    file_log = []
                    
                    # 1. Checagem da div .limitador (exceto para Secad)
                    if not is_secad:
                        if not re.search(r'class\s*=\s*["\'][^"\']*limitador[^"\']*["\']', content, re.IGNORECASE):
                            analysis_results["missing_limitador"].append(html)
                            file_log.append("<span style='font-family:monospace; color:#c0392b;'>[ FALHOU ]</span>")
                        else:
                            file_log.append("<span style='font-family:monospace; color:#27ae60;'>[ PASSOU ]</span>")
                    
                    # 2. Checagem de estruturas complexas (Binpar High Risk)
                    # Lista dentro de Tabela
                    if "<table>" in content and ("<ul>" in content or "<ol>" in content):
                        msg = f"{html} (Lista dentro de Tabela)"
                        analysis_results["binpar_complex_warnings"].append(msg)
                        file_log.append("<span style='font-family:monospace; color:#f39c12;'>[ AVISO  ]</span> Estrutura complexa: Lista dentro de Tabela")
                    
                    # Lista dentro de Div (Risco Médio)
                    elif "<div>" in content and ("<ul>" in content or "<ol>" in content):
                        # Só alerta se houver uma div imediatamente pai ou próxima
                        msg = f"{html} (Lista dentro de Div)"
                        analysis_results["binpar_complex_warnings"].append(msg)
                        file_log.append("<span style='font-family:monospace; color:#f39c12;'>[ AVISO  ]</span> Estrutura complexa: Lista dentro de Div")
                    
                    # Determinação do status consolidado para o prefixo
                    if any("FALHOU" in s for s in file_log):
                        status_marker = "<span style='font-family:monospace; color:#c0392b;'>[ FALHOU ]</span>"
                    elif any("AVISO" in s for s in file_log):
                        status_marker = "<span style='font-family:monospace; color:#f39c12;'>[ AVISO  ]</span>"
                    elif any("PASSOU" in s for s in file_log):
                        status_marker = "<span style='font-family:monospace; color:#27ae60;'>[ PASSOU ]</span>"
                    else:
                        # Arquivo sem validações ativas (ex: Secad sem .limitador e sem estruturas complexas)
                        status_marker = "<span style='font-family:monospace; color:#27ae60;'>[ PASSOU ]</span>"
                    
                    # Limpeza dos detalhes (remove os marcadores internos para evitar redundância)
                    clean_details = []
                    for log in file_log:
                        # Remove a tag span do status
                        msg = re.sub(r'<span[^>]*>\[.*?\]</span>\s*', '', log).strip()
                        if msg: clean_details.append(msg)
                    
                    if not clean_details:
                        if "PASSOU" in status_marker and not is_secad:
                            details = "Div .limitador presente"
                        elif "FALHOU" in status_marker:
                            details = "Div .limitador ausente"
                        else:
                            # Secad ou sem problemas estruturais
                            details = "Verificação estrutural OK"
                    else:
                        details = "; ".join(clean_details)
                    
                    # Só adiciona ao log se houver algo relevante ou for não-Secad
                    if not is_secad or clean_details:
                        analysis_results["detailed_logs"].append(f"{status_marker} 📄 {html}: {details}")
            
            if analysis_results["detailed_logs"]:
                analysis_results["detailed_logs"].insert(0, "<br>📄 <strong>Detalhamento: Classe .limitador e Estruturas</strong>")
        
        # Logs de console para feedback imediato
        if analysis_results["missing_limitador"]:
            print(f"{Fore.RED}    [      FALHOU      ] .limitador AUSENTE em {len(analysis_results['missing_limitador'])} arquivos.")
        else:
            print(f"{Fore.GREEN}    [      PASSOU      ] Classe .limitador aplicada em todos os arquivos.")
            
        return analysis_results
    except Exception as e:
        print(f"{Fore.RED}    [      FALHOU      ] Erro na varredura de XHTML: {e}")
        analysis_results["detailed_logs"].append(f"<span style='font-family:monospace; color:#c0392b;'>[      FALHOU      ]</span> Erro crítico na varredura: {str(e)}")
        return analysis_results