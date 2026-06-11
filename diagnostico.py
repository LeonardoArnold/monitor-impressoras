# -*- coding: utf-8 -*-
"""
diagnostico.py — Sonda UMA impressora e salva TUDO num arquivo de texto.

Para que serve: como o Claude nao consegue acessar a rede do hospital, esta
ferramenta coleta as respostas reais da impressora (SNMP + HTTP) para que ele
possa ver exatamente o formato e ajustar o programa com certeza.

Uso:
    python diagnostico.py
    (ele pergunta o IP e a senha)

Resultado: cria um arquivo "diagnostico_IP.txt" na mesma pasta.
Abra esse arquivo e mande o conteudo para o Claude.
A SENHA NAO e gravada no arquivo.
"""

import sys, io, re, ssl, socket
import urllib.request, urllib.parse, http.cookiejar

import snmp_engine as snmp


def linha(t=""):
    print(t)


def secao(titulo):
    print("\n" + "=" * 70)
    print(titulo)
    print("=" * 70)


def diag_snmp(ip):
    secao("1. SNMP PADRAO (suprimentos)")
    try:
        supplies = snmp.get_supplies(ip)
        if not supplies:
            linha("(nenhum suprimento retornado)")
        for s in supplies:
            linha("- desc=%r  level=%s  max=%s  pct=%s  status=%s" %
                  (s["desc"], s["level"], s["max"], s["pct"], s["status"]))
        toner, tambor = snmp._classificar(supplies)
        linha("")
        linha("Classificado -> TONER=%r  CILINDRO=%r" %
              (toner["desc"] if toner else None,
               tambor["desc"] if tambor else None))
    except socket.timeout:
        linha("SEM RESPOSTA SNMP (timeout). SNMP pode estar desligado.")
    except Exception as ex:
        linha("ERRO SNMP: %s" % ex)


def diag_snmp_brother(ip):
    secao("2. SNMP PRIVADO BROTHER (procurando toner em %)")
    # Sub-arvores conhecidas da Brother que costumam guardar nivel de toner
    bases = [
        "1.3.6.1.4.1.2435.2.3.9.4.2.1.5.5",
        "1.3.6.1.4.1.2435.2.4.3.99.3.1.6.1",
    ]
    for base in bases:
        linha("\n-- walk %s --" % base)
        try:
            res = snmp.snmp_walk(ip, base, timeout=2.0)
            if not res:
                linha("  (vazio)")
            for oid, tag, val in res[:30]:
                hexv = val.hex()
                try:
                    txt = val.decode("latin-1", "replace")
                    txt = "".join(c if 32 <= ord(c) < 127 else "." for c in txt)
                except Exception:
                    txt = ""
                inteiro = snmp._decode_int(val) if len(val) <= 4 else "-"
                linha("  %s  tag=0x%02x  int=%s  hex=%s  txt=%r" %
                      (oid, tag, inteiro, hexv[:40], txt[:30]))
        except socket.timeout:
            linha("  (timeout)")
        except Exception as ex:
            linha("  ERRO: %s" % ex)


def diag_http(ip, senha):
    secao("3. HTTP / LOGIN")
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(jar),
        urllib.request.HTTPSHandler(context=ctx),
    )
    opener.addheaders = [("User-Agent", "Mozilla/5.0")]
    base = "https://%s" % ip

    # 3a. paginas e seus formularios
    for page in ("/home/status.html", "/general/information.html?kind=item"):
        linha("\n-- GET %s%s --" % (base, page))
        try:
            r = opener.open(base + page, timeout=6)
            html = r.read().decode("utf-8", "replace")
            linha("   status=%s  url_final=%s  tamanho=%d" % (r.status, r.url, len(html)))
            form = snmp._parse_form(html, r.url)
            if form:
                linha("   FORM action=%s" % form["action"])
                linha("   FORM campo_senha=%s" % form["pwfield"])
                linha("   FORM campos=%s" % form["fields"])
            else:
                linha("   (sem formulario de senha nesta pagina)")
            # mostra trechos com 'toner' / 'tambor' / 'password'
            for termo in ("toner", "tambor", "password", "B_Pwd", "loginurl", "action="):
                idx = html.lower().find(termo.lower())
                if idx >= 0:
                    trecho = html[max(0, idx-40):idx+80].replace("\n", " ")
                    linha("   [%s] ...%s..." % (termo, trecho))
        except urllib.error.HTTPError as ex:
            linha("   HTTPError %s %s" % (ex.code, ex.reason))
        except Exception as ex:
            linha("   ERRO: %s" % ex)

    # 3b. tenta o login automatico do programa
    linha("\n-- LOGIN AUTOMATICO (mesma logica do programa) --")
    try:
        dados, erro = snmp._login_e_busca(ip, senha)
        linha("   resultado=%s  erro=%s" % (dados, erro))
    except Exception as ex:
        linha("   ERRO: %s" % ex)


def main():
    print("=== Diagnostico de impressora Brother ===\n")
    ip = input("IP da impressora (ex: 192.168.200.136): ").strip()
    if not re.match(r"^\d{1,3}(\.\d{1,3}){3}$", ip):
        print("IP invalido."); return
    senha = input("Senha da impressora (nao sera gravada): ").strip()

    # captura toda a saida
    buf = io.StringIO()
    old = sys.stdout
    sys.stdout = _Tee(old, buf)
    try:
        print("Impressora: %s" % ip)
        diag_snmp(ip)
        diag_snmp_brother(ip)
        diag_http(ip, senha)
    finally:
        sys.stdout = old

    # salva (sem a senha)
    nome = "diagnostico_%s.txt" % ip.replace(".", "-")
    with open(nome, "w", encoding="utf-8") as f:
        f.write(buf.getvalue())
    print("\n\nArquivo salvo: %s" % nome)
    print("Abra esse arquivo e mande o conteudo para o Claude.")
    input("\nPressione ENTER para sair.")


class _Tee:
    """Escreve na tela e no buffer ao mesmo tempo."""
    def __init__(self, *streams): self.streams = streams
    def write(self, s):
        for st in self.streams: st.write(s)
    def flush(self):
        for st in self.streams: st.flush()


if __name__ == "__main__":
    main()
