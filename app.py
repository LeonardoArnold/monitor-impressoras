# -*- coding: utf-8 -*-
"""
app.py — CAMADA DE LOGICA
=========================
Servidor Flask. Serve o painel e responde a API.
A senha das impressoras e salva junto com cada IP no impressoras.json.
"""

import os, json, re, threading
from concurrent.futures import ThreadPoolExecutor
from flask import Flask, jsonify, request, render_template
import snmp_engine as snmp

app     = Flask(__name__)
BASE    = os.path.dirname(os.path.abspath(__file__))
ARQUIVO = os.path.join(BASE, "impressoras.json")
IP_RE   = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")


def carregar():
    if os.path.exists(ARQUIVO):
        with open(ARQUIVO, encoding="utf-8") as f:
            return json.load(f)
    return []

def salvar(lista):
    with open(ARQUIVO, "w", encoding="utf-8") as f:
        json.dump(lista, f, ensure_ascii=False, indent=2)

def ip_valido(ip):
    return IP_RE.match(ip) and all(0 <= int(p) <= 255 for p in ip.split("."))


@app.route("/")
def index():
    return render_template("index.html")


# ── API impressoras ───────────────────────────────────────────────────────
@app.route("/api/impressoras", methods=["GET"])
def listar():
    # Nao expoe a senha pro frontend
    return jsonify([{"local":p["local"],"ip":p["ip"]} for p in carregar()])

@app.route("/api/impressoras", methods=["POST"])
def adicionar():
    d = request.get_json(force=True)
    local = (d.get("local") or "").strip()
    ip    = (d.get("ip")    or "").strip()
    senha = (d.get("senha") or "").strip()
    if not ip_valido(ip):
        return jsonify({"erro": "IP inválido. Use o formato 192.168.0.10"}), 400
    lista = carregar()
    if any(p["ip"] == ip for p in lista):
        return jsonify({"erro": "Esse IP já está cadastrado"}), 400
    lista.append({"local": local or ip, "ip": ip, "senha": senha})
    salvar(lista)
    return jsonify([{"local":p["local"],"ip":p["ip"]} for p in lista])

@app.route("/api/impressoras/<ip>", methods=["DELETE"])
def remover(ip):
    lista = [p for p in carregar() if p["ip"] != ip]
    salvar(lista)
    return jsonify([{"local":p["local"],"ip":p["ip"]} for p in lista])

@app.route("/api/impressoras/<ip>/senha", methods=["PUT"])
def atualizar_senha(ip):
    d = request.get_json(force=True)
    senha = (d.get("senha") or "").strip()
    lista = carregar()
    for p in lista:
        if p["ip"] == ip:
            p["senha"] = senha
            break
    salvar(lista)
    return jsonify({"ok": True})

@app.route("/api/senha-todas", methods=["PUT"])
def senha_todas():
    d = request.get_json(force=True)
    senha = (d.get("senha") or "").strip()
    lista = carregar()
    for p in lista:
        p["senha"] = senha
    salvar(lista)
    return jsonify({"ok": True, "total": len(lista)})


# ── API status (consulta SNMP + HTTP) ────────────────────────────────────
def _para_json(r):
    t, d = r["toner"], r["tambor"]
    return {
        "local":  r["local"], "ip": r["ip"],
        "online": r["online"], "erro": r["erro"], "aviso": r["aviso"],
        "toner_pct":    t["pct"]    if t else None,
        "toner_status": t["status"] if t else None,
        "tambor_pct":    d["pct"]    if d else None,
        "tambor_status": d["status"] if d else None,
    }

@app.route("/api/status")
def status():
    lista = carregar()
    if not lista:
        return jsonify([])
    def consultar(p):
        return snmp.consultar_impressora(p["local"], p["ip"], p.get("senha",""))
    with ThreadPoolExecutor(max_workers=10) as ex:
        resultados = list(ex.map(consultar, lista))
    return jsonify([_para_json(r) for r in resultados])


# ── Inicia ────────────────────────────────────────────────────────────────
def _abrir_painel():
    import webbrowser
    webbrowser.open("http://localhost:5000")

if __name__ == "__main__":
    threading.Timer(1.5, _abrir_painel).start()
    app.run(host="0.0.0.0", port=5000, debug=False)
