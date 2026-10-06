"""Servidor local sin Azure Functions: python -m agent.devserver → http://localhost:7071
Expone las mismas rutas de contracts/api.yaml (POST /session solo aquí, en Azure lo emite servicio) y una página de chat mínima en /.
Solo para desarrollo; sin dependencias extra (http.server)."""
from __future__ import annotations
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from agent.auth import AuthError, decode_token, issue_test_token, require_scope
from agent.cli import USERS
from agent.config.settings import get_settings
from agent import handle as H

S = get_settings()
PAGE = """<!doctype html><html lang=es><meta charset=utf-8><title>Agente Crédito LATAM · local</title>
<style>body{font-family:system-ui;max-width:860px;margin:24px auto;padding:0 16px;color:#1d2230}
#log{border:1px solid #ccc;border-radius:8px;padding:12px;height:420px;overflow:auto;background:#fafafa}
.u{text-align:right;margin:8px 0}.u span{background:#2f4fb0;color:#fff;padding:8px 12px;border-radius:12px;display:inline-block}
.a{margin:8px 0}.a span{background:#fff;border:1px solid #ddd;padding:8px 12px;border-radius:12px;display:inline-block;max-width:80%}
.meta{font-size:12px;color:#666;margin-left:4px}code{background:#eee;padding:1px 4px;border-radius:4px}
form{display:flex;gap:8px;margin-top:12px}input[type=text]{flex:1;padding:10px}button{padding:10px 14px}select{padding:8px}</style>
<h2>Agente Crédito LATAM · local (mocks)</h2>
<p>Usuario: <select id=u></select> <span class=meta id=scopes></span></p>
<div id=log></div>
<form id=f><input type=text id=m placeholder="Escribe en español o portugués…" autofocus><button>Enviar</button></form>
<div id=confirm style="display:none;margin-top:8px">Pre-evaluación pendiente: <button onclick="conf(true)">Sí, autorizo</button> <button onclick="conf(false)">No</button></div>
<script>
const U=%USERS%;let tok=null,conv=null,pending=null;const sel=document.getElementById('u');
for(const k in U){const o=document.createElement('option');o.value=k;o.textContent=k;sel.appendChild(o)}
async function session(){const r=await fetch('/session',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({user:sel.value})});const j=await r.json();tok=j.token;conv=null;document.getElementById('scopes').textContent=U[sel.value].scopes.join(', ')+' · '+U[sel.value].locale;document.getElementById('log').innerHTML='';}
sel.onchange=session;session();
function add(cls,html){const d=document.createElement('div');d.className=cls;d.innerHTML='<span>'+html+'</span>';document.getElementById('log').appendChild(d);d.scrollIntoView()}
document.getElementById('f').onsubmit=async e=>{e.preventDefault();const m=document.getElementById('m');const text=m.value.trim();if(!text)return;m.value='';add('u',text);
 const r=await fetch('/chat',{method:'POST',headers:{'content-type':'application/json','authorization':'Bearer '+tok},body:JSON.stringify({message:text,conversation_id:conv,locale:U[sel.value].locale})});const j=await r.json();conv=j.conversation_id||conv;
 if(!r.ok){add('a','<b>'+r.status+'</b> '+JSON.stringify(j));return}
 add('a',j.reply+'<div class=meta>action=<code>'+j.action+'</code> · nodos: '+(j.node_path||[]).join(' → ')+' · reglas: '+(j.rules_fired||[]).join(', ')+' · citas: '+j.citations.map(c=>c.type+':'+c.id).join(', ')+(j.case_id?' · case '+j.case_id:'')+' · '+j.latency_ms+' ms · trace '+j.trace_id.slice(0,8)+'</div>');
 pending=j.action_id||null;document.getElementById('confirm').style.display=pending?'block':'none';};
async function conf(ok){const r=await fetch('/chat/confirm',{method:'POST',headers:{'content-type':'application/json','authorization':'Bearer '+tok},body:JSON.stringify({action_id:pending,confirmed:ok})});const j=await r.json();add('a',(j.reply||JSON.stringify(j))+'<div class=meta>/chat/confirm · '+r.status+'</div>');pending=null;document.getElementById('confirm').style.display='none'}
</script></html>"""


class Handler(BaseHTTPRequestHandler):
    def _send(self, status: int, body, ctype="application/json"):
        data = body.encode() if isinstance(body, str) else json.dumps(body, ensure_ascii=False).encode()
        self.send_response(status); self.send_header("content-type", ctype + "; charset=utf-8"); self.send_header("content-length", str(len(data))); self.end_headers(); self.wfile.write(data)

    def _body(self):
        n = int(self.headers.get("content-length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def _auth(self, scope=None):
        claims = decode_token((self.headers.get("authorization") or "").removeprefix("Bearer ").strip(), S.jwt_signing_key)
        if scope:
            require_scope(claims, scope)
        return claims

    def do_GET(self):
        p = urlparse(self.path).path
        if p == "/":
            return self._send(200, PAGE.replace("%USERS%", json.dumps(USERS)), "text/html")
        if p == "/healthz":
            st, h = H.healthz(); return self._send(st, h)
        try:
            if p.startswith("/handoff/"):
                self._auth("handoff:read"); _, d, _ = H.runtime(); doc = d.store.get_handoff(p.split("/")[2])
                return self._send(200, doc) if doc else self._send(404, {"error": "not_found"})
            if p.startswith("/trace/"):
                self._auth("handoff:read"); return self._send(501, {"error": "pendiente"})
        except AuthError as e:
            return self._send(e.status, {"error": e.code})
        self._send(404, {"error": "not_found"})

    def do_POST(self):
        p = urlparse(self.path).path
        try:
            if p == "/session":  # solo local: en Azure lo emite servicio
                u = USERS[self._body().get("user", "cliente_co_ok")]
                return self._send(200, {"token": issue_test_token(u["customer_id"], u["scopes"], S.jwt_signing_key, S.jwt_exp_min, u["locale"])})
            if p == "/chat":
                c = self._auth(); b = self._body()
                out = H.handle(b["message"], {"customer_id": c["customer_id"], "scopes": c["scopes"], "locale": H.pick_locale(b.get("locale"), c.get("locale")), "conversation_id": b.get("conversation_id")})
                st = out.pop("_state"); out["node_path"] = st.get("node_path"); out["rules_fired"] = st.get("rules_fired")
                return self._send(200, out)
            if p == "/chat/confirm":
                c = self._auth(); b = self._body()
                out = H.confirm(b["action_id"], bool(b.get("confirmed")), {"customer_id": c["customer_id"]})
                return self._send(200, out) if out else self._send(404, {"error": "action_not_found"})
        except AuthError as e:
            return self._send(e.status, {"error": e.code})
        self._send(404, {"error": "not_found"})

    def log_message(self, fmt, *args):  # silencioso salvo errores
        if args and str(args[1]).startswith(("4", "5")):
            super().log_message(fmt, *args)


if __name__ == "__main__":
    print("agente local en http://localhost:7071  (Ctrl+C para salir)")
    ThreadingHTTPServer(("127.0.0.1", 7071), Handler).serve_forever()
