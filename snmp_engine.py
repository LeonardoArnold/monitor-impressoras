# -*- coding: utf-8 -*-
"""
snmp_engine.py — CAMADA DE COLETA DE DADOS
==========================================
Fluxo real confirmado contra Brother DCP-L5512DN:

  1. SNMP (UDP 161) — sem senha
     Cilindro: retorna % corretamente.
     Toner: retorna -3 ("tem toner, sem % numerica via SNMP").

  2. Login HTTPS (urllib + cookiejar) — para obter o % do toner:
     a. GET /general/information.html  →  impressora redireciona para
        /etc/timeouterror.html?url=...  (pagina de login, so campo senha)
     b. Extrai o campo hidden "url" ou "loginurl" do formulario
     c. POST /etc/mnt_info.html  com  B_Pwd=SENHA & url=... & loginurl=...
     d. Impressora define cookie de sessao e redireciona para a pagina de
        manutencao com Toner% e Cilindro%
     e. Extrai os valores com regex
"""

import socket, re, ssl, urllib.request, urllib.parse, http.cookiejar

COMMUNITY    = "public"
TIMEOUT      = 2.5
HTTP_TIMEOUT = 6.0

OID_SUPPLY_DESC = "1.3.6.1.2.1.43.11.1.1.6.1"
OID_SUPPLY_MAX  = "1.3.6.1.2.1.43.11.1.1.8.1"
OID_SUPPLY_LVL  = "1.3.6.1.2.1.43.11.1.1.9.1"


# ── SNMP (BER encoding) ───────────────────────────────────────────────────
def _encode_length(n):
    if n < 0x80: return bytes([n])
    out = b""
    while n > 0: out = bytes([n & 0xFF]) + out; n >>= 8
    return bytes([0x80 | len(out)]) + out

def _tlv(tag, v): return bytes([tag]) + _encode_length(len(v)) + v

def _encode_int(v):
    l = 1
    while True:
        try: b = int(v).to_bytes(l, "big", signed=True); break
        except OverflowError: l += 1
    return _tlv(0x02, b)

def _encode_oid(oid):
    p = [int(x) for x in oid.split(".")]
    body = bytes([40*p[0]+p[1]])
    for arc in p[2:]:
        if arc < 0x80: body += bytes([arc])
        else:
            s = []
            while arc > 0: s.append(arc & 0x7F); arc >>= 7
            s.reverse()
            for i in range(len(s)-1): body += bytes([s[i] | 0x80])
            body += bytes([s[-1]])
    return _tlv(0x06, body)

def _read_tlv(data, off):
    tag = data[off]; off += 1
    l = data[off]; off += 1
    if l & 0x80:
        n = l & 0x7F; l = int.from_bytes(data[off:off+n],"big"); off += n
    return tag, data[off:off+l], off+l

def _decode_oid(d):
    if not d: return ""
    arcs = [d[0]//40, d[0]%40]; val = 0
    for b in d[1:]:
        val = (val<<7)|(b&0x7F)
        if not (b&0x80): arcs.append(val); val = 0
    return ".".join(str(a) for a in arcs)

def _decode_int(d): return int.from_bytes(d,"big",signed=True) if d else 0

def _build_getnext(community, oid, req_id):
    vb  = _tlv(0x30, _encode_oid(oid)+_tlv(0x05,b""))
    pdu = _tlv(0xA1, _encode_int(req_id)+_encode_int(0)+_encode_int(0)+_tlv(0x30,vb))
    return _tlv(0x30, _encode_int(1)+_tlv(0x04, community.encode("latin-1"))+pdu)

def _parse_response(data):
    _, seq, _ = _read_tlv(data, 0)
    _, _, off = _read_tlv(seq, 0)
    _, _, off = _read_tlv(seq, off)
    _, pdu, _ = _read_tlv(seq, off)
    _, _, o = _read_tlv(pdu, 0); _, _, o = _read_tlv(pdu, o); _, _, o = _read_tlv(pdu, o)
    _, vblist, _ = _read_tlv(pdu, o)
    _, vb, _ = _read_tlv(vblist, 0)
    _, ob, p = _read_tlv(vb, 0)
    vt = vb[p]; _, vv, _ = _read_tlv(vb, p)
    return _decode_oid(ob), vt, vv

def snmp_walk(host, base_oid, community=COMMUNITY, timeout=TIMEOUT):
    results = []; current = base_oid
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout); req_id = 1
    try:
        while True:
            sock.sendto(_build_getnext(community, current, req_id), (host, 161))
            req_id += 1
            data, _ = sock.recvfrom(8192)
            oid, tag, val = _parse_response(data)
            if tag in (0x80,0x81,0x82): break
            if oid != base_oid and not oid.startswith(base_oid+"."): break
            results.append((oid, tag, val)); current = oid
            if len(results) > 200: break
    finally:
        sock.close()
    return results


