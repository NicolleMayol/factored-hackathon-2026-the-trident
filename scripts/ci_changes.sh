#!/usr/bin/env bash
# ADR-27 · Qué capas tocó un cambio. Lo usan main.yml y pr.yml para decidir qué corre.
# Uso: scripts/ci_changes.sh <base> <head>   (escribe key=true|false en $GITHUB_OUTPUT y en stdout)
# Sin base válida (rama nueva, workflow_dispatch) o con cambios en el propio pipeline: todo en true, salvo infra.
set -euo pipefail
base="${1:-}"; head="${2:-HEAD}"
out="${GITHUB_OUTPUT:-/dev/stdout}"

all=false
if [ -z "$base" ] || [ "$base" = "0000000000000000000000000000000000000000" ] || ! git cat-file -e "$base^{commit}" 2>/dev/null; then
  all=true; files=""
else
  files=$(git diff --name-only "$base" "$head")
fi
echo "$files" | grep -qE '^(\.github/workflows/(main|pr)\.yml|scripts/ci_changes\.sh)$' && all=true

has() { $all && return 0; echo "$files" | grep -E "$1" | grep -qvE "${2:-^$}"; }
# Terraform solo corre si cambian los .tf o el script del backend: ni un cambio del pipeline (main.yml,
# infra.yml) ni un run sin base planea infra
# (el apply pide aprobación y no hay nada nuevo que aplicar). Para forzarlo: workflow_dispatch de infra.yml.
only() { echo "$files" | grep -qE "$1"; }
emit() { if has "$2" "${3:-}"; then v=true; else v=false; fi; echo "$1=$v" >> "$out"; [ "$out" = /dev/stdout ] || echo "$1=$v"; }

# ci: todo lo que no sea solo docs, diagramas o Terraform (los prompts y el corpus son .md y los tests los leen).
emit ci        '.'                                                           '^(docs|diagrams|infra)/'
if only '^(infra/.*\.tf|infra/scripts/)'; then v=true; else v=false; fi
echo "infra=$v" >> "$out"; [ "$out" = /dev/stdout ] || echo "infra=$v"
emit function  '^(agent/|policy/|contracts/|deploy/|data/mock/|requirements\.txt$|\.github/workflows/deploy\.yml$)'
emit web       '^(web/|\.github/workflows/deploy-web\.yml$)'
emit bundles   '^(data/|policy/catalog\.yaml$|\.github/workflows/bundles\.yml$)'
emit diagrams  '^(diagrams/|contracts/impact-map\.yaml$|\.github/workflows/diagram-sync\.yml$)' '^diagrams/out/'
# drawio: solo si cambia el dibujo; main exporta y sube los PNG con la App (diagram-export.yml).
# Ni el impact-map ni un cambio del pipeline re-exportan: el render cambia bytes aunque el dibujo sea igual.
if only '^diagrams/.*\.drawio$'; then v=true; else v=false; fi
echo "drawio=$v" >> "$out"; [ "$out" = /dev/stdout ] || echo "drawio=$v"
