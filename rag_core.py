"""
Nucleo do RAG - logica compartilhada entre CLI e interface web.
Suporta busca hibrida (semantica + BM25) e chunking otimizado para contratos.
"""
from __future__ import annotations

import os
import pickle
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
import httpx
from langchain_chroma import Chroma
from langchain_community.document_loaders import PyPDFLoader
from langchain_community.document_loaders import PyMuPDFLoader
from langchain_community.retrievers import BM25Retriever
from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.retrievers import BaseRetriever
from langchain_openai import AzureChatOpenAI, AzureOpenAIEmbeddings

from langchain_text_splitters import RecursiveCharacterTextSplitter


# Chunking otimizado para contratos: rapido e eficiente
CHUNK_SIZE = 1200       # Trechos medios - boa cobertura sem excesso de chunks
CHUNK_OVERLAP = 100     # Overlap reduzido - menos redundancia, indexacao mais rapida
RETRIEVER_K = 8         # Menos docs = recuperacao mais rapida

_RAG_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "Voce e um assistente especializado em extrair e apresentar informacoes dos contratos e documentos PDF da base. "
            "O contexto abaixo contem trechos extraidos dos arquivos. Sua tarefa e:\n"
            "1. Responder a pergunta usando APENAS as informacoes presentes no contexto.\n"
            "2. Use o historico da conversa (se fornecido) para entender perguntas de acompanhamento (ex: 'explique o item 2', 'qual o valor?').\n"
            "3. Sempre indicar de qual arquivo/fonte veio cada informacao (ex: conforme o arquivo X, pagina Y).\n"
            "4. Organize a resposta de forma clara. Liste itens quando apropriado (ex: ICJs, clausulas).\n"
            "5. Se a informacao nao estiver no contexto, diga que nao encontrou no material disponivel.",
        ),
        ("human", "{hist}\nPergunta: {question}\n\nContexto (trechos dos documentos da base):\n{context}"),
    ]
)


def _get_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(f"Variavel de ambiente ausente: {name}")
    return value


def _setup_ca_bundle(base_dir: Path) -> Path | None:
    chain_path = os.getenv("CORP_CA_CHAIN_PATH")
    if chain_path:
        path = Path(chain_path)
        if path.exists():
            return path
    corp_cert = os.getenv("CORP_CA_CERT_PATH")
    corp_root = os.getenv("CORP_CA_ROOT_PATH")
    cert_paths = []
    if corp_cert:
        cert_paths.extend(p.strip() for p in corp_cert.split(";") if p.strip())
    if corp_root:
        cert_paths.extend(p.strip() for p in corp_root.split(";") if p.strip())
    if not cert_paths:
        return None

    existing = [Path(p) for p in cert_paths if Path(p).exists()]
    if not existing:
        return None

    bundle_path = base_dir / "ca_bundle.pem"
    try:
        import certifi

        parts = [Path(certifi.where()).read_bytes()]
        for p in existing:
            parts.append(p.read_bytes())
        with open(bundle_path, "wb") as f:
            f.write(b"\n".join(parts))
        return bundle_path
    except Exception:
        return existing[0]


def _ensure_tiktoken_cache() -> None:
    cache_dir = os.getenv("TIKTOKEN_CACHE_DIR")
    if not cache_dir:
        return
    cache_path = Path(cache_dir)
    cache_path.mkdir(parents=True, exist_ok=True)


