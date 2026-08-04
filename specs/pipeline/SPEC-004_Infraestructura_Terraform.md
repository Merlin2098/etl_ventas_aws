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
    ├── s3_data_lake/          # bucket bronze/silver/gold/quarantine + notificaciones a EventBridge
    ├── lambda_ingestion/       # 8 funciones Lambda (4 ingesta + 4 transform) + sus IAM roles
    ├── eventbridge/            # 8 reglas + 8 targets + 8 permisos (ingesta y transformación)
    ├── ecr/                    # 4 repositorios ECR (uno por división, compartido entre ambas Lambdas de esa división)
    ├── glue_catalog/           # Glue Database + Crawler
    └── athena/                 # Athena Workgroup + resultados
```

Cada módulo expone `log_group_name`, `log_group_arn` y el/los `resource_arn` relevantes como outputs (Policy 009).

---

# Módulos Terraform

## `modules/s3_data_lake`

- Bucket(s) para las capas **Bronze**, **Silver**, **Gold** y **Quarantine** (ver SPEC-003 para estructura de particiones).
- Puede ser un único bucket con prefijos (`bronze/`, `silver/`, `gold/`, `quarantine/`) o buckets separados; se define como variable del módulo (`use_single_bucket: bool`), con **un único bucket con prefijos** como default por simplicidad (Policy 008 — simplicidad).
- `force_destroy = true` en los buckets de datos, consistente con el patrón ya usado en el bucket de artifacts (`artifact_bucket_force_destroy`), dado que es un entorno de demo efímero.
- Bloqueo de acceso público en todos los buckets (Policy 004 — Security By Default), server-side encryption AES256.
- Notificaciones a EventBridge habilitadas sobre el bucket de datos (`aws_s3_bucket_notification` con `eventbridge = true`, un único recurso de este tipo por bucket, como exige AWS). No define reglas ni destinos: solo publica los eventos `Object Created` al bus de eventos por defecto. El enrutamiento por división/etapa hacia cada Lambda vive en `modules/eventbridge`.

## `modules/eventbridge`

- 8 `aws_cloudwatch_event_rule` (una por división y por etapa) con `event_pattern` filtrando `source: aws.s3`, `detail-type: Object Created`, el nombre del bucket de datos, y el prefijo de la key:
  - Ingesta: `prefix = "bronze/<division>/"` (ej. `bronze/electronica/`).
  - Transformación: `prefix = "silver/store=<division>/"`.
- 8 `aws_cloudwatch_event_target`, uno por regla, apuntando al ARN de la Lambda de ingesta o transformación correspondiente.
- 8 `aws_lambda_permission` (`principal = "events.amazonaws.com"`, `source_arn` = ARN de la regla propia), uno por regla — ver "Policy 010" más abajo para por qué viven en este módulo y no en `lambda_ingestion`.
- Recibe como variables de entrada los 4 maps de ARN/nombre de Lambda (ingesta y transformación) expuestos por `modules/lambda_ingestion`, y el nombre del bucket expuesto por `modules/s3_data_lake`.

## `modules/ecr`

- Un repositorio ECR por división (4 repositorios: `electronica`, `supermercado`, `moda`, `marketplace`), compartido entre la Lambda de ingesta y la de transformación de esa división (ambas usan la misma imagen, ver `modules/lambda_ingestion`).
- `image_scanning_configuration` habilitado (escaneo de vulnerabilidades por defecto).
- Terraform gestiona únicamente el repositorio; **no gestiona el build ni el push de la imagen** (ver "Flujo de despliegue").

## `modules/lambda_ingestion`

8 funciones Lambda (`aws_lambda_function`) en total, dos por división:

- **Lambda de ingesta** (una por división, 4 en total):
  - `package_type = "Image"`, referenciando el URI de la imagen ya publicada en el repositorio ECR correspondiente.
  - Rol IAM de ejecución dedicado (least privilege): permisos de lectura sobre `bronze/<division>/`, escritura sobre `silver/store=<division>/` y `quarantine/store=<division>/`, y `logs:CreateLogStream`/`logs:PutLogEvents` sobre su propio log group.
  - Variables de entorno específicas de división (detalle en SPEC-005): nombre de bucket, prefijos de silver/quarantine, nombre de división.
- **Lambda de transformación** (una por división, 4 en total):
  - Misma imagen ECR que la Lambda de ingesta de su división, pero con `image_config.command` sobreescribiendo el `CMD` de la imagen para apuntar al handler de transformación (`lambda_ingestion.transform.handler.handler`) — no requiere un build ni repositorio ECR adicional.
  - Rol IAM de ejecución propio (distinto del de ingesta): permisos de lectura sobre `silver/store=<division>/`, escritura sobre `gold/store=<division>/` y `quarantine/store=<division>/`, y `logs:CreateLogStream`/`logs:PutLogEvents` sobre su propio log group.
  - Variables de entorno: nombre de bucket, prefijos de silver/gold/quarantine, nombre de división.
- `modules/lambda_ingestion` expone los ARNs y nombres de las 8 funciones (como cuatro maps: ARN/nombre × ingesta/transformación) para que `modules/eventbridge` los consuma como variables de entrada. Este módulo **no** declara ningún `aws_lambda_permission` — ese permiso vive en `modules/eventbridge` (ver Policy 010 más abajo).
- `aws_cloudwatch_log_group` explícito por función (8 en total), con `retention_in_days` (Policy 009), en vez de depender del log group implícito de Lambda.

**Policy 010 (IAM cross-module placement) aplicada a EventBridge:** el principio de la política no cambia — el permiso se declara en el módulo donde se conoce el ARN determinante — pero bajo EventBridge ese ARN determinante es el de la **regla**, no el de la Lambda, así que el permiso se declara en `modules/eventbridge` en vez de en `modules/lambda_ingestion`. Es la misma regla aplicada a una dependencia que invirtió de dirección respecto al diseño anterior (notificación S3 directa, donde el ARN determinante era el del bucket, conocido por `lambda_ingestion`), no una excepción a Policy 010.

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

- `aws_s3_bucket` (datos: bronze/silver/gold/quarantine, y resultados de Athena)
- `aws_s3_bucket_notification` (una sola, `eventbridge = true`)
- `aws_ecr_repository` × 4
- `aws_lambda_function` × 8 (4 ingesta + 4 transformación)
- `aws_cloudwatch_event_rule` × 8 (4 ingesta + 4 transformación)
- `aws_cloudwatch_event_target` × 8
- `aws_lambda_permission` × 8 (`principal = events.amazonaws.com`, scopeado a la regla correspondiente)
- `aws_iam_role` + `aws_iam_role_policy` por Lambda (8)
- `aws_cloudwatch_log_group` por Lambda (8)
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

- `data_bucket_name` (o `bronze_bucket_name` / `silver_bucket_name` / `gold_bucket_name` / `quarantine_bucket_name` si se opta por buckets separados)
- `ecr_repository_urls` (map por división)
- `lambda_function_arns` (map por división, Lambda de ingesta)
- `transform_lambda_function_arns` (map por división, Lambda de transformación)
- `lambda_log_group_names` (map por división, Lambda de ingesta)
- `transform_lambda_log_group_names` (map por división, Lambda de transformación)
- `eventbridge_rule_names` (map por división, regla de ingesta)
- `eventbridge_transform_rule_names` (map por división, regla de transformación)
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
- Lambda de ingesta: `${name_prefix}-ingestion-<division>`
- Lambda de transformación: `${name_prefix}-transform-<division>`
- IAM roles de Lambda de ingesta: `${name_prefix}-lambda-<division>-role`
- IAM roles de Lambda de transformación: `${name_prefix}-lambda-<division>-transform-role`
- Log groups de Lambda de ingesta: `/aws/lambda/${name_prefix}-ingestion-<division>`
- Log groups de Lambda de transformación: `/aws/lambda/${name_prefix}-transform-<division>`
- Reglas de EventBridge de ingesta: `${name_prefix}-ingestion-<division>`
- Reglas de EventBridge de transformación: `${name_prefix}-transform-<division>`
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
     │  (function_arn/name por división, ingesta y transformación)
     │                                   │
     ▼                                   ▼
modules/s3_data_lake            modules/eventbridge
     │  (bucket_name)                    ▲
     └───────────────────────────────────┘
     │  (bucket_arn)
     ▼
modules/glue_catalog
     │  (database_name)
     ▼
modules/athena
```

