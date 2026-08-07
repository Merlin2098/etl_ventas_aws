# Carga a Bronze vía consola web de S3

> **Estado: decidido y aplicado.** Reemplaza la propuesta anterior de landing
> page con API Gateway + Lambda + presigned URL (ver "Propuesta descartada"
> más abajo, conservada como referencia histórica).

## Motivación

La carga de archivos de ventas a Bronze es 100% manual por CLI
(`python scripts/data_generator/generate_sales.py --upload` o
`scripts/aws/upload_to_aws.sh`). Para responder "¿cómo cargaría esto un
usuario final sin terminal?" sin construir infraestructura nueva, se optó por
la consola web de S3 (drag-and-drop) en vez de una landing page propia.

## Mecanismo

1. Generar los archivos localmente, sin subir (el script pide la fecha por
   consola):
   ```bash
   python scripts/data_generator/generate_sales.py --no-upload
   ```
   ```
   Fecha inicio (YYYY-MM-DD): 2026-08-04
   Fecha fin (YYYY-MM-DD, Enter para un solo día):
   ```
2. Los archivos quedan en `data/date=<fecha>/<division>/<division>_<fecha>.<ext>`
   — mismo layout, en el mismo orden (fecha → división), que la key que usa
   Bronze en S3 (`bronze/date=<fecha>/<division>/...`, ver
   [`src/generators/engine/uploader.py`](../../src/generators/engine/uploader.py)).
   Esto es a propósito: permite arrastrar la carpeta local tal cual, y agrupa
   las 4 divisiones de un mismo día bajo una sola carpeta `date=<fecha>/`.
3. En la consola de AWS, navegar al bucket de datos (`terraform output
   data_bucket_name`) y al prefijo `bronze/`.
4. Arrastrar `data/date=<fecha>/` (un día completo, las 4 divisiones de una
   vez) —o una subcarpeta `data/date=<fecha>/<division>/` puntual— dentro de
   `bronze/`. La consola de S3 preserva la estructura de subcarpetas al
   soltar una carpeta, así que `data/date=.../electronica/...` se sube como
   `bronze/date=.../electronica/...`.
5. Desde acá el pipeline existente (EventBridge → Lambdas de
   ingesta/transform → Glue/Athena) no cambia — la consola es solo una puerta
   de entrada alternativa al mismo layout `bronze/date=<fecha>/<division>/`
   que ya enruta EventBridge.

## Por qué el layout local se hizo coincidir con el de S3

El enrutamiento de EventBridge hacia cada Lambda de ingesta depende de que la
división sea identificable en la key (ver
[SPEC-003](../../specs/pipeline/SPEC-003_Pipeline_Procesamiento.md) y
[`infra/modules/eventbridge/main.tf`](../../infra/modules/eventbridge/main.tf)).
Bronze particiona **por fecha primero, división después**
(`bronze/date=<fecha>/<division>/...`), justamente para que una carga por
fecha agrupe las 4 divisiones en una sola carpeta al arrastrar — y como la
división ya no es el primer segmento de la key, el filtro de EventBridge usa
el operador `wildcard` (`bronze/date=*/<division>/*`) en vez de `prefix`, que
solo puede anclarse al inicio de la key. El generador local
(`generate_division()` en
[`scripts/data_generator/generate_sales.py`](../../scripts/data_generator/generate_sales.py))
escribe con el mismo orden (`data/date=<fecha>/<division>/...`), calcado del
layout de S3 — si alguna vez quedaran desalineados, arrastrar la carpeta
local produciría una key que ninguna regla de EventBridge matchea, dejando el
archivo huérfano en Bronze sin ningún error visible.

## Limitaciones aceptadas

- **Sin chequeo de duplicados.** La consola de S3 sobrescribe sin preguntar
  si ya existe un objeto en esa key — a diferencia del diseño descartado de
  Lambda (que sí iba a rechazar con 409 si ya existía dataset para esa
  división+fecha). El CLI existente tiene el mismo comportamiento
  ("reprocesar el mismo archivo sobrescribe Silver y Gold para esa partición
  — último gana", SPEC-003), así que esto no es una regresión respecto al
  mecanismo ya vigente, solo la ausencia de una protección que la propuesta
  de landing page iba a agregar.
- **Requiere credenciales de consola AWS**, no solo credenciales
  programáticas de `s3:PutObject`. Si quien va a subir datos no tiene acceso
  a la consola (SSO o usuario IAM con login de consola habilitado), este
  mecanismo no aplica y hay que volver al CLI.
- **Sigue sin ser "un usuario final sin conocimiento de AWS"** — la consola
  de S3 asume comodidad navegando buckets y prefijos. Para ese caso de uso
  real, la propuesta de landing page (abajo) seguiría siendo la solución
  correcta si se retoma en el futuro.

## Propuesta descartada: landing page + API Gateway + Lambda

Se había diseñado (sin implementar) una landing page con formulario de
subida, respaldada por una Lambda `upload-gateway` que verificaba
`s3:ListBucket` con prefijo antes de emitir una `generate_presigned_post`, de
forma que la sobreescritura de división+fecha existente fuera rechazada con
409 (sobreescritura manual vía CLI, nunca automática desde la web). El diseño
completo — piezas de backend/frontend, alternativas de hosting (S3 website vs
CloudFront+OAC), trade-offs — no se repite acá para no duplicar contenido;
quedó superado por la decisión de usar la consola de S3 en su lugar, motivada
por mantener acotado el alcance de la demo (ver
[SPEC-001](../../specs/SPEC-001_Vision_General.md), sección "Evoluciones
futuras"). Si en el futuro se necesita servir carga a usuarios sin acceso a
la consola AWS, ese diseño (presigned URL con verificación previa) sigue
siendo el patrón correcto a retomar — no la consola web.