def _build_vectorstore(
    pdf_dir: Path, persist_dir: Path, embeddings: AzureOpenAIEmbeddings
) -> tuple[Chroma, list[Document] | None]:
    """Retorna (vectorstore, chunks para BM25 ou None)."""
    persist_dir.mkdir(parents=True, exist_ok=True)
    force_reindex = os.getenv("REINDEX", "").lower() in ("true", "1", "yes")
    chunks_file = persist_dir / "chunks.pkl"

    if not force_reindex and any(persist_dir.iterdir()):
        vectorstore = Chroma(
            persist_directory=str(persist_dir), embedding_function=embeddings
        )
        chunks = None
        if chunks_file.exists():
            try:
                with open(chunks_file, "rb") as f:
                    chunks = pickle.load(f)
            except Exception:
                pass
        return vectorstore, chunks

    if force_reindex and persist_dir.exists():
        shutil.rmtree(persist_dir)
        persist_dir.mkdir(parents=True, exist_ok=True)

    pdf_dir_resolved = pdf_dir.resolve()
    if not pdf_dir_resolved.exists():
        raise ValueError(f"Pasta nao encontrada: {pdf_dir_resolved}")

    pdf_files = sorted(pdf_dir_resolved.glob("**/*.pdf"))
    if not pdf_files:
        raise ValueError(f"Nenhum PDF encontrado em {pdf_dir_resolved}")

    # Carrega PDFs em paralelo (PyMuPDF primeiro - mais rapido)
    def _load_pdf(path: Path) -> list[Document]:
        try:
            return PyMuPDFLoader(str(path)).load()
        except Exception:
            try:
                return PyPDFLoader(str(path)).load()
            except Exception as e:
                print(f"Aviso: erro ao carregar {path.name}: {e}")
                return []

    documents = []
    with ThreadPoolExecutor(max_workers=4) as ex:
        for doc_list in ex.map(_load_pdf, pdf_files):
            documents.extend(doc_list)

    for doc in documents:
        src = doc.metadata.get("source", "")
        if src:
            doc.metadata["filename"] = Path(src).name

    # Separadores para contratos: paragrafos, clausulas, linhas (evita cortes no meio)
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n\n", "\n\n", "\n", ". ", " ", ""],
        length_function=len,
    )
    chunks = splitter.split_documents(documents)

    with open(chunks_file, "wb") as f:
        pickle.dump(chunks, f)

    print(f"Indexando {len(chunks)} trechos de {len(documents)} pagina(s) em {len(pdf_files)} arquivo(s)...")

    vectorstore = Chroma.from_documents(
        chunks, embeddings, persist_directory=str(persist_dir)
    )
    return vectorstore, chunks


