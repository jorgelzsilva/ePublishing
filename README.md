# EPUB Validator Tool (ePublishing)

Ferramenta automatizada para validação técnica e análise de qualidade de arquivos EPUB, integrando o validador oficial da W3C com inteligência artificial para diagnósticos avançados.

## 🚀 Funcionalidades

- **Validação EPubCheck**: Execução do validador oficial para detectar erros fatais, erros e avisos.
- **Análise de Estrutura**: Verificação de TOC (Nav/NCX), PageList e integridade de âncoras internas.
- **Checagem de CSS**: Validação de regras específicas (ex: `.limitador`) e detecção de riscos para renderização em sistemas Binpar.
- **Visão Computacional (IA)**: Captura de tela automática de elementos complexos (tabelas, listas) e análise visual via Qwen3-VL para detectar sobreposições ou erros de layout.
- **Conselhos Técnicos (IA)**: Explicação didática dos erros do EPubCheck com sugestões de correção em texto simples.
- **Links Externos**: Teste de status (HTTP 200) para todos os links externos encontrados no conteúdo.
- **Validação de Interatividade**: Checagem de exercícios, IDs de `onclick` e consistência com o gabarito.

## 📂 Estrutura do Projeto

- `main.py`: Ponto de entrada que orquestra todo o fluxo de validação e gera o relatório HTML.
- `modules/`:
  - `structural.py`: Valida a navegação (TOC), créditos de editoração e integridade dos arquivos.
  - `css_checker.py`: Analisa arquivos CSS e a aplicação da estrutura `.limitador` nos XHTMLs.
  - `vision_ai.py`: Interface com IA para análise de imagens e geração de conselhos técnicos.
  - `interactivity.py`: Lógica para validar atividades interativas e gabaritos.
  - `link_validator.py`: Validador assíncrono de links externos.
- `prompts.txt`: Central de instruções para a IA, separada por tags para fácil manutenção.
- `input/`: Pasta onde os arquivos `.epub` devem ser colocados para processamento.
- `reports/`: Local de saída dos relatórios HTML e capturas de tela.

## 🛠️ Como Usar

### Pré-requisitos
1. **Java**: Necessário para rodar o `epubcheck.jar`.
2. **Python 3.10+**: Linguagem base do projeto.
3. **LM Studio** (Opcional): Para rodar os modelos de IA localmente na porta `1234`.

### Passo a Passo
1. **Clonar o Repositório**:
   ```bash
   git clone https://github.com/jorgelzsilva/ePublishing.git
   cd ePublishing
   ```

2. **Configurar Ambiente Virtual**:
   ```bash
   python -m venv epublishing
   source epublishing/bin/activate  # No Windows: .\epublishing\Scripts\activate
   ```

3. **Instalar Dependências**:
   ```bash
   pip install -r requirements.txt
   playwright install chromium
   ```

4. **Preparar Validação**:
   - Coloque seus arquivos `.epub` na pasta `input/`.
   - Certifique-se de que a pasta `epubcheck-5.1.0/` está na raiz com o arquivo `.jar`.

5. **Executar**:
   ```bash
   python main.py
   ```

6. **Ver Relatórios**:
   - Abra os arquivos gerados na pasta `reports/` no seu navegador.

## 🛡️ Segurança e Configuração
Os prompts da IA podem ser ajustados diretamente no arquivo `prompts.txt`. Para habilitar/desabilitar a análise de visão (que pode ser lenta), altere a variável `ENABLE_VISION_AI` no `main.py`.

---
*Desenvolvido para ePublishing - 2025*