# ── SNMP alto nivel ───────────────────────────────────────────────────────
def get_supplies(host, community=COMMUNITY, timeout=TIMEOUT):
    def walk_map(base):
        return {oid.split(".")[-1]: val
                for oid, _, val in snmp_walk(host, base, community, timeout)}
    rd = walk_map(OID_SUPPLY_DESC)
    rm = walk_map(OID_SUPPLY_MAX)
    rl = walk_map(OID_SUPPLY_LVL)
    out = []
    for idx, db in rd.items():
        desc = db.decode("latin-1","replace").strip()
        mx = _decode_int(rm[idx]) if idx in rm else None
        lv = _decode_int(rl[idx]) if idx in rl else None
        pct = status = None
        if lv is not None and mx is not None and mx > 0 and lv >= 0:
            pct = round(lv / mx * 100)
        elif lv == -3: status = "OK"
        elif lv == -2: status = "?"
        out.append({"desc":desc,"pct":pct,"status":status,"level":lv,"max":mx})
    return out

def _classificar(supplies):
    toner = drum = None
    for s in supplies:
        low = s["desc"].lower()
        if toner is None and "toner" in low: toner = s
        elif drum is None and ("drum" in low or "tambor" in low or "opc" in low): drum = s
    return toner, drum



# ── HTTP com login (le o formulario automaticamente) ──────────────────────
def _ssl_ctx():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode    = ssl.CERT_NONE
    return ctx

def _novo_opener():
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(jar),
        urllib.request.HTTPSHandler(context=_ssl_ctx()),
    )
    opener.addheaders = [
        ("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"),
        ("Accept", "text/html,application/xhtml+xml,*/*"),
    ]
    return opener, jar

def _extrair(html, label_re):
    m = re.search(label_re + r'[^<]{0,20}</[^>]+>\s*(?:<[^>]+>\s*)*(\d+)%',
                  html, re.S | re.I)
    return int(m.group(1)) if m else None

def _login_ok(html):
    """True se o HTML parece ser a pagina de manutencao (login bem-sucedido)."""
    if re.search(r'B_Pwd|timeouterror|Tempo.limite|Iniciar.sess|type=["\']?password', html, re.I):
        return False
    return bool(re.search(r'\d+%', html))

def _parse_form(html, page_url):
    """Acha o formulario de login (o que tem campo de senha) e devolve
       action absoluta, todos os campos e o nome do campo de senha."""
    for f in re.findall(r'<form\b[^>]*>.*?</form>', html, re.I | re.S):
        if not re.search(r'type=["\']?password', f, re.I):
            continue
        am = re.search(r'<form\b[^>]*\baction=["\']?([^"\'\s>]+)', f, re.I)
        action = urllib.parse.urljoin(page_url, am.group(1) if am else page_url)
        fields = {}; pwfield = None
        for inp in re.findall(r'<input\b[^>]*>', f, re.I):
            nm = re.search(r'\bname=["\']?([^"\'\s>]+)', inp, re.I)
            if not nm:
                continue
            name = nm.group(1)
            vm = re.search(r'\bvalue=["\']?([^"\'>]*)', inp, re.I)
            val = vm.group(1) if vm else ""
            if re.search(r'type=["\']?password', inp, re.I):
                pwfield = name; val = ""
            fields[name] = val
        return {"action": action, "fields": fields, "pwfield": pwfield}
    return None

def _buscar_manutencao(opener, base, timeout):
    """GET na pagina de manutencao; devolve o HTML se estiver logado."""
    try:
        r = opener.open(base + "/general/information.html?kind=item", timeout=timeout)
        html = r.read().decode("utf-8", "replace")
        return html if _login_ok(html) else None
    except Exception:
        return None