class _HybridRetriever(BaseRetriever):
    """Combina busca semantica e BM25 (keyword)."""

    def __init__(self, semantic_retriever: BaseRetriever, bm25_retriever: BM25Retriever, k: int = RETRIEVER_K):
        super().__init__()
        self.semantic = semantic_retriever
        self.bm25 = bm25_retriever
        self.k = k

    def _get_relevant_documents(self, query: str) -> list[Document]:
        seen: set[tuple[str, str]] = set()
        result: list[Document] = []

        def _add(doc: Document) -> None:
            key = (doc.page_content[:100], doc.metadata.get("source", ""))
            if key not in seen:
                seen.add(key)
                result.append(doc)

        with ThreadPoolExecutor(max_workers=2) as ex:
            f_sem = ex.submit(self.semantic.invoke, query)
            f_bm25 = ex.submit(self.bm25.invoke, query)
            for doc in f_sem.result()[: self.k // 2]:
                _add(doc)
            for doc in f_bm25.result()[: self.k - len(result)]:
                _add(doc)
        return result[: self.k]


def _create_retriever(
    vectorstore: Chroma, chunks: list[Document] | None, use_hybrid: bool = True
) -> BaseRetriever:
    """Cria retriever (hibrido ou apenas semantico)."""
    semantic_retriever = vectorstore.as_retriever(search_kwargs={"k": RETRIEVER_K})

    if use_hybrid and chunks:
        try:
            bm25_retriever = BM25Retriever.from_documents(chunks, k=RETRIEVER_K // 2)
            return _HybridRetriever(semantic_retriever, bm25_retriever)
        except Exception:
            pass
    return semantic_retriever


_TERMOS_BASE = frozenset(("na base", "na pasta", "na pasta base", "base de"))
_TERMOS_ARQUIVO = frozenset(("pdf", "pdfs", "arquivo", "arquivos", "documento", "documentos"))


def _is_question_about_pdfs_in_base(question: str) -> bool:
    q = question.lower().strip()
    tem_base = any(t in q for t in _TERMOS_BASE) or ("base" in q and ("esta" in q or "tem" in q))
    tem_arquivo = any(t in q for t in _TERMOS_ARQUIVO) or "quais" in q or "lista" in q
    return tem_base and (tem_arquivo or "quais" in q or "lista" in q or "o que" in q)


def _list_pdfs_in_base(pdf_dir: Path) -> tuple[str, list]:
    pdf_dir_resolved = pdf_dir.resolve()
    if not pdf_dir_resolved.exists():
        return f"A pasta Base nao foi encontrada em {pdf_dir_resolved}.", []
    pdf_files = sorted(pdf_dir_resolved.glob("**/*.pdf"))
    if not pdf_files:
        return "Nenhum arquivo PDF encontrado na pasta Base.", []
    linhas = [f"{i + 1}. {p.name}" for i, p in enumerate(pdf_files)]
    resposta = f"Os seguintes {len(pdf_files)} arquivo(s) PDF estao na base:\n\n" + "\n".join(linhas)
    return resposta, []


def _get_source_label(doc: Document) -> str:
    source = doc.metadata.get("source", "")
    page = doc.metadata.get("page", "")
    if source:
        nome_arquivo = Path(source).name
        if page is not None and str(page).strip():
            return f"{nome_arquivo} (pagina {page})"
        return nome_arquivo
    return "Documento"


def answer_question(
    question: str,
    retriever: BaseRetriever,
    llm: AzureChatOpenAI,
    pdf_dir: Path,
    *,
    history: list[tuple[str, str]] | None = None,
    filter_source: str | None = None,
    vectorstore: Chroma | None = None,
) -> tuple[str, list[Document]]:
    """Responde pergunta usando RAG ou lista de PDFs.
    history: ultimas (pergunta, resposta) para contexto de acompanhamento.
    filter_source: nome do arquivo para filtrar (ex: Contrato 5900.0122983.22.2.pdf).
    """
    if _is_question_about_pdfs_in_base(question):
        resposta, _ = _list_pdfs_in_base(pdf_dir)
        return resposta, []

    if filter_source and vectorstore:
        # Chroma: $eq para filename; fallback: busca sem filtro e filtra em Python
        filter_dict = {"filename": {"$eq": filter_source}}
        try:
            docs = vectorstore.similarity_search(question, k=RETRIEVER_K, filter=filter_dict)
        except Exception:
            docs = []
        if not docs:
            # Indice antigo sem metadata filename: busca e filtra por source
            all_docs = vectorstore.similarity_search(question, k=RETRIEVER_K * 2)
            docs = [d for d in all_docs if filter_source in d.metadata.get("source", "") or
                    d.metadata.get("filename", "") == filter_source]
            docs = docs[:RETRIEVER_K]
    else:
        docs = retriever.invoke(question)
    if not docs:
        return (
            "Nenhum trecho relevante encontrado nos documentos. "
            "Tente reformular a pergunta ou defina REINDEX=true no .env para reindexar.",
            [],
        )

    context = "\n\n".join(
        f"[Fonte {i + 1} - {_get_source_label(doc)}]\n{doc.page_content}"
        for i, doc in enumerate(docs)
    )

    hist_text = ""
    if history:
        hist_parts = ["\n\nHistorico da conversa (para contexto):\n"]
        hist_parts.extend(f"P: {p}\nR: {r}\n\n" for p, r in history[-5:])
        hist_text = "".join(hist_parts)

    chain = _RAG_PROMPT | llm
    response = chain.invoke({
        "question": question,
        "context": context,
        "hist": hist_text,
    })
    return response.content, docs


def suggest_follow_up_questions(question: str, answer: str, llm: Any) -> list[str]:
    """Gera sugestoes de perguntas de acompanhamento com base na pergunta e resposta."""
    from langchain_core.prompts import ChatPromptTemplate

    prompt = ChatPromptTemplate.from_messages([
        (
            "system",
            "Voce gera sugestoes de perguntas de acompanhamento. Com base na pergunta e resposta fornecidas, "
            "liste 4 a 6 perguntas curtas que o usuario poderia fazer em seguida (ex: 'Explique melhor o item 2', "
            "'Qual o valor mencionado?', 'Quais sao os prazos?'). Uma por linha, sem numeracao.",
        ),
        ("human", "Pergunta: {question}\n\nResposta: {answer}\n\nSugestoes de proximas perguntas:"),
    ])
    try:
        response = (prompt | llm).invoke({"question": question, "answer": answer})
        lines = [s.strip() for s in response.content.strip().split("\n") if s.strip()]
        return lines[:6] if lines else []
    except Exception:
        return []


def rebuild_rag(base_dir: Path, rag_components: dict[str, Any]) -> dict[str, Any]:
    """Forca reindexacao (apos upload de PDFs)."""
    os.environ["REINDEX"] = "true"
    try:
        return init_rag(base_dir)
    finally:
        os.environ.pop("REINDEX", None)


def init_rag(base_dir: Path) -> dict[str, Any]:
    """Inicializa RAG e retorna componentes (retriever, llm, pdf_dir, etc)."""
    load_dotenv()
    _setup_ca_bundle(base_dir)
    _ensure_tiktoken_cache()

    verify_ssl = os.getenv("VERIFY_SSL", "true").lower() not in ("false", "0", "no")
    if not verify_ssl:
        for k in ("REQUESTS_CA_BUNDLE", "SSL_CERT_FILE"):
            os.environ.pop(k, None)
        ssl_verify = False
    elif os.getenv("USE_SYSTEM_CA", "").lower() in ("true", "1", "yes"):
        for k in ("REQUESTS_CA_BUNDLE", "SSL_CERT_FILE"):
            os.environ.pop(k, None)
        ssl_verify = True
    else:
        ca = _setup_ca_bundle(base_dir)
        if ca:
            os.environ["REQUESTS_CA_BUNDLE"] = str(ca)
            os.environ["SSL_CERT_FILE"] = str(ca)
            ssl_verify = str(ca)
        else:
            ssl_verify = True

    endpoint = _get_env("AZURE_OPENAI_ENDPOINT")
    api_key = _get_env("API_KEY_MODELOS_TEXTO")
    api_version = _get_env("AZURE_OPENAI_API_VERSION")
    chat_deployment = _get_env("AZURE_OPENAI_CHAT_DEPLOYMENT")
    embed_deployment = _get_env("AZURE_OPENAI_EMBEDDINGS_DEPLOYMENT")
    apim_headers = {"Ocp-Apim-Subscription-Key": api_key}

    http_client = httpx.Client(verify=ssl_verify)
    llm = AzureChatOpenAI(
        azure_endpoint=endpoint,
        api_key=api_key,
        api_version=api_version,
        azure_deployment=chat_deployment,
        temperature=0.1,
        http_client=http_client,
        default_headers=apim_headers,
    )
    embeddings = AzureOpenAIEmbeddings(
        azure_endpoint=endpoint,
        api_key=api_key,
        api_version=api_version,
        azure_deployment=embed_deployment,
        http_client=http_client,
        default_headers=apim_headers,
    )

    pdf_dir = base_dir / "Base"
    persist_dir = base_dir / "vectorstore"

    vectorstore, chunks = _build_vectorstore(pdf_dir, persist_dir, embeddings)
    retriever = _create_retriever(vectorstore, chunks)

    return {
        "retriever": retriever,
        "vectorstore": vectorstore,
        "llm": llm,
        "pdf_dir": pdf_dir,
        "get_source_label": _get_source_label,
    }
