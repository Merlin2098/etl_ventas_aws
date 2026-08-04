# Arquitectura del proyecto

Registro vivo de la arquitectura desplegada y de cómo fue cambiando. El diagrama
fuente vive en [`architecture.dot`](architecture.dot) (Graphviz); este documento
lo explica y lleva la bitácora de revisiones.

**Regenerar el diagrama tras cualquier cambio estructural** (nuevo módulo,
cambio de mecanismo de trigger, nuevo servicio AWS):

```bash
dot -Tsvg docs/architecture.dot -o docs/architecture.svg
# o -Tpng si se prefiere PNG
```

No commitear el render (`.svg`/`.png`) salvo que se necesite explícitamente
para una presentación — el `.dot` es la fuente de verdad versionable, y
regenerar el render es un comando.

---

## Estado actual (2026-08-04)

### Flujo de datos

```
Generadores Python (manual)
        │  PutObject
        ▼
S3 bronze/<division>/date=<fecha>/
        │  Object Created → EventBridge (bus por defecto)
        ▼
EventBridge rule "ingestion-<division>"  (module.eventbridge)
        │  invoke
        ▼
Lambda ingestion-<division>  (Docker/ECR, module.lambda_ingestion)
        │  parse → normalize_silver
        ├──► S3 silver/store=<division>/date=<fecha>/  (Parquet, delete-then-write)
        └──► S3 quarantine/store=<division>/date=<fecha>/  (filas inválidas)
        │
        │  Object Created → EventBridge (bus por defecto)
        ▼
EventBridge rule "transform-<division>"  (module.eventbridge)
        │  invoke
        ▼
Lambda transform-<division>  (misma imagen que ingestion, distinto CMD)
        │  validate_and_normalize
        ├──► S3 gold/store=<division>/date=<fecha>/  (Parquet, delete-then-write)
        └──► S3 quarantine/store=<division>/date=<fecha>/  (filas inválidas)
        │
        ▼
Glue Crawler (module.glue_catalog) → Glue Data Catalog → Amazon Athena
```

4 divisiones (`electronica`, `supermercado`, `moda`, `marketplace`) × 2 etapas
= 8 funciones Lambda, 8 reglas de EventBridge, 4 repositorios ECR (compartidos
entre ingesta y transformación de cada división).

### Módulos Terraform y su dependencia

```
module.ecr
     │  repository_urls
     ▼
module.lambda_ingestion
     │             │  function_arns/names (ingesta + transform)
     ▼             ▼
module.s3_data_lake ──► module.eventbridge
     │  bucket_arn
     ▼
module.glue_catalog
     │  database_name
     ▼
module.athena
```

- `s3_data_lake` **no depende de `lambda_ingestion`**: solo habilita
  `eventbridge = true` en el bucket, sin conocer ningún ARN de Lambda.
- `eventbridge` depende de `lambda_ingestion` (ARNs/nombres de las 8 funciones,
  para los targets y los `aws_lambda_permission`) y de `s3_data_lake` (nombre
  del bucket, para el `event_pattern` de cada regla).
- Detalle completo de recursos, variables y outputs por módulo: SPEC-004.

### Decisiones de diseño vigentes

- **Trigger vía EventBridge, no notificación S3 directa.** Cada regla tiene su
  propio `aws_lambda_permission` scopeado al ARN de la regla — evita la clase
  de bug de `depends_on`/`merge()` mal cableado que causó INCIDENTE-001 (ver
  sección "Cómo llegamos acá" abajo).
- **Un bucket único con prefijos** (`bronze/`, `silver/`, `gold/`,
  `quarantine/`, `athena-results/`), no buckets separados por capa (Policy
  008 — simplicidad).
- **Una imagen Docker por división, compartida entre ingesta y
  transformación** — la Lambda de transformación no tiene parser propio, solo
  cambia el `CMD` vía `image_config.command`.
- **IAM least-privilege por función**, declarado junto al módulo que posee el
  recurso protegido (Policy 010): permisos de datos en `lambda_ingestion`,
  permiso de invocación EventBridge→Lambda en `eventbridge`.
