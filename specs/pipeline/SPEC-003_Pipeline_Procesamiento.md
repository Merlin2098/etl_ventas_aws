# SPEC-003 - Pipeline de Procesamiento

## Estado

Borrador v0.1 (Línea Base)

---

# Objetivo

Describir el comportamiento funcional completo del pipeline de datos, desde la generación de archivos hasta su disponibilidad para consulta, incluyendo la organización del Data Lake y el flujo de errores.

---

# Flujo completo de procesamiento

```
Ejecución manual de generadores (Python)
        │
        ▼
 Amazon S3 (Bronze) — partición por fecha
        │
EventBridge (Object Created, wildcard bronze/date=*/<division>/)
        │
        ▼
 Lambda de ingesta (Docker) — una función por división/formato
        │
        ├── Parsea con su parser dedicado y normaliza tipos/fechas (sin sale_id ni total)
        │
        ├── Filas válidas ──────────► Amazon S3 (Silver) — partición por división y fecha
        │
        └── Filas inválidas ───────► Amazon S3 (Quarantine)
                │
                ▼
        EventBridge (Object Created, prefijo silver/store=<division>/)
                │
                ▼
         Lambda de transformación (Docker) — una función por división
                │
                ├── Valida el contrato Gold completo (genera sale_id si falta, recalcula total)
                │
                ├── Filas válidas ──────────► Amazon S3 (Gold) — partición por división y fecha
                │
                └── Filas inválidas ───────► Amazon S3 (Quarantine)
```

Cada división tiene su propia función Lambda de ingesta (4 en total) y su propia función Lambda de transformación (4 en total, 8 en total entre ambas etapas). Las Lambdas de ingesta están empaquetadas en una imagen Docker independiente por división, con el parser de su formato; las de transformación comparten la misma imagen que la Lambda de ingesta de su división (no dependen del formato de origen), diferenciándose solo por el comando de entrada de la función (ver SPEC-004/SPEC-005). No existe una Lambda única con router interno: la selección de parser/etapa queda resuelta por la regla de EventBridge que enruta cada evento a su función (ver "Eventos de S3").

---

# Generación de archivos

- Cada división tiene un generador Python independiente (ver SPEC-002).
- Durante el webinar, la llegada diaria de archivos se simula mediante **ejecución manual** de los generadores: el presentador corre cada script (o los cinco en secuencia) para mostrar el pipeline reaccionando en vivo, archivo por archivo.
- No existe un orquestador automático ni un scheduler en el alcance de esta demo; queda como evolución futura (SPEC-001 - Visión General, sección "Evoluciones futuras": EventBridge Scheduler). EventBridge sí se usa en el pipeline (ver "Eventos de S3"), pero únicamente como enrutador de eventos `Object Created` — no como scheduler; son dos capacidades distintas del mismo servicio.

---

# Carga hacia Amazon S3

- Cada generador, tras crear el archivo localmente, lo sube directamente al bucket/prefijo **Bronze**.
- La subida es un `PutObject` simple por archivo; no hay carga por lotes ni multipart en el alcance de esta demo.

---

# Organización del Data Lake

## Capa Bronze

- Los datos se reciben **tal cual** son generados, sin transformación.
- Partición por **fecha y división** (la fecha primero, en el path):

```
s3://<bucket>/bronze/date=YYYY-MM-DD/<division>/<division>_<YYYY-MM-DD>.<ext>
```

Ejemplo:

```
s3://<bucket>/bronze/date=2026-08-01/electronica/electronica_2026-08-01.csv
s3://<bucket>/bronze/date=2026-08-01/supermercado/supermercado_2026-08-01.xlsx
s3://<bucket>/bronze/date=2026-08-01/moda/moda_2026-08-01.json
s3://<bucket>/bronze/date=2026-08-01/marketplace/marketplace_2026-08-01.pdf
```

La división queda identificada tanto en el segundo segmento del path como en el nombre de
archivo. La fecha va primero en el path (a diferencia de Silver/Gold, que llevan división
primero) para que una carga de un mismo día agrupe las cuatro divisiones bajo una sola
carpeta `date=<fecha>/` — el caso de uso de cargar Bronze arrastrando una carpeta a la
consola web de S3 (ver `docs/consideraciones/carga_web_bronze.md`).

