// ADR-28 F15 · carga contra /api/chat con los mensajes del eval (eval/cases.jsonl), cada uno con su usuario de prueba.
// Umbrales de contracts/ops.yaml (alerts.p95_ms, alerts.error_rate); el workflow carga.yml los pasa por entorno.
//   k6 run -e API=https://<function>.azurewebsites.net -e VUS=10 -e DURACION=1m scripts/carga/chat.js
import http from "k6/http";
import { check, sleep } from "k6";

const API = __ENV.API;
const CASOS = open("../../eval/cases.jsonl").split("\n").filter((l) => l.trim()).map((l) => JSON.parse(l));
const JSON_H = { "content-type": "application/json" };

export const options = {
  scenarios: { chat: { executor: "constant-vus", vus: Number(__ENV.VUS || 10), duration: __ENV.DURACION || "1m" } },
  thresholds: {
    "http_req_duration{ruta:chat}": [`p(95)<${__ENV.P95_MS || 8000}`],
    "http_req_failed{ruta:chat}": [`rate<${__ENV.ERROR_RATE || 0.02}`],
    checks: ["rate>0.98"],
  },
  summaryTrendStats: ["avg", "p(50)", "p(90)", "p(95)", "max"],
};

// Un token por usuario de los casos; /session solo emite usuarios que existen (los mismos de /meta).
export function setup() {
  if (!API) throw new Error("falta -e API=https://...");
  const tokens = {};
  for (const u of [...new Set(CASOS.map((c) => c.user))]) {
    const r = http.post(`${API}/api/session`, JSON.stringify({ user: u }), { headers: JSON_H, tags: { ruta: "session" } });
    if (r.status === 200) tokens[u] = r.json("token");
  }
  if (!Object.keys(tokens).length) throw new Error("/session no emitió ningún token");
  return { tokens };
}

export default function (data) {
  const casos = CASOS.filter((c) => data.tokens[c.user]);
  const c = casos[(__VU * 7 + __ITER) % casos.length];
  const r = http.post(`${API}/api/chat`, JSON.stringify({ message: c.message, locale: c.language }), {
    headers: { ...JSON_H, authorization: `Bearer ${data.tokens[c.user]}` },
    tags: { ruta: "chat", accion_esperada: c.expected_action },
    timeout: "60s",
  });
  check(r, {
    "200": (x) => x.status === 200,
    "trae action y trace_id": (x) => x.status === 200 && !!x.json("action") && !!x.json("trace_id"),
  });
  sleep(1 + Math.random()); // una persona lee la respuesta antes de escribir otra vez
}
