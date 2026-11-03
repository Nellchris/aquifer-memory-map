"""Check whether the hosts this project depends on are reachable.

Both Hub'Eau and BDLISA are BRGM-operated (*.eaufrance.fr, *.brgm.fr). On some
networks the TLS handshake to those names is reset by a filtering device while
unrelated hosts work fine; this script tells those cases apart.
"""
import socket
import ssl
import sys

HOSTS = [
    ("hubeau.eaufrance.fr", "Hub'Eau API — piezometry stations and chroniques"),
    ("bdlisa.eaufrance.fr", "BDLISA — aquifer entity reference and downloads"),
    ("services.sandre.eaufrance.fr", "Sandre — BDLISA WFS / referentials"),
    ("www.data.gouv.fr", "control host (unrelated, should always pass)"),
]


def probe(host, port=443, timeout=15):
    """Return (stage_reached, detail). Distinguishes DNS / TCP / TLS failure."""
    try:
        ip = socket.gethostbyname(host)
    except OSError as exc:
        return "DNS", str(exc)
    try:
        sock = socket.create_connection((host, port), timeout=timeout)
    except OSError as exc:
        return "TCP", f"{ip}: {exc}"
    try:
        ctx = ssl.create_default_context()
        with ctx.wrap_socket(sock, server_hostname=host):
            pass
    except OSError as exc:
        return "TLS", f"{ip}: {exc}"
    finally:
        sock.close()
    return "OK", ip


def main():
    width = max(len(h) for h, _ in HOSTS)
    failures = []
    for host, note in HOSTS:
        stage, detail = probe(host)
        print(f"{host:<{width}}  {stage:<4}  {detail}")
        print(f"{'':<{width}}        {note}")
        if stage != "OK":
            failures.append((host, stage, detail))

    print()
    if not failures:
        print("All hosts reachable. The pipeline can run.")
        return 0

    tls_only = [f for f in failures if f[1] == "TLS"]
    if tls_only and all(h != "www.data.gouv.fr" for h, _, _ in failures):
        print(
            "TCP connects but the TLS handshake is reset for the BRGM hosts while\n"
            "the control host works. That is SNI-based filtering between this\n"
            "machine and the API, not an API outage. Things to try:\n"
            "  - disable HTTPS/SSL scanning in local antivirus or security software\n"
            "  - allow *.eaufrance.fr and *.brgm.fr on the network firewall\n"
            "  - run from a different network, or over a VPN\n"
            "  - check the API status at https://api.gouv.fr/les-api/api_hubeau_piezometrie"
        )
    return 1


if __name__ == "__main__":
    sys.exit(main())
