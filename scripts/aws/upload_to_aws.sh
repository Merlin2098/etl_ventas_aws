#!/usr/bin/env bash
set -euo pipefail

# Genera datos sintéticos de ventas y los sube directo a S3 Bronze, sin tener
# que exportar DATA_BUCKET a mano primero (ver docs/consideraciones/despliegue.md
# "4. Probar el pipeline end-to-end"). El nombre del bucket se resuelve leyendo
# el output real de Terraform (mismo patrón que scripts/docker/docker_push.sh),
# en vez de estar hardcodeado — así el script sigue funcionando aunque cambie
# project_name/environment en terraform.tfvars.
#
# Uso:
#   ./scripts/aws/upload_to_aws.sh                                   # las 4 divisiones; pide fecha/rango por consola
#   ./scripts/aws/upload_to_aws.sh --division electronica --seed 42  # cualquier flag de generate_sales.py funciona
#
# generate_sales.py pide la fecha (o fecha inicio/fin para un rango) de forma
# interactiva por stdin — no se pasa por flag. Todo lo que se pase después del
# nombre de este script se reenvía tal cual a generate_sales.py (--division,
# --seed, --rows, etc.), con --upload siempre agregado — este script solo
# resuelve el bucket, no cambia la lógica de generación.
#
# Requiere que `terraform apply` ya haya corrido con éxito (infra/) y
# credenciales AWS válidas para `s3:PutObject` sobre el bucket de datos. Si
# `terraform apply` no corrió, `terraform output` falla acá mismo con un error
# claro, en vez de subir el archivo a un bucket que no existe.

# Raíz del repo, calculada a partir de la ubicación de este script (no del
# directorio desde donde se lo invoque), para que funcione sin importar el cwd.
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

export DATA_BUCKET
DATA_BUCKET=$(terraform -chdir="${REPO_ROOT}/infra" output -raw data_bucket_name)

echo "DATA_BUCKET=${DATA_BUCKET}"

# --upload dispara la subida real a S3 (por defecto generate_sales.py solo
# escribe en disco local); "$@" reenvía --division/--date/--seed/etc. tal cual
# los haya pasado quien invocó este script.
python "${REPO_ROOT}/scripts/data_generator/generate_sales.py" --upload "$@"
