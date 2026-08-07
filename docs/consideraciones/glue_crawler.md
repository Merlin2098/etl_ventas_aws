# Consideraciones sobre el Glue Crawler

El Glue Crawler (`data-platform-dev-gold-crawler`, `modules/glue_catalog`) es
el único mecanismo de descubrimiento de particiones de este proyecto. Se
ejecuta de forma manual — `glue_crawler_schedule` está vacío a propósito, sin
scheduler (ver `SPEC-004_Infraestructura_Terraform.md` y
`SPEC-006_Analitica_Validacion_E2E.md`).

## Cómo correrlo

```bash
aws glue start-crawler --name data-platform-dev-gold-crawler

# Sondear hasta que vuelva a READY
aws glue get-crawler --name data-platform-dev-gold-crawler --query 'Crawler.State' --output text

# Confirmar que la última corrida terminó bien (Status: SUCCEEDED, no FAILED)
aws glue get-crawler --name data-platform-dev-gold-crawler --query 'Crawler.LastCrawl' --output json
```

O con `scripts/aws/run_glue_crawler.sh`, que resuelve el nombre del crawler
desde el output de Terraform, dispara la corrida, hace el polling hasta
`READY` y valida `LastCrawl.Status` en un solo comando:

```bash
./scripts/aws/run_glue_crawler.sh
```

Por consola: Glue → Crawlers → `data-platform-dev-gold-crawler` → **Run**.

No se usa `MSCK REPAIR TABLE` ni `ALTER TABLE ADD PARTITION` manual en este
proyecto: toda actualización de particiones pasa por el Crawler, para mantener
un único mecanismo de descubrimiento (SPEC-006).

## El Crawler es manual: cargar a S3 no basta para que Athena vea los datos

Subir un archivo directo a `bronze/date=<fecha>/<división>/` (por CLI, consola
S3, o cualquier método fuera del generador Python) **sí** dispara el pipeline
completo de forma automática — EventBridge invoca la Lambda de ingesta, luego
la de transformación, hasta escribir en `gold/`. Esa parte no requiere ningún
paso manual (SPEC-003/SPEC-004).

Lo que **no** es automático es que esos datos aparezcan en Athena. Consultar
`gold` sin haber corrido el Crawler después de la carga devuelve resultados
**desactualizados** o vacíos para la partición nueva, no un error — es fácil
confundirlo con un fallo del pipeline cuando en realidad el dato ya está en
S3, solo no catalogado todavía.

**Requisito previo antes de consultar datos recién cargados:** el Crawler debe
haber corrido con éxito (`State: READY` y `LastCrawl.Status: SUCCEEDED`)
después de que las Lambdas de transformación escribieron en `gold/` — de lo
contrario la tabla no existe o le faltan particiones recientes.

**Para una demo en vivo:** anunciar este paso explícitamente como parte del
guion ("ahora le decimos a Glue que vaya a mirar qué hay nuevo") evita que la
audiencia interprete la espera como que el pipeline no funcionó.

## Permiso IAM requerido: `glue:BatchGetPartition`

El rol IAM del Crawler debe incluir `glue:BatchGetPartition` (además de
`glue:GetPartitions`, `glue:BatchCreatePartition`, `glue:BatchUpdatePartition`,
ver `SPEC-004_Infraestructura_Terraform.md` → `modules/glue_catalog`). El
Crawler la invoca para reconciliar particiones ya catalogadas contra las
nuevas que descubre en cada corrida — no queda cubierta implícitamente por las
otras acciones de partición.

Sin este permiso, `start-crawler` termina en `Status: FAILED` con
`AccessDeniedException`, y ninguna tabla queda disponible para Athena.
Detectado por primera vez en la validación E2E del 2026-08-04 y corregido en
`infra/modules/glue_catalog/main.tf`.

## Nombre real de la tabla

Sin `table_prefix` configurado en `aws_glue_crawler`, el Crawler deriva el
nombre de la tabla del último segmento del path S3: `gold/` → tabla **`gold`**
(no `sales`, que era solo un nombre ilustrativo en versiones previas de la
spec). Confirmado contra el despliegue real.

## Ver también

- `docs/consideraciones/athena_queries.md` — queries de ejemplo para correr una vez que el Crawler ya catalogó los datos.
- `specs/pipeline/SPEC-006_Analitica_Validacion_E2E.md` — especificación completa de Glue/Athena y criterios de validación E2E.
- `specs/pipeline/SPEC-004_Infraestructura_Terraform.md` — definición del módulo `glue_catalog`.
