# SPEC-004 - Infraestructura como Código (Terraform)

## Estado

Borrador v0.1 (Línea Base)

---

# Objetivo

Definir la infraestructura AWS necesaria para soportar el laboratorio, así como la organización del proyecto Terraform, en línea con los guardrails obligatorios de `ai/policies/global.md` (Policy 009 — AWS/Terraform Operational Guardrails, Policy 010 — IAM Cross-Module Placement).

---

# Organización del repositorio

El `infra/` actual es un módulo raíz plano (`main.tf`, `variables.tf`, `outputs.tf`, `providers.tf`) con recursos genéricos ya desplegados (bucket de artifacts, rol de ejecución para jobs de datos, log group, budget mensual). Estos recursos existentes **se mantienen** y no se duplican.

Los recursos nuevos del proyecto se organizan en **módulos por servicio**, invocados desde el módulo raíz:

```
infra/
├── main.tf                  # recursos existentes + invocación de módulos
├── variables.tf              # variables existentes + nuevas variables del proyecto
├── outputs.tf                 # outputs existentes + nuevos outputs
├── providers.tf
├── backend.tf.example
├── terraform.tfvars.example
└── modules/
    ├── s3_data_lake/          # buckets bronze, gold, quarantine
    ├── lambda_ingestion/       # 4 funciones Lambda + sus IAM roles + event notifications
    ├── ecr/                    # 4 repositorios ECR (uno por división)
    ├── glue_catalog/           # Glue Database + Crawler
    └── athena/                 # Athena Workgroup + resultados
```

Cada módulo expone `log_group_name`, `log_group_arn` y el/los `resource_arn` relevantes como outputs (Policy 009).

---

# Módulos Terraform

## `modules/s3_data_lake`

- Bucket(s) para las capas **Bronze**, **Gold** y **Quarantine** (ver SPEC-003 para estructura de particiones).
- Puede ser un único bucket con tres prefijos (`bronze/`, `gold/`, `quarantine/`) o tres buckets separados; se define como variable del módulo (`use_single_bucket: bool`), con **un único bucket con prefijos** como default por simplicidad (Policy 008 — simplicidad).
- `force_destroy = true` en los buckets de datos (bronze/gold/quarantine), consistente con el patrón ya usado en el bucket de artifacts (`artifact_bucket_force_destroy`), dado que es un entorno de demo efímero.
- Bloqueo de acceso público en todos los buckets (Policy 004 — Security By Default), server-side encryption AES256.
- Notificaciones S3 (`aws_s3_bucket_notification`) sobre el bucket de datos, con un bloque `lambda_function` por división, filtrado por `filter_prefix = "bronze/<division>/"` según el layout definido en SPEC-003 (ej. `filter_prefix = "bronze/electronica/"`). Al ser la división el primer segmento del path (no la fecha, que es variable), el prefijo es literal y estático — condición necesaria para que `filter_prefix` funcione (S3 no admite comodines en filtros de notificación).

## `modules/ecr`

- Un repositorio ECR por división (4 repositorios: `electronica`, `supermercado`, `moda`, `marketplace`).
- `image_scanning_configuration` habilitado (escaneo de vulnerabilidades por defecto).
- Terraform gestiona únicamente el repositorio; **no gestiona el build ni el push de la imagen** (ver "Flujo de despliegue").

## `modules/lambda_ingestion`

- 4 funciones Lambda (`aws_lambda_function`), una por división, cada una:
  - `package_type = "Image"`, referenciando el URI de la imagen ya publicada en el repositorio ECR correspondiente.
  - Rol IAM de ejecución dedicado por función (least privilege): permisos de lectura sobre `bronze/`, escritura sobre `gold/` y `quarantine/`, y `logs:CreateLogStream`/`logs:PutLogEvents` sobre su propio log group.
  - Variables de entorno específicas de división (detalle en SPEC-005): nombre de bucket, prefijos de gold/quarantine, nombre de división.
- Siguiendo **Policy 010** (IAM cross-module placement): el permiso `lambda:InvokeFunction` que S3 necesita para invocar cada Lambda (`aws_lambda_permission`, con `source_arn` apuntando al bucket) se declara en `modules/lambda_ingestion` (donde vive la función), no en `modules/s3_data_lake`. El módulo S3 recibe los ARNs de las 4 Lambdas como variables de entrada para configurar `aws_s3_bucket_notification`.
- `aws_cloudwatch_log_group` explícito por función, con `retention_in_days` (Policy 009), en vez de depender del log group implícito de Lambda.

## `modules/glue_catalog`

- Un `aws_glue_catalog_database` para el proyecto.
- Un `aws_glue_crawler` apuntando a `gold/`, programado o de ejecución manual (ver SPEC-006 para el detalle de descubrimiento de esquema).
- Rol IAM del Crawler con permisos de lectura sobre `gold/` y de escritura sobre el Data Catalog.

## `modules/athena`

- Un `aws_athena_workgroup` dedicado al proyecto.
- Ubicación de resultados de consulta: prefijo `athena-results/` dentro del mismo bucket de datos (no un bucket adicional), consistente con el default `use_single_bucket = true` de `modules/s3_data_lake` — un bucket menos que administrar y destruir, sin implicaciones funcionales distintas para esta demo.

---

# Recursos AWS

Resumen de recursos nuevos a introducir (además de los ya existentes en `infra/main.tf`):

- `aws_s3_bucket` (datos: bronze/gold/quarantine, y resultados de Athena)
- `aws_s3_bucket_notification`
- `aws_ecr_repository` × 4
- `aws_lambda_function` × 4
- `aws_lambda_permission` × 4
- `aws_iam_role` + `aws_iam_role_policy` por Lambda (4)
- `aws_cloudwatch_log_group` por Lambda (4)
- `aws_glue_catalog_database`
- `aws_glue_crawler`
- `aws_iam_role` + `aws_iam_role_policy` para el Crawler
- `aws_athena_workgroup`

