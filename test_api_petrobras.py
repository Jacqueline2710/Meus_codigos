"""
Teste da API de modelos de linguagem OpenAI via APIM Petrobras.
Usa endpoint LiteLLM e header Ocp-Apim-Subscription-Key.
"""
from __future__ import annotations

import os
from pathlib import Path

import requests
from dotenv import load_dotenv


def _get_env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    if value:
        return value
    return default


def _setup_ca_verify(base_dir: Path):
    """Usa CORP_CA_CHAIN_PATH (cadeia completa) ou monta certifi + CA(s)."""
    chain_path = _get_env("CORP_CA_CHAIN_PATH")
    if chain_path:
        path = Path(chain_path)
        if path.exists():
            return str(path)
    corp_cert = _get_env("CORP_CA_CERT_PATH")
    corp_root = _get_env("CORP_CA_ROOT_PATH")
    cert_paths = []
    if corp_cert:
        cert_paths.extend(p.strip() for p in corp_cert.split(";") if p.strip())
    if corp_root:
        cert_paths.extend(p.strip() for p in corp_root.split(";") if p.strip())
    if not cert_paths:
        return True
    try:
        import certifi

        bundle_path = base_dir / "ca_bundle.pem"
        parts = [Path(certifi.where()).read_bytes()]
        for p in cert_paths:
            path = Path(p)
            if path.exists():
                parts.append(path.read_bytes())
        with open(bundle_path, "wb") as f:
            f.write(b"\n".join(parts))
        return str(bundle_path)
    except Exception:
        return True


def main() -> None:
    load_dotenv()

    base_dir = Path(__file__).resolve().parents[1]

    # Parâmetros do cenário Petrobras (produto "Contratos")
    endpoint = _get_env("LITELLM_BASE_URL") or (
        "https://apit.petrobras.com.br/ia/texto/v1/litellm/litellm"
    )
    api_key = _get_env("API_KEY_MODELOS_TEXTO")
    model = _get_env("LITELLM_MODEL") or "gpt-4"

    verify = _setup_ca_verify(base_dir)

    # Opção para rede corporativa com proxy/inspection SSL
    if _get_env("VERIFY_SSL", "true").lower() in ("false", "0", "no"):
        verify = False
        print("Aviso: VERIFY_SSL=false - SSL desabilitado (apenas para teste)")

    # USE_SYSTEM_CA=true: usa certificados do sistema, sem definir SSL_CERT_FILE
    if _get_env("USE_SYSTEM_CA", "").lower() in ("true", "1", "yes"):
        verify = True
        if "SSL_CERT_FILE" in os.environ:
            del os.environ["SSL_CERT_FILE"]
        if "REQUESTS_CA_BUNDLE" in os.environ:
            del os.environ["REQUESTS_CA_BUNDLE"]
        print("Aviso: USE_SYSTEM_CA=true - usando certificados do sistema (sem SSL_CERT_FILE)")
    elif verify and isinstance(verify, str):
        os.environ["REQUESTS_CA_BUNDLE"] = verify
        os.environ["SSL_CERT_FILE"] = verify

    if not api_key:
        print("Erro: defina API_KEY_MODELOS_TEXTO no .env")
        return

    headers = {
        "Ocp-Apim-Subscription-Key": api_key,
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": "Olá, IA Petrobras! Responda apenas 'ok' se está funcionando.",
            }
        ],
        "max_tokens": 50,
    }

    print(f"Endpoint: {endpoint}")
    print(f"Modelo: {model}")
    print(f"CA: {verify}")
    print("-" * 50)

    try:
        response = requests.post(
            endpoint,
            headers=headers,
            json=payload,
            verify=verify,
            timeout=30,
        )
        print(f"Status: {response.status_code}")
        print("Resposta:", response.text)
        if response.status_code == 200:
            print("\n✓ Credencial, endpoint e modelo estão corretos!")
        elif response.status_code == 401:
            print("\n✗ 401: Revise a API key, modelo ou endpoint.")
        else:
            print("\n✗ Erro. Experimente outros modelos (gpt-3.5-turbo, gpt-4-32k, etc.)")
    except requests.exceptions.SSLError as e:
        print(f"Erro SSL: {e}")
        print("Sugestões:")
        print("  1. Defina CORP_CA_CERT_PATH no .env com o CA corporativo (.pem)")
        print("  2. Em rede corporativa com proxy/inspection: VERIFY_SSL=false no .env")
    except Exception as e:
        print(f"Erro: {e}")


if __name__ == "__main__":
    main()
