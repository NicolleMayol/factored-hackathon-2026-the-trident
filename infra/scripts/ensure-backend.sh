#!/usr/bin/env bash
# Crea (si no existe) el storage del estado de Terraform. Idempotente. Lo corre el workflow `infra` antes de `terraform init`.
# Requiere `az login` hecho con el SP del pipeline.
set -euo pipefail
RG=rg-tfstate-agent-bank-dev
SA=sttfstateagentbankdev
LOC=eastus2

az group create -n "$RG" -l "$LOC" --tags project=fh26-agente-credito managed_by=ensure-backend -o none
if ! az storage account show -n "$SA" -g "$RG" -o none 2>/dev/null; then
  az storage account create -n "$SA" -g "$RG" -l "$LOC" --sku Standard_LRS --kind StorageV2 \
    --min-tls-version TLS1_2 --allow-blob-public-access false -o none
  az storage account blob-service-properties update -n "$SA" -g "$RG" --enable-versioning true -o none
fi
az storage container create -n tfstate --account-name "$SA" --auth-mode login -o none
echo "backend listo: $RG/$SA/tfstate"
