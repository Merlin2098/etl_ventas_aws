#!/usr/bin/env bash
set -euo pipefail

# Corre el Glue Crawler y espera a que termine, para que los datos nuevos
# queden visibles en Athena sin tener que hacer el polling a mano (ver
# docs/consideraciones/glue_crawler.md — el Crawler es el único mecanismo de
# descubrimiento de particiones de este proyecto y no se ejecuta solo).
#
# Este script reemplaza un mini-runbook de 3 pasos manuales:
#   1. aws glue start-crawler --name <nombre>
#   2. sondear aws glue get-crawler ... hasta que State vuelva a READY
#   3. revisar LastCrawl.Status (READY solo significa "ya no está corriendo",
#      NO que la corrida haya sido exitosa — ese chequeo es fácil de olvidar
#      si se hace a mano, y es justo lo que valida este script al final).
#
# Uso:
#   ./scripts/aws/run_glue_crawler.sh
#
# Requiere que `terraform apply` ya haya corrido con éxito (infra/) y
# credenciales AWS con permiso para glue:StartCrawler / glue:GetCrawler.

# Raíz del repo, calculada a partir de la ubicación de este script (no del
# directorio desde donde se lo invoque), para que funcione sin importar el cwd.
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# Nombre real del Crawler leído del output de Terraform, no hardcodeado —
# sigue funcionando aunque cambie project_name/environment en terraform.tfvars.
CRAWLER_NAME=$(terraform -chdir="${REPO_ROOT}/infra" output -raw glue_crawler_name)

echo "Iniciando crawler: ${CRAWLER_NAME}"
aws glue start-crawler --name "${CRAWLER_NAME}"

echo "Esperando a que el crawler termine..."
while true; do
  STATE=$(aws glue get-crawler --name "${CRAWLER_NAME}" --query 'Crawler.State' --output text)
  if [ "${STATE}" = "READY" ]; then
    break
  fi
  echo "  estado=${STATE}, reintentando en 10s..."
  sleep 10
done

# READY únicamente confirma que el crawler dejó de correr — el resultado real
# de la corrida (¿catalogó bien las particiones nuevas o falló a mitad de
# camino?) está en LastCrawl.Status, por eso se valida por separado acá.
STATUS=$(aws glue get-crawler --name "${CRAWLER_NAME}" --query 'Crawler.LastCrawl.Status' --output text)
echo "Crawler terminado con LastCrawl.Status=${STATUS}"

if [ "${STATUS}" != "SUCCEEDED" ]; then
  echo "La corrida del crawler no fue exitosa — revisar CloudWatch Logs (/aws-glue/crawlers/${CRAWLER_NAME})." >&2
  exit 1
fi

echo "Tabla Gold catalogada. Las particiones nuevas ya son consultables en Athena."
