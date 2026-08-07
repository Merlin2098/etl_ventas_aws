# Cómo desplegar el proyecto en AWS

Checklist operativo, en orden. Para el **por qué** de cada decisión (por qué
nunca usar `latest`, por qué el segundo `apply`, etc.) ver
[SPEC-004](../../specs/pipeline/SPEC-004_Infraestructura_Terraform.md) y la
sección "5. Desplegar en AWS" del [README](../../README.md). Este documento es
la versión "solo los comandos, en orden" para ejecutar sin releer la narrativa
completa cada vez.

## Requisitos previos

| Herramienta                                                                             | Uso                             |
| --------------------------------------------------------------------------------------- | ------------------------------- |
| AWS CLI, con credenciales configuradas (`aws sts get-caller-identity` debe responder) | Todo el despliegue              |
| Terraform 1.x                                                                           | Infraestructura                 |
| Docker                                                                                  | Build de las 4 imágenes Lambda |
| Python 3.12+ con`requirements.txt`/`requirements-dev.txt` instalados                | Generar datos y correr tests    |

## 0. Configurar variables

```bash
cd infra
cp terraform.tfvars.example terraform.tfvars
```

Editar `terraform.tfvars` — como mínimo revisar:

| Variable               | Default              | Cuándo cambiarla                                                                                                                     |
| ---------------------- | -------------------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| `project_name`       | `data-platform`    | Si convive con otro proyecto en la misma cuenta                                                                                       |
| `environment`        | `dev`              | Esta demo asume un único entorno; no cambiar sin adaptar el resto                                                                    |
| `aws_region`         | `us-east-1`        | Según la región donde se quiera desplegar                                                                                           |
| `owner`              | `data-engineering` | Tag informativo                                                                                                                       |
| `budget_alert_email` | vacío               | Si se quiere alerta de presupuesto por correo (ver "Ask before" en[AGENTS.md](../../AGENTS.md) — cambiar esto requiere confirmación) |