Esto exige que el filtrado de EventBridge por división ya no pueda anclarse al inicio de la
key con `prefix` (el segundo segmento es ahora la fecha, variable). En su lugar se usa el
operador `wildcard` de EventBridge, que sí admite anclar un segmento en medio de la key:
`bronze/date=*/<division>/*` (ver "Eventos de S3" más abajo).

## Capa Silver

- Partición por **división y fecha**, en formato Parquet, mismo estilo de partición Hive que Gold (a diferencia de Bronze, que no usa `store=` por convención heredada del diseño original — ver razonamiento arriba):

```
s3://<bucket>/silver/store=<division>/date=YYYY-MM-DD/part-*.parquet
```

- Producida por la Lambda de ingesta: filas parcialmente normalizadas (tipos y fecha corregidos), sin `sale_id` generado ni `total` recalculado — ver esquema Silver en SPEC-002 y validaciones en SPEC-005.
- Aplica el mismo contrato "último gana" (delete-then-write) que Gold: un reprocesamiento del archivo Bronze de origen sobrescribe la partición Silver correspondiente, evitando que la Lambda de transformación reingiera filas Silver duplicadas.

## Capa Gold

- Partición por **división y fecha**, en formato Parquet:

```
s3://<bucket>/gold/store=<division>/date=YYYY-MM-DD/part-*.parquet
```

Esta estructura es la que registra y descubre el Glue Crawler (ver SPEC-006).

## Capa Quarantine

- Filas inválidas dentro de un archivo procesado se escriben a una zona separada, particionada igual que Gold para mantener trazabilidad de origen y fecha:

```
s3://<bucket>/quarantine/store=<division>/date=YYYY-MM-DD/errors-*.json
```

- Cada registro en cuarentena conserva la fila original más metadata del error (regla de validación incumplida, timestamp de procesamiento). El formato exacto del registro de error se define en SPEC-005.

---

# Eventos de S3 y enrutamiento con EventBridge

- El bucket de datos tiene habilitadas las notificaciones a EventBridge (`aws_s3_bucket_notification` con `eventbridge = true`): cada `PutObject` exitoso se publica como evento `Object Created` (`source: aws.s3`) en el bus de eventos por defecto de la cuenta, sin pasar por una suscripción directa S3 -> Lambda.
- Se configuran 8 **reglas de EventBridge** (`aws_cloudwatch_event_rule`), una por división y por etapa, cada una con su propio `aws_cloudwatch_event_target` apuntando a la Lambda correspondiente:
  - Ingesta: una regla por división, con `event_pattern` filtrando `detail.bucket.name` (el bucket de datos) y `detail.object.key` por `wildcard = "bronze/date=*/<division>/*"` (ej. `bronze/date=*/electronica/*` para la Lambda de ingesta de Electrónica — el operador `wildcard` es necesario porque `prefix` solo ancla al inicio de la key, y la división ya no es el primer segmento), invoca la Lambda de ingesta correspondiente.
  - Transformación: una regla por división, con el mismo patrón filtrando `prefix = "silver/store=<division>/"`, invoca la Lambda de transformación correspondiente.
- Cada regla tiene su propio `aws_lambda_permission` (`principal = "events.amazonaws.com"`, `source_arn` = ARN de la regla), scopeado 1:1 a esa regla — a diferencia de una notificación S3 directa, donde un único recurso `aws_s3_bucket_notification` por bucket forzaba agrupar las 8 suscripciones en un mismo bloque de configuración.
- No se utiliza SQS como buffer intermedio: cada archivo dispara una invocación independiente de la Lambda correspondiente a su etapa (modelo simple, adecuado para el volumen y propósito didáctico de esta demo).
- Detalle de infraestructura (módulo, recursos exactos, IAM) en SPEC-004.

---

# Ejecución automática de Lambda

- Cada Lambda de ingesta se invoca una vez por archivo de su división subido a `bronze/` (filtrado por el patrón de nombre configurado en la notificación S3); recibe el evento S3 y descarga el archivo para procesarlo con su parser dedicado.
- Cada Lambda de transformación se invoca una vez por archivo Parquet escrito en `silver/store=<division>/` por la Lambda de ingesta de esa misma división; recibe el evento S3, descarga el Parquet y valida/normaliza sus filas al esquema Gold completo.

---

# Detección del tipo de archivo