- **`force_destroy`/`force_delete` en todo recurso con estado que pueda
  bloquear un `destroy`**: bucket de datos, repositorios ECR, workgroup de
  Athena — entorno de demo efímero, sin pasos manuales para destruir.
- **Sin orquestador ni scheduler.** La generación de archivos es manual
  (ejecución de los scripts Python); EventBridge se usa únicamente para
  enrutar eventos `Object Created`, no como scheduler (esa es una capacidad
  distinta, listada como evolución futura en SPEC-001).

---

## Bitácora de cambios estructurales

### 2026-08-04 — Migración del trigger a EventBridge

**Por qué:** INCIDENTE-001 (`docs/INCIDENTE-001_Trigger_S3_Silver_Transform_No_Dispara.md`).
El trigger `silver/store=<division>/` → `transform-<division>` nunca se disparaba
en producción, aunque la configuración de notificación S3 aparecía correcta vía
API y coincidía con el state de Terraform. Causa raíz: en el diseño anterior
(notificación S3 directa), el `depends_on` del `aws_s3_bucket_notification`
apuntaba a nombres de función Lambda en vez de a los recursos
`aws_lambda_permission`, y un `merge()` de dos mapas con las mismas claves de
división colapsaba 8 entradas en 4 — las 4 reglas de `transform-*` quedaban sin
garantía de que su permiso existiera antes de que S3 validara la notificación.

**Qué cambió:**
- `module.s3_data_lake` pasó de un `aws_s3_bucket_notification` con 8 bloques
  `lambda_function` a uno solo con `eventbridge = true`.
- Nuevo `module.eventbridge`: 8 `aws_cloudwatch_event_rule` + 8
  `aws_cloudwatch_event_target` + 8 `aws_lambda_permission` (regla y permiso en
  el mismo módulo — elimina la clase de bug de origen, no solo esta instancia).
  `module.lambda_ingestion` dejó de declarar `aws_lambda_permission`.
- Código: `src/lambda_ingestion/common/s3_event.py` (`extract_s3_location`)
  acepta ambos envelopes de evento (notificación S3 y EventBridge) para permitir
  desplegar el código antes que el cambio de infraestructura.
- Specs actualizadas: SPEC-001, SPEC-003, SPEC-004, SPEC-005, SPEC-006.

**Efecto en este diagrama:** el diagrama de flujo de datos ahora muestra
"EventBridge rule" como intermediario entre cada capa S3 y su Lambda, en vez de
una flecha directa S3 → Lambda.

### 2026-08-04 — Fix de fecha de partición Hive (`718c856`)

`transform_handler_base.py` no inyectaba la fecha de partición Hive antes de
validar filas, causando que el 100% de las filas fueran a cuarentena. No afectó
la topología de infraestructura — sin cambios en este diagrama.

### Anterior — Separación en 8 funciones Lambda (`e78f1c1`)

División de una Lambda por etapa (antes: una función combinaba ingesta y
transformación) en 8 funciones independientes (4 ingesta + 4 transformación),
compartiendo imagen Docker por división. Ver SPEC-004/SPEC-005 para el detalle
del diseño resultante, que es el que refleja el diagrama actual.

---

## Cómo mantener este documento al día

Cuando un cambio toque alguno de estos puntos, actualizar `architecture.dot` y
agregar una entrada a la bitácora:

- Se agrega, quita o renombra un módulo Terraform.
- Cambia el mecanismo de trigger o el flujo de eventos entre etapas.
- Se agrega un servicio AWS nuevo al pipeline.
- Cambia la dependencia entre módulos (quién pasa qué ARN/nombre a quién).
- Se resuelve un incidente que cambió el diseño (como este).

No es necesario actualizar este documento por cambios que no alteran la
topología: ajustes de IAM dentro de un módulo existente, cambios de código de
negocio (parsers, validaciones), tuning de memoria/timeout, etc. — esos quedan
documentados en SPEC-004/SPEC-005 y en el historial de git.