`divisions`, `data_bucket_force_destroy`, `lambda_memory_size`,
`lambda_timeout` y `glue_crawler_schedule` tienen defaults razonables para la
demo (ver [SPEC-004 &#34;Variables&#34;](../../specs/pipeline/SPEC-004_Infraestructura_Terraform.md#variables)) — no hace falta tocarlos para el primer despliegue.

```bash
terraform init
```

## 1. Primer `terraform apply` — toda la infraestructura

```bash
terraform apply
```

`lambda_image_tag` tiene como default `"placeholder"` para las 4 divisiones
(`infra/variables.tf`), un tag que todavía no existe en ningún repositorio
ECR. Esto **no bloquea la creación** de las 8 funciones Lambda: AWS valida el
formato del `image_uri` al crear el recurso, pero no que la imagen exista
hasta que la función se invoca por primera vez. Terraform crea todo — ECR,
las 8 Lambdas (apuntando al tag placeholder), S3, EventBridge, Glue, Athena —
en un solo `apply`.

Esto crea, en este orden de dependencias (ver
[SPEC-004 &#34;Dependencias entre recursos&#34;](../../specs/pipeline/SPEC-004_Infraestructura_Terraform.md#dependencias-entre-recursos)):

1. `ecr` — 4 repositorios vacíos (uno por división).
2. `lambda_ingestion` — 8 funciones (4 ingesta + 4 transformación), sus IAM roles y log groups, con `image_uri` apuntando al tag placeholder.
3. `s3_data_lake` — bucket único con prefijos `bronze/`, `silver/`, `gold/`, `quarantine/`, `athena-results/`, con notificaciones a EventBridge habilitadas.
4. `eventbridge` — 8 reglas + 8 targets + 8 permisos, enrutando cada evento `Object Created` a la Lambda correcta (ingesta: wildcard sobre `bronze/date=*/<division>/*`; transformación: prefix sobre `silver/store=<division>/`).
5. `glue_catalog` — database + crawler (no corre automáticamente, ver paso 4).
6. `athena` — workgroup dedicado.

Verificación rápida tras el apply:

```bash
terraform output data_bucket_name
terraform output ecr_repository_urls
terraform output lambda_function_arns
terraform output glue_crawler_name
terraform output athena_workgroup_name
```

Las 8 Lambdas ya existen en este punto, pero **no funcionan todavía** — su
imagen (`<tag>=placeholder`) no existe en ECR. Invocarlas ahora fallaría.

## 2. Build y push de las 4 imágenes Docker

Desde la raíz del repo (no desde `infra/`):

```bash
cd ..
./scripts/docker/docker_build.sh    # build local, sin credenciales AWS, ~1 imagen por división
./scripts/docker/docker_push.sh     # login a ECR + push de las 4 imágenes
```

Ambos scripts etiquetan con el SHA corto del commit actual
(`git rev-parse --short HEAD`). `docker_push.sh` termina imprimiendo el bloque
exacto para pegar en `terraform.tfvars`:

```hcl
lambda_image_tag = {
  electronica = "<sha>", supermercado = "<sha>",
  moda = "<sha>", marketplace = "<sha>"
}
```

> **Nunca usar el tag `latest`.** Terraform compara el tag declarado contra el
> desplegado; con `latest` nunca detecta el cambio y la Lambda se queda con
> código viejo sin ningún error visible.

Pegar ese bloque en `infra/terraform.tfvars`, reemplazando el que trae el
`terraform.tfvars.example` (si lo copiaste sin editar, ahora mismo no tiene
`lambda_image_tag` explícito y está usando el default `"placeholder"`).

## 3. Segundo `terraform apply` — apuntar las Lambdas a la imagen real

```bash
cd infra
terraform apply
```

Con `lambda_image_tag` ya actualizado, Terraform detecta el cambio de
`image_uri` en las 8 funciones y las actualiza in-place (mismo plan que
"Iterar sobre código de Lambda ya desplegado" más abajo). Después de este
segundo apply el pipeline queda funcional de punta a punta.

## 4. Probar el pipeline end-to-end

### 4a. Generar los datos localmente, por fecha

```bash
python scripts/data_generator/generate_sales.py
```

El script pide la fecha por consola:

```
Fecha inicio (YYYY-MM-DD): 2026-08-04
Fecha fin (YYYY-MM-DD, Enter para un solo día):
```

Dejar la fecha fin en blanco genera un solo día; completarla genera todos los
días del rango indicado (reemplaza al viejo `--week` de 7 días fijos — ahora
el rango es de cualquier longitud). Sin `--upload`, este comando solo escribe
en disco — nada toca S3 todavía. Los archivos quedan en
`data/date=2026-08-04/<division>/...`, mismo layout que usa Bronze
(`bronze/date=<fecha>/<division>/...`), para las dos formas de subida del
siguiente paso.

### 4b. Subir a Bronze

Dos formas, elegir una:

**CLI**, en un solo paso con la generación (`--upload` reemplaza a 4a; la
fecha se sigue pidiendo por consola):

```bash
export DATA_BUCKET=$(terraform -chdir=infra output -raw data_bucket_name)
python scripts/data_generator/generate_sales.py --upload
```

O con `scripts/aws/upload_to_aws.sh`, que resuelve `DATA_BUCKET` desde el
output de Terraform automáticamente (sin el `export` manual) y reenvía
cualquier argumento a `generate_sales.py`:

```bash
./scripts/aws/upload_to_aws.sh
./scripts/aws/upload_to_aws.sh --division electronica --seed 42   # una división, reproducible
```

**Consola web de S3**, sobre los archivos ya generados en 4a: arrastrar
`data/date=<fecha>/` (un día completo, las 4 divisiones de una vez) dentro
del prefijo `bronze/` del bucket de datos. El layout local ya coincide con la
key de Bronze. Ver [carga_web_bronze.md](carga_web_bronze.md) — sin chequeo
de duplicados, a diferencia del CLI que simplemente sobrescribe la misma
partición.

A partir de acá el pipeline corre solo (event-driven): EventBridge dispara las
4 Lambdas de ingesta → Silver → dispara las 4 de transformación → Gold. Sin
intervención manual. Para observarlo:

```bash
aws s3 ls s3://$DATA_BUCKET/silver/ --recursive
aws s3 ls s3://$DATA_BUCKET/gold/   --recursive
aws logs tail /aws/lambda/data-platform-dev-ingestion-electronica --follow
```

## 5. Correr el Glue Crawler — paso manual, fácil de olvidar

```bash
aws glue start-crawler --name $(terraform -chdir=infra output -raw glue_crawler_name)
aws glue get-crawler --name $(terraform -chdir=infra output -raw glue_crawler_name) --query 'Crawler.State' --output text
```

O con `scripts/aws/run_glue_crawler.sh`, que resuelve el nombre del Crawler
desde Terraform, dispara la corrida y hace polling hasta `READY`, fallando
con exit code distinto de cero si `LastCrawl.Status` no es `SUCCEEDED`:

```bash
./scripts/aws/run_glue_crawler.sh
```

El descubrimiento de particiones **no es automático** en este proyecto — sin
este paso, Athena no ve datos nuevos aunque ya estén en `gold/` (no da error,
devuelve resultados vacíos o desactualizados). Detalle completo en
[docs/consideraciones/glue_crawler.md](glue_crawler.md).

## 6. Consultar en Athena

Queries listas para pegar, incluyendo por qué `date` se filtra como string y
no como `DATE`, en
[docs/consideraciones/athena_queries.md](athena_queries.md).

## 7. Validar el despliegue completo

```bash
python scripts/testing/run_cloud_tests.py    # smoke tests + E2E contra AWS real
```

Criterios de aceptación completos en
[SPEC-006](../../specs/pipeline/SPEC-006_Analitica_Validacion_E2E.md).

## Iterar sobre código de Lambda ya desplegado

Repetir, en orden:

1. `./scripts/docker/docker_build.sh && ./scripts/docker/docker_push.sh`
2. Actualizar `lambda_image_tag` en `terraform.tfvars` con el nuevo tag impreso.
3. `terraform apply` (desde `infra/`) — actualiza las 8 funciones in-place.

## Destruir todo

```bash
cd infra
terraform destroy
```

Funciona sin pasos manuales previos: los buckets de datos tienen
`force_destroy = true` y los repositorios ECR `force_delete = true`, así que
Terraform los vacía y elimina en la misma corrida. No destruye los recursos
preexistentes del módulo raíz (bucket de artifacts, rol de ejecución de jobs,
budget) salvo que se pida explícitamente.

## Problemas conocidos al desplegar

- **El Crawler falla con `AccessDeniedException`**: falta el permiso
  `glue:BatchGetPartition` en su rol IAM (no queda cubierto implícitamente por
  `glue:GetPartitions`/`BatchCreatePartition`/`BatchUpdatePartition`). Ya
  corregido en `modules/glue_catalog`, mencionado acá como referencia si se
  modifica ese módulo.
- **Un CTAS en Athena falla con `InvalidRequestException`**: el workgroup
  fuerza `enforce_workgroup_configuration = true`; una query con
  `external_location` propia no está permitida — omitir esa cláusula.
- **Silver se escribe pero Gold nunca aparece**: si se llegara a revertir el
  trigger de EventBridge por una notificación S3 directa, ver el postmortem
  completo en
  [INCIDENTE-001](../indicentes/INCIDENTE-001_Trigger_S3_Silver_Transform_No_Dispara.md)
  antes de reintentar ese diseño — la causa raíz fue un `depends_on` mal
  cableado en Terraform, no una limitación de la plataforma.
