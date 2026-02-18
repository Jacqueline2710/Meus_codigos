"""
Valida e verifica os certificados configurados para a API Petrobras.
"""
from __future__ import annotations

import os
import ssl
import sys
from pathlib import Path

from dotenv import load_dotenv


def _get_env(name: str, default: str | None = None) -> str | None:
    return os.getenv(name) or default


def validar_certificado_pem(caminho: Path) -> dict:
    """Valida um arquivo de certificado PEM."""
    resultado = {"ok": False, "erro": None, "detalhes": {}}
    try:
        from cryptography import x509
        from cryptography.hazmat.backends import default_backend

        data = caminho.read_bytes()
        if b"-----BEGIN CERTIFICATE-----" not in data:
            resultado["erro"] = "Formato invalido: nao e PEM (esperado -----BEGIN CERTIFICATE-----)"
            return resultado

        cert = x509.load_pem_x509_certificate(data, default_backend())
        resultado["ok"] = True
        resultado["detalhes"] = {
            "emissor": cert.issuer.rfc4514_string(),
            "assunto": cert.subject.rfc4514_string(),
            "valido_de": str(cert.not_valid_before_utc),
            "valido_ate": str(cert.not_valid_after_utc),
        }
    except Exception as e:
        resultado["erro"] = str(e)
    return resultado


def validar_ca_bundle(caminho: Path) -> dict:
    """Verifica se o bundle de CA esta correto."""
    resultado = {"ok": False, "erro": None, "num_certs": 0}
    try:
        data = caminho.read_bytes()
        count = data.count(b"-----BEGIN CERTIFICATE-----")
        resultado["num_certs"] = count
        resultado["ok"] = count > 0
        if count == 0:
            resultado["erro"] = "Nenhum certificado encontrado no bundle"
        # Verifica se contem CA Petrobras (base64 "UGV0cm9icmFz" = Petrobras)
        tem_petrobras = (
            b"petrobras" in data.lower()
            or b"Petrobras" in data
            or b"UGV0cm9icmFz" in data  # Petrobras em base64
        )
        resultado["tem_ca_petrobras"] = tem_petrobras
    except Exception as e:
        resultado["erro"] = str(e)
    return resultado


def main() -> None:
    load_dotenv()
    base_dir = Path(__file__).resolve().parents[1]

    print("=" * 60)
    print("VALIDACAO DE CERTIFICADOS - API PETROBRAS")
    print("=" * 60)

    # 1. Cadeia completa ou certificados individuais
    chain_path = _get_env("CORP_CA_CHAIN_PATH")
    if chain_path:
        path = Path(chain_path)
        if path.exists():
            print(f"\n1. Cadeia completa: {path.name}")
            r = validar_ca_bundle(path)
            print(f"   Certificados: {r['num_certs']}")
            print(f"   Contem CA Petrobras: {r.get('tem_ca_petrobras', '?')}")
            if r["ok"]:
                print("   [OK] Bundle valido")
        else:
            print(f"\n1. CORP_CA_CHAIN_PATH: NAO ENCONTRADO em {path}")
    if not chain_path or not Path(chain_path).exists():
        for env_name, label in [
            ("CORP_CA_CERT_PATH", "CA Intermediaria (Emissora)"),
            ("CORP_CA_ROOT_PATH", "CA Raiz (Root Corporativa)"),
        ]:
            corp_path_str = _get_env(env_name)
            if corp_path_str:
            for p in (x.strip() for x in corp_path_str.split(";") if x.strip()):
                corp_path = Path(p)
                if corp_path.exists():
                    print(f"\n1. {label}: {corp_path.name}")
                    r = validar_certificado_pem(corp_path)
                    if r["ok"]:
                        print("   [OK] Certificado valido")
                        for k, v in r["detalhes"].items():
                            print(f"   - {k}: {v}")
                    else:
                        print(f"   [ERRO] {r['erro']}")
                else:
                    print(f"\n1. {label}: NAO ENCONTRADO em {corp_path}")
            elif env_name == "CORP_CA_CERT_PATH":
                print("\n1. CORP_CA_CERT_PATH nao definido no .env")

    # 2. CA Bundle (para teste SSL)
    chain_path_obj = Path(chain_path) if chain_path else None
    bundle_path = chain_path_obj if (chain_path_obj and chain_path_obj.exists()) else base_dir / "ca_bundle.pem"
    print(f"\n2. CA Bundle para SSL: {bundle_path.name}")
    if bundle_path.exists():
        r = validar_ca_bundle(bundle_path)
        print(f"   Certificados no bundle: {r['num_certs']}")
        print(f"   Contem CA Petrobras: {r.get('tem_ca_petrobras', '?')}")
        if r["ok"]:
            print("   [OK] Bundle valido")
        else:
            print(f"   [ERRO] {r.get('erro', '')}")
    else:
        print("   [AVISO] ca_bundle.pem nao existe - sera criado ao rodar test_api_petrobras.py")

    # 3. Teste SSL (opcional)
    print("\n3. Teste de conexao SSL com apit.petrobras.com.br")
    verify = str(bundle_path) if bundle_path.exists() else True
    try:
        import urllib.request

        req = urllib.request.Request("https://apit.petrobras.com.br/")
        ctx = ssl.create_default_context(cafile=verify if isinstance(verify, str) else None)
        with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
            print("   [OK] Conexao SSL bem-sucedida")
    except ssl.SSLCertVerificationError as e:
        print(f"   [FALHA] {e}")
        print("\n   Causa provavel: falta a CA Raiz (Petrobras CA Root Corporativa).")
        print("   O certnew.cer e a CA Intermediaria; o servidor exige a cadeia completa.")
        print("   Solucoes:")
        print("   1. Obtenha o certificado raiz no portal PKI Petrobras e defina CORP_CA_ROOT_PATH no .env")
        print("   2. Ou use VERIFY_SSL=false no .env (apenas para teste em rede corporativa)")
    except Exception as e:
        print(f"   [ERRO] {e}")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