---

# Variables

Nuevas variables en el módulo raíz (además de las existentes en `variables.tf`):

| Variable | Tipo | Descripción |
|----------|------|-------------|
| `divisions` | `list(string)` | Lista de divisiones (`electronica`, `supermercado`, `moda`, `marketplace`), usada para generar los recursos repetidos vía `for_each`. |
| `data_bucket_force_destroy` | `bool` | Default `true`; permite destruir los buckets de datos con objetos dentro. |
| `lambda_image_tag` | `map(string)` | Tag/digest de la imagen ECR a desplegar por división; se actualiza tras cada build manual (ver "Flujo de despliegue"). |
| `lambda_memory_size` / `lambda_timeout` | `number` | Configuración de recursos de cada función Lambda. |
| `glue_crawler_schedule` | `string` | Expresión cron opcional para el Crawler; vacío = ejecución manual únicamente. |

Se reutilizan `project_name`, `environment`, `owner`, `aws_region`, `tags`, `cost_center` y `log_retention_days` ya definidas en `variables.tf`.

---

# Outputs

Nuevos outputs en el módulo raíz:

- `data_bucket_name` (o `bronze_bucket_name` / `gold_bucket_name` / `quarantine_bucket_name` si se opta por buckets separados)
- `ecr_repository_urls` (map por división)
- `lambda_function_arns` (map por división)
- `lambda_log_group_names` (map por división)
- `glue_database_name`
- `glue_crawler_name`
- `athena_workgroup_name`

---

# Naming Convention

Se reutiliza el patrón ya establecido en `infra/main.tf`:

```
local.name_prefix = "${project_name}-${environment}"
```

Aplicado a los nuevos recursos:

- Buckets: `${name_prefix}-<sufijo>` (ej. `retail-data-lake-dev-<account_id>-datalake`)
- ECR: `${name_prefix}-<division>` (ej. `retail-data-lake-dev-electronica`)
- Lambda: `${name_prefix}-ingestion-<division>`
- IAM roles de Lambda: `${name_prefix}-lambda-<division>-role`
- Log groups de Lambda: `/aws/lambda/${name_prefix}-ingestion-<division>`
- Glue database: `${name_prefix}_catalog` (guion bajo, requisito de Glue)
- Glue crawler: `${name_prefix}-gold-crawler`
- Athena workgroup: `${name_prefix}-workgroup`

Todos los recursos aplican `local.common_tags` (Policy 009).

---

# Dependencias entre recursos

```
modules/ecr
     │  (repository_url por división)
     ▼
modules/lambda_ingestion
     │  (function_arn por división)
     ▼
modules/s3_data_lake
     │  (bucket_arn)
     ▼
modules/glue_catalog
     │  (database_name)
     ▼
modules/athena
```

- `lambda_ingestion` depende de `ecr` (necesita el repositorio para referenciar la imagen).
- `s3_data_lake` depende de `lambda_ingestion` (necesita los ARNs de las 4 funciones para configurar las notificaciones y otorgar `lambda:InvokeFunction`, ver Policy 010).
- `glue_catalog` depende de `s3_data_lake` (el Crawler apunta a la ruta de `gold/`).
- `athena` depende de `glue_catalog` (el Workgroup consulta la base de datos catalogada).

---

# Flujo de despliegue

1. **Build y push de imágenes** (fuera de Terraform, vía script/Makefile): por cada división, `docker build` + `docker push` hacia el repositorio ECR correspondiente. Requiere que el repositorio ECR ya exista.
2. **Primer `terraform apply`**: crea `modules/ecr` (repositorios vacíos).
3. Ejecutar el script de build/push (paso 1) para poblar los repositorios con al menos una imagen.
4. Actualizar `lambda_image_tag` en `terraform.tfvars` con el tag/digest publicado.
5. **Segundo `terraform apply`**: crea `lambda_ingestion`, `s3_data_lake` (con notificaciones ya apuntando a Lambdas existentes), `glue_catalog` y `athena`.
6. Iteraciones posteriores de código de Lambda: repetir pasos 1, 4 y 5 (build/push + actualizar tag + apply) para desplegar la nueva imagen.

Este flujo en dos fases (repositorio antes que función) es necesario porque `aws_lambda_function` con `package_type = "Image"` requiere que la imagen ya exista en ECR al momento de crear el recurso.

---

# Flujo de destrucción

1. `terraform destroy` puede ejecutarse directamente: todos los buckets de datos (bronze/gold/quarantine, resultados de Athena) tienen `force_destroy = true`, por lo que Terraform los vacía y elimina sin pasos manuales previos.
2. Los repositorios ECR requieren `force_delete = true` en `aws_ecr_repository` para eliminarse aunque contengan imágenes (se declara explícitamente en `modules/ecr`, siguiendo el mismo criterio de entorno efímero).
3. No se destruyen los recursos ya existentes en el módulo raíz (bucket de artifacts, rol de ejecución de jobs, budget) salvo que el usuario lo solicite explícitamente; son compartidos con otros posibles usos del proyecto base.

---

# Fuera de alcance

- Gestión del build/push de imágenes Docker dentro de Terraform (se resuelve con script externo, ver SPEC-005 para el contenido del Dockerfile).
- Múltiples entornos (staging/prod); esta demo asume `environment = dev` únicamente.
- Uso de Terraform workspaces o pipelines de CI/CD para aplicar cambios (Policy 001 del framework — fuera del alcance educativo de este webinar).
