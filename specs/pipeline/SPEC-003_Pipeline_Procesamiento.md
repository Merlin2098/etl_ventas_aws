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
S3 Event Notification (ObjectCreated, prefijo bronze/<division>/)
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
        S3 Event Notification (ObjectCreated, prefijo silver/store=<division>/)
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

Cada división tiene su propia función Lambda de ingesta (4 en total) y su propia función Lambda de transformación (4 en total, 8 en total entre ambas etapas). Las Lambdas de ingesta están empaquetadas en una imagen Docker independiente por división, con el parser de su formato; las de transformación comparten la misma imagen que la Lambda de ingesta de su división (no dependen del formato de origen), diferenciándose solo por el comando de entrada de la función (ver SPEC-004/SPEC-005). No existe una Lambda única con router interno: la selección de parser/etapa queda resuelta por la propia suscripción del evento S3 a cada función (ver "Eventos de S3").

---

# Generación de archivos

- Cada división tiene un generador Python independiente (ver SPEC-002).
- Durante el webinar, la llegada diaria de archivos se simula mediante **ejecución manual** de los generadores: el presentador corre cada script (o los cinco en secuencia) para mostrar el pipeline reaccionando en vivo, archivo por archivo.
- No existe un orquestador automático ni un scheduler en el alcance de esta demo; queda como evolución futura (SPEC-001 - Visión General, sección "Evoluciones futuras": EventBridge Scheduler).

---

# Carga hacia Amazon S3

- Cada generador, tras crear el archivo localmente, lo sube directamente al bucket/prefijo **Bronze**.
- La subida es un `PutObject` simple por archivo; no hay carga por lotes ni multipart en el alcance de esta demo.

---

# Organización del Data Lake

## Capa Bronze

- Los datos se reciben **tal cual** son generados, sin transformación.
- Partición por **división y fecha** (la división primero, en el path):

```
s3://<bucket>/bronze/<division>/date=YYYY-MM-DD/<division>_<YYYY-MM-DD>.<ext>
```

Ejemplo:

```
s3://<bucket>/bronze/electronica/date=2026-08-01/electronica_2026-08-01.csv
s3://<bucket>/bronze/supermercado/date=2026-08-01/supermercado_2026-08-01.xlsx
s3://<bucket>/bronze/moda/date=2026-08-01/moda_2026-08-01.json
s3://<bucket>/bronze/marketplace/date=2026-08-01/marketplace_2026-08-01.pdf
```

La división queda identificada tanto en el prefijo del path como en el nombre de archivo.
El prefijo (`bronze/<division>/`) es lo que permite filtrar la S3 Event Notification por
división (ver "Eventos de S3"): al ser un prefijo **literal** y estático, `filter_prefix`
puede aislarlo sin depender de la fecha, que es variable. Con un layout `bronze/date=.../`
(fecha primero) esto no sería posible, porque la fecha cambia en cada ejecución y ningún
prefijo fijo podría aislar la división.

## Capa Silver

- Partición por **división y fecha**, en formato Parquet, mismo estilo de partición Hive que Gold (a diferencia de Bronze, que no usa `store=` — ver razonamiento arriba):

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

# Eventos de S3

- Se configura una única **S3 Event Notification** (`s3:ObjectCreated:*`) sobre el bucket de datos (AWS solo permite un recurso de este tipo por bucket), con dos conjuntos de bloques `lambda_function`, uno por etapa:
  - Ingesta: un bloque por división, filtrado por `filter_prefix = "bronze/<division>/"` (ej. `filter_prefix = "bronze/electronica/"` para la Lambda de ingesta de Electrónica), invoca la Lambda de ingesta correspondiente.
  - Transformación: un bloque por división, filtrado por `filter_prefix = "silver/store=<division>/"`, invoca la Lambda de transformación correspondiente.
- Al ser prefijos literales y estáticos (sin depender de la fecha, que es variable en cada archivo), `filter_prefix` aísla la división y la etapa de forma inequívoca — ver "Organización del Data Lake" para el razonamiento completo.
- No se utiliza SQS como buffer intermedio: cada archivo dispara una invocación independiente de la Lambda correspondiente a su etapa (modelo simple, adecuado para el volumen y propósito didáctico de esta demo).

---

# Ejecución automática de Lambda

- Cada Lambda de ingesta se invoca una vez por archivo de su división subido a `bronze/` (filtrado por el patrón de nombre configurado en la notificación S3); recibe el evento S3 y descarga el archivo para procesarlo con su parser dedicado.
- Cada Lambda de transformación se invoca una vez por archivo Parquet escrito en `silver/store=<division>/` por la Lambda de ingesta de esa misma división; recibe el evento S3, descarga el Parquet y valida/normaliza sus filas al esquema Gold completo.