def _login_e_busca(ip, senha, timeout=HTTP_TIMEOUT):
    """
    1. Tenta acessar a pagina de manutencao direto (as vezes nem precisa login)
    2. Se nao, abre a pagina de login, LE O FORMULARIO automaticamente
       (action + nome do campo de senha + campos ocultos)
    3. Preenche a senha, faz o POST, refaz o GET da manutencao
    4. Extrai Toner% e Cilindro%
    """
    opener, jar = _novo_opener()
    base = "https://%s" % ip

    # 1. talvez ja esteja acessivel
    html = _buscar_manutencao(opener, base, timeout)
    if html:
        return {"toner": _extrair(html, r"Toner[*\s]*"),
                "tambor": _extrair(html, r"(?:tambor|drum)[*\s]*")}, None

    # 2. acha o formulario de login
    form = None; page_url = None
    for page in ("/home/status.html", "/general/status.html",
                 "/general/information.html?kind=item"):
        try:
            r = opener.open(base + page, timeout=timeout)
            page_url = r.url
            page_html = r.read().decode("utf-8", "replace")
            form = _parse_form(page_html, page_url)
            if form and form["pwfield"]:
                break
        except Exception:
            continue

    if not form or not form["pwfield"]:
        return None, "Formulario de login nao encontrado"

    # 3. preenche e envia
    fields = dict(form["fields"])
    fields[form["pwfield"]] = senha
    data = urllib.parse.urlencode(fields).encode()
    try:
        req = urllib.request.Request(
            form["action"], data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded",
                     "Referer": page_url})
        r2 = opener.open(req, timeout=timeout)
        html2 = r2.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        if e.code == 401:
            return None, "Senha incorreta"
        html2 = ""
    except Exception:
        html2 = ""

    # 4. busca a pagina de manutencao com o cookie obtido
    html = _buscar_manutencao(opener, base, timeout)
    if not html:
        html = html2 if _login_ok(html2) else None
    if not html:
        return None, "Senha incorreta"

    return {"toner": _extrair(html, r"Toner[*\s]*"),
            "tambor": _extrair(html, r"(?:tambor|drum)[*\s]*")}, None


def _corrigir_com_http(ip, toner, tambor, senha):
    precisa_t = toner  is not None and toner["pct"]  is None
    precisa_d = tambor is not None and tambor["pct"] is None
    if not precisa_t and not precisa_d:
        return toner, tambor, None
    if not senha:
        return toner, tambor, "sem_senha"

    dados, erro = _login_e_busca(ip, senha)
    if erro:
        return toner, tambor, erro

    if dados:
        if precisa_t and dados.get("toner") is not None:
            toner  = dict(toner);  toner["pct"]  = dados["toner"];  toner["status"]  = None
        if precisa_d and dados.get("tambor") is not None:
            tambor = dict(tambor); tambor["pct"] = dados["tambor"]; tambor["status"] = None

    return toner, tambor, None


# ── Funcao principal ──────────────────────────────────────────────────────
def consultar_impressora(local, ip, senha="", community=COMMUNITY, timeout=TIMEOUT):
    res = {"local":local,"ip":ip,"online":False,
           "toner":None,"tambor":None,"erro":"","aviso":""}
    try:
        supplies = get_supplies(ip, community, timeout)
        if not supplies:
            res["erro"] = "Sem dados SNMP"; return res
        res["online"] = True
        toner, tambor = _classificar(supplies)
        toner, tambor, http_erro = _corrigir_com_http(ip, toner, tambor, senha)
        res["toner"]  = toner
        res["tambor"] = tambor
        if http_erro == "Senha incorreta":
            res["aviso"] = "Senha incorreta — clique em 🔑 para corrigir"
        elif http_erro == "sem_senha":
            res["aviso"] = "Informe a senha para ver o toner"
        elif http_erro:
            res["aviso"] = "Toner indisponível (%s)" % http_erro
    except socket.timeout:
        res["erro"] = "Sem resposta (SNMP desligado?)"
    except Exception as ex:
        res["erro"] = "Erro: %s" % ex
    return res
