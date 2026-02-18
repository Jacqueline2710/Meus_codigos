# RAG Contratos - Interface Web e Melhorias

## Novas funcionalidades

### 1. Interface Web (Streamlit)
Execute no navegador:
```bash
cd python
streamlit run app_streamlit.py
```
Acesse http://localhost:8501

### 2. Histórico de conversa
- Todas as perguntas e respostas são mantidas na sessão
- Botão "Limpar histórico" na barra lateral
- Permite perguntas de acompanhamento no contexto da conversa

### 3. Exportar respostas
- **TXT**: texto simples com pergunta, resposta e fontes
- **Word (.docx)**: documento formatado (requer python-docx)

### 4. Busca híbrida e chunking
- **Busca híbrida**: combina busca semântica (embeddings) + BM25 (palavras-chave)
- **Chunking para contratos**: trechos de 1500 caracteres, overlap de 200
- Melhor recuperação de cláusulas, ICJs e termos específicos

## Estrutura

- `main.py` - Interface de linha de comando
- `app_streamlit.py` - Interface web
- `rag_core.py` - Lógica compartilhada (busca híbrida, chunking, RAG)

## Dependências adicionais

```bash
pip install streamlit python-docx rank_bm25
```

## Reindexação

Para aplicar o novo chunking e busca híbrida, defina no `.env`:
```
REINDEX=true
```
Execute uma vez e depois comente a linha.