---

# Detección del tipo de archivo

- La selección de la función Lambda correcta ocurre a nivel de infraestructura (filtro de la S3 Event Notification por prefijo `bronze/<division>/`), no dentro de la función.
- Dentro de cada Lambda, el formato es conocido de antemano (una función = un formato = un parser), por lo que no existe lógica de detección/enrutamiento en tiempo de ejecución.
- Si un archivo llega a `bronze/` bajo un prefijo de división que no coincide con ninguna notificación configurada, ninguna Lambda se invoca; el archivo queda huérfano en Bronze (ver "Flujo de errores").

---

# Conversión hacia formato estándar

Ocurre en dos etapas, cada una en su propia Lambda (ver SPEC-002 esquemas Silver/Gold y SPEC-005 validaciones):

- **Ingesta (Bronze → Silver)**: cada Lambda aplica su parser dedicado (uno por formato/división) para extraer las filas del archivo de origen, y normaliza tipos/fecha (`date` a `YYYY-MM-DD`, cantidad/precio a numérico, currency/status por defecto) sin generar `sale_id` ni calcular `total`. Filas que no completen estos campos se separan hacia cuarentena; el resto continúa hacia Silver.
- **Transformación (Silver → Gold)**: la Lambda de transformación toma las filas Silver ya tipadas y completa el contrato Gold: genera `sale_id` si no vino uno válido, recalcula `total` como `quantity * price`, y reaplica las mismas validaciones de campo (idempotentes sobre datos ya normalizados). Asigna `store` según la división de origen en ambas etapas.

---

# Escritura en las capas Silver y Gold

- Las filas válidas se escriben en formato **Parquet**: Silver en `silver/store=<division>/date=<fecha>/` (Lambda de ingesta), Gold en `gold/store=<division>/date=<fecha>/` (Lambda de transformación) — en ambos casos sin las columnas `store` ni `date` dentro del archivo (quedan codificadas en el path como partición Hive; ver SPEC-002 y SPEC-005).
- Reprocesar el mismo archivo de origen (mismo `bronze/<division>/date=.../<division>_<fecha>.<ext>`) **sobrescribe** el resultado correspondiente tanto en Silver como en Gold para esa partición división+fecha ("último gana"); no se contempla deduplicación ni versionado de escrituras.
- Para cumplir "último gana" de forma efectiva, cada Lambda **borra los objetos existentes** bajo su propia partición (`silver/store=<division>/date=<fecha>/` o `gold/store=<division>/date=<fecha>/`, según corresponda) antes de escribir el nuevo Parquet de la invocación (delete-then-write). Esto es necesario porque el nombre del archivo Parquet incluye el `request_id` de la invocación (ver SPEC-005) y por lo tanto es distinto en cada reprocesamiento; sin el borrado previo, los archivos se acumularían en la misma partición en vez de sobrescribirse, duplicando filas en las consultas de Athena.

---

# Flujo de errores (alto nivel)

| Nivel | Caso | Acción |
|-------|------|--------|
| Fila | Campo faltante, tipo inválido, fecha no parseable, cantidad/precio no numérico o negativo (etapa ingesta o transformación) | La fila se envía a `quarantine/`; el resto del archivo continúa procesándose. Dado que la transformación reaplica las mismas reglas de campo que ya pasó Silver, en la práctica una fila solo cae en cuarentena en la etapa de ingesta — la transformación puede rechazarla igualmente si se reprocesara un Parquet Silver alterado manualmente. |
| Archivo | Nombre de archivo no coincide con ningún patrón de notificación S3 configurado, archivo corrupto o ilegible | Si ninguna Lambda se invoca, el archivo queda sin procesar en Bronze/Silver (visible por ausencia de datos en la capa siguiente). Si la Lambda correcta se invoca pero no puede leer el archivo, se registra el error en CloudWatch Logs y el archivo completo no genera salida en la capa siguiente. Tratamiento detallado en SPEC-005. |
| Lambda | Excepción no controlada durante el procesamiento | Se registra en CloudWatch Logs de la función correspondiente (ingesta o transformación); comportamiento de reintento sujeto a la configuración por defecto de Lambda ante invocaciones asíncronas desde S3. |

El detalle de implementación de validaciones, logging y manejo de excepciones se profundiza en SPEC-005.

---

# Fuera de alcance

- Orquestación automática o scheduling de la generación diaria de archivos (ver evoluciones futuras en SPEC-001).
- Uso de SQS, colas de mensajería o dead-letter queues.
- Deduplicación o versionado de archivos reprocesados.
- Reintentos avanzados o backoff configurado manualmente más allá del comportamiento por defecto de Lambda.
