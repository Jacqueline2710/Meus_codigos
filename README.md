# Consulta de dados contratuais - DGRTA

Chat para perguntas e respostas baseadas em arquivos/documentos dos contratos da DGRTA. Utiliza RAG (Retrieval-Augmented Generation) com busca híbrida (semântica + BM25) e integração com API de modelos da Petrobras.

## Estrutura do projeto

```
IA_Contratos/
├── Base/                    # PDFs dos contratos (adicionar ou fazer upload)
├── assets/
│   └── banner_dgrta.png     # Banner do cabeçalho
├── vectorstore/             # Índice vetorial (gerado automaticamente)
├── python/
│   ├── app_streamlit.py     # Interface web (Streamlit)
│   ├── main.py              # Interface CLI
│   ├── rag_core.py          # Lógica RAG compartilhada
│   ├── test_api_petrobras.py # Teste da API
│   ├── validar_certificado.py # Validação de certificados SSL
│   └── run_app.bat          # Iniciar aplicação web
├── .env                     # Configurações (criar a partir do .env.example)
├── requirements.txt        # Dependências Python
└── README.md
```

## Requisitos

- Python 3.10+
- Acesso à rede Petrobras (API APIM)
- Certificados corporativos (se aplicável)

## Instalação

1. Clone ou copie o projeto para sua máquina.

2. Crie um ambiente virtual (recomendado):
   ```bash
   python -m venv venv
   venv\Scripts\activate   # Windows
   ```

3. Instale as dependências:
   ```bash
   pip install -r requirements.txt
   ```

4. Configure o arquivo `.env` (veja seção [Configuração](#configuração)).

5. Coloque os PDFs dos contratos na pasta `Base/`.

## Configuração

Crie um arquivo `.env` na raiz do projeto com as variáveis necessárias. Exemplo:

```env
# API Petrobras - chave do produto
API_KEY_MODELOS_TEXTO=sua_chave_aqui

# Endpoints
AZURE_OPENAI_ENDPOINT=https://apit.petrobras.com.br/ia/openai/v1/openai-azure
AZURE_OPENAI_API_VERSION=2024-02-15-preview
AZURE_OPENAI_CHAT_DEPLOYMENT=gpt-5-chat-petrobras
AZURE_OPENAI_EMBEDDINGS_DEPLOYMENT=embedding-3-large-global

# Certificados SSL (rede corporativa)
CORP_CA_CHAIN_PATH=caminho/para/ca_bundle.pem
VERIFY_SSL=false

# Cache tiktoken (opcional)
TIKTOKEN_CACHE_DIR=./tiktoken_cache

# Reindexar PDFs (usar apenas quando necessário)
# REINDEX=true
```

### Variáveis principais

| Variável | Descrição |
|----------|-----------|
| `API_KEY_MODELOS_TEXTO` | Chave APIM para acesso à API de modelos |
| `AZURE_OPENAI_ENDPOINT` | Endpoint da API Azure OpenAI (Petrobras) |
| `AZURE_OPENAI_CHAT_DEPLOYMENT` | Nome do deployment do modelo de chat |
| `AZURE_OPENAI_EMBEDDINGS_DEPLOYMENT` | Nome do deployment de embeddings |
| `CORP_CA_CHAIN_PATH` | Caminho para cadeia de certificados CA |
| `VERIFY_SSL` | `false` para desabilitar verificação SSL (rede corporativa) |
| `REINDEX` | `true` para forçar reindexação dos PDFs |

## Como executar

### Interface web (Streamlit)

**Opção 1 – Script batch (Windows):**
```
Executar: python\run_app.bat
```

**Opção 2 – Linha de comando:**
```bash
cd python
python -m streamlit run app_streamlit.py
```

A aplicação abre em `http://localhost:8501`.

### Interface CLI

```bash
cd python
python main.py
```

**Com filtro por documento:**
```bash
python main.py -f "Contrato 5900.0122983.22.2.pdf"
```

**Comandos disponíveis na CLI:**
- `/filter ARQUIVO` – Filtrar busca por documento
- `/filter off` – Desativar filtro
- `/historico` – Ver últimas perguntas e respostas
- `/limpar` – Limpar histórico

## Funcionalidades

- **Chat com histórico** – Perguntas de acompanhamento (ex.: "Explique o item 2")
- **Upload de PDFs** – Envio de novos documentos pela interface web
- **Filtro por documento** – Buscar apenas em um contrato específico
- **Exportação** – Respostas em TXT, Word, Excel e PDF
- **Busca híbrida** – Semântica + BM25 para melhor recuperação

## Dependências principais

- `streamlit` – Interface web
- `langchain-chroma` – Vector store
- `langchain-openai` – Modelos e embeddings (Azure)
- `langchain-community` – Loaders de PDF
- `pypdf` / `pymupdf` – Leitura de PDFs
- `rank_bm25` – Busca por palavras-chave
- `python-docx` – Exportação Word
- `openpyxl` – Exportação Excel
- `reportlab` – Exportação PDF

## Solução de problemas

| Problema | Solução |
|----------|---------|
| Erro de certificado SSL | Configure `VERIFY_SSL=false` ou `CORP_CA_CHAIN_PATH` |
| Nenhum PDF encontrado | Verifique se a pasta `Base/` existe e contém PDFs |
| Respostas vazias | Defina `REINDEX=true` no `.env` e reinicie |
| API não responde | Verifique `API_KEY_MODELOS_TEXTO` e conectividade de rede |