- `lambda_ingestion` depende de `ecr` (necesita el repositorio para referenciar la imagen — ambas funciones de una división comparten la misma imagen).
- `eventbridge` depende de `lambda_ingestion` (ARNs y nombres de las 8 funciones, para los targets y los permisos) y de `s3_data_lake` (nombre del bucket, para el `event_pattern` de cada regla).
- `s3_data_lake` **ya no depende de `lambda_ingestion`**: a diferencia del diseño anterior (notificación S3 directa), el módulo del bucket no necesita conocer ningún ARN de Lambda — solo habilita `eventbridge = true`. Esto es lo que permite que `module.eventbridge` reciba `data_bucket_name` desde el output real de `s3_data_lake` (`module.s3_data_lake.bucket_name`) en vez de depender del string `local.data_bucket_name` calculado en el módulo raíz para evitar un ciclo; ese workaround queda acotado a `lambda_ingestion` (sus políticas IAM sí referencian el ARN del bucket directamente).
- `glue_catalog` depende de `s3_data_lake` (el Crawler apunta a la ruta de `gold/`).
- `athena` depende de `glue_catalog` (el Workgroup consulta la base de datos catalogada).

---

# Flujo de despliegue

1. **Build y push de imágenes** (fuera de Terraform, vía script/Makefile): por cada división, `docker build` + `docker push` hacia el repositorio ECR correspondiente. Cada imagen sirve tanto a la Lambda de ingesta como a la de transformación de esa división (ver SPEC-005) — no hay build separado por etapa. Requiere que el repositorio ECR ya exista.
2. **Primer `terraform apply`**: crea `modules/ecr` (repositorios vacíos).
3. Ejecutar el script de build/push (paso 1) para poblar los repositorios con al menos una imagen.
4. Actualizar `lambda_image_tag` en `terraform.tfvars` con el tag/digest publicado.
5. **Segundo `terraform apply`**: crea `lambda_ingestion` (8 funciones), `s3_data_lake` (con `eventbridge = true`), `eventbridge` (8 reglas + 8 targets + 8 permisos, ya apuntando a las 8 Lambdas existentes), `glue_catalog` y `athena`.
6. Iteraciones posteriores de código de Lambda: repetir pasos 1, 4 y 5 (build/push + actualizar tag + apply) para desplegar la nueva imagen a ambas funciones de cada división.

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
