"""
RAG Contratos - Interface de linha de comando.
Usa rag_core para logica compartilhada (busca hibrida, chunking).
Suporta historico de conversa, filtro por documento e comandos inline.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from dotenv import load_dotenv

from rag_core import answer_question, init_rag


def main() -> None:
    parser = argparse.ArgumentParser(description="Contratos - Consulta via CLI")
    parser.add_argument(
        "-f", "--filter",
        metavar="ARQUIVO",
        help="Filtrar busca por documento (ex: Contrato 5900.0122983.22.2.pdf)",
    )
    args = parser.parse_args()

    load_dotenv()

    base_dir = Path(__file__).resolve().parents[1]
    rag = init_rag(base_dir)

    history: list[tuple[str, str]] = []
    filter_source = args.filter

    pdf_dir = rag["pdf_dir"]
    pdf_files = sorted(pdf_dir.glob("**/*.pdf")) if pdf_dir.exists() else []
    pdf_names = {p.name for p in pdf_files}
    print("RAG pronto. Digite sua pergunta (ENTER vazio para sair).")
    print("Comandos: /filter ARQUIVO ou /filter off | /historico | /limpar")
    if pdf_files:
        print("\nDocumentos na base:")
        for i, p in enumerate(pdf_files, 1):
            print(f"  {i}. {p.name}")
    if filter_source:
        print(f"\nFiltro ativo: {filter_source}")
    print()

    while True:
        question = input("Pergunta: ").strip()
        if not question:
            break

        # Comandos inline
        if question.startswith("/filter "):
            val = question[8:].strip()
            if val.lower() == "off":
                filter_source = None
                print("Filtro desativado.")
            elif val in pdf_names:
                filter_source = val
                print(f"Filtro definido: {filter_source}")
            else:
                print(f"Arquivo nao encontrado. Use um dos listados acima.")
            continue
        if question == "/historico":
            if not history:
                print("Nenhuma pergunta anterior.")
            else:
                for i, (p, r) in enumerate(history[-5:], 1):
                    preview = r[:200] + "..." if len(r) > 200 else r
                    print(f"\n--- {i} ---\nP: {p}\nR: {preview}")
            continue
        if question == "/limpar":
            history.clear()
            print("Historico limpo.")
            continue

        print("Processando... ", end="", flush=True)
        answer, sources = answer_question(
            question,
            rag["retriever"],
            rag["llm"],
            rag["pdf_dir"],
            history=history,
            filter_source=filter_source,
            vectorstore=rag.get("vectorstore"),
        )
        history.append((question, answer))
        if len(history) > 5:
            history = history[-5:]

        print("Pronto.\n\nResposta:\n", answer)
        if sources:
            print("\nFontes consultadas:")
            for idx, doc in enumerate(sources, 1):
                label = rag["get_source_label"](doc)
                print(f"  {idx}. {label}")
        print()


if __name__ == "__main__":
    main()