- La selección de la función Lambda correcta ocurre a nivel de infraestructura (`event_pattern` de la regla de EventBridge, filtrando por wildcard `bronze/date=*/<division>/*`), no dentro de la función.
- Dentro de cada Lambda, el formato es conocido de antemano (una función = un formato = un parser), por lo que no existe lógica de detección/enrutamiento en tiempo de ejecución.
- Si un archivo llega a `bronze/` bajo un prefijo de división que no coincide con ninguna regla configurada, ninguna Lambda se invoca; el archivo queda huérfano en Bronze (ver "Flujo de errores").

---

# Conversión hacia formato estándar

Ocurre en dos etapas, cada una en su propia Lambda (ver SPEC-002 esquemas Silver/Gold y SPEC-005 validaciones):

- **Ingesta (Bronze → Silver)**: cada Lambda aplica su parser dedicado (uno por formato/división) para extraer las filas del archivo de origen, y normaliza tipos/fecha (`date` a `YYYY-MM-DD`, cantidad/precio a numérico, currency/status por defecto) sin generar `sale_id` ni calcular `total`. Filas que no completen estos campos se separan hacia cuarentena; el resto continúa hacia Silver.
- **Transformación (Silver → Gold)**: la Lambda de transformación toma las filas Silver ya tipadas y completa el contrato Gold: genera `sale_id` si no vino uno válido, recalcula `total` como `quantity * price`, y reaplica las mismas validaciones de campo (idempotentes sobre datos ya normalizados). Asigna `store` según la división de origen en ambas etapas.

---

# Escritura en las capas Silver y Gold

- Las filas válidas se escriben en formato **Parquet**: Silver en `silver/store=<division>/date=<fecha>/` (Lambda de ingesta), Gold en `gold/store=<division>/date=<fecha>/` (Lambda de transformación) — en ambos casos sin las columnas `store` ni `date` dentro del archivo (quedan codificadas en el path como partición Hive; ver SPEC-002 y SPEC-005).
- Reprocesar el mismo archivo de origen (mismo `bronze/date=.../<division>/<division>_<fecha>.<ext>`) **sobrescribe** el resultado correspondiente tanto en Silver como en Gold para esa partición división+fecha ("último gana"); no se contempla deduplicación ni versionado de escrituras.
- Para cumplir "último gana" de forma efectiva, cada Lambda **borra los objetos existentes** bajo su propia partición (`silver/store=<division>/date=<fecha>/` o `gold/store=<division>/date=<fecha>/`, según corresponda) antes de escribir el nuevo Parquet de la invocación (delete-then-write). Esto es necesario porque el nombre del archivo Parquet incluye el `request_id` de la invocación (ver SPEC-005) y por lo tanto es distinto en cada reprocesamiento; sin el borrado previo, los archivos se acumularían en la misma partición en vez de sobrescribirse, duplicando filas en las consultas de Athena.

---

# Flujo de errores (alto nivel)

| Nivel | Caso | Acción |
|-------|------|--------|
| Fila | Campo faltante, tipo inválido, fecha no parseable, cantidad/precio no numérico o negativo (etapa ingesta o transformación) | La fila se envía a `quarantine/`; el resto del archivo continúa procesándose. Dado que la transformación reaplica las mismas reglas de campo que ya pasó Silver, en la práctica una fila solo cae en cuarentena en la etapa de ingesta — la transformación puede rechazarla igualmente si se reprocesara un Parquet Silver alterado manualmente. |
| Archivo | Nombre de archivo no coincide con ninguna regla de EventBridge configurada, archivo corrupto o ilegible | Si ninguna Lambda se invoca, el archivo queda sin procesar en Bronze/Silver (visible por ausencia de datos en la capa siguiente). Si la Lambda correcta se invoca pero no puede leer el archivo, se registra el error en CloudWatch Logs y el archivo completo no genera salida en la capa siguiente. Tratamiento detallado en SPEC-005. |
| Lambda | Excepción no controlada durante el procesamiento | Se registra en CloudWatch Logs de la función correspondiente (ingesta o transformación); el reintento sigue la política por defecto del target de EventBridge (hasta 185 intentos durante 24 horas, con backoff exponencial), no la de una invocación asíncrona directa desde S3. |

El detalle de implementación de validaciones, logging y manejo de excepciones se profundiza en SPEC-005.

---

# Fuera de alcance

- Orquestación automática o scheduling de la generación diaria de archivos (ver evoluciones futuras en SPEC-001).
- Uso de SQS, colas de mensajería o dead-letter queues.
- Deduplicación o versionado de archivos reprocesados.
- Reintentos avanzados o backoff configurado manualmente más allá del comportamiento por defecto de Lambda.
