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
S3 Event Notification (ObjectCreated)
        │
        ▼
 Lambda (Docker) — una función por división/formato
        │
        ├── Valida y transforma filas con su parser dedicado
        │
        ├── Filas válidas ──────────► Amazon S3 (Gold) — partición por división y fecha
        │
        └── Filas inválidas ───────► Amazon S3 (Quarantine)
```

Cada división tiene su propia función Lambda (5 en total), cada una empaquetada en una imagen Docker independiente con el parser de su formato. No existe una Lambda única con router interno: la selección de parser queda resuelta por la propia suscripción del evento S3 a cada función (ver "Eventos de S3").

---

# Generación de archivos

- Cada división tiene un generador Python independiente (ver SPEC-002).
- Durante el webinar, la llegada diaria de archivos se simula mediante **ejecución manual** de los generadores: el presentador corre cada script (o los cinco en secuencia) para mostrar el pipeline reaccionando en vivo, archivo por archivo.
- No existe un orquestador automático ni un scheduler en el alcance de esta demo; queda como evolución futura (SPEC-001, sección "Evoluciones futuras": EventBridge Scheduler).

---

# Carga hacia Amazon S3

- Cada generador, tras crear el archivo localmente, lo sube directamente al bucket/prefijo **Bronze**.
- La subida es un `PutObject` simple por archivo; no hay carga por lotes ni multipart en el alcance de esta demo.

---

# Organización del Data Lake

## Capa Bronze

- Los datos se reciben **tal cual** son generados, sin transformación.
- Partición **solo por fecha** (sin partición por división):

```
s3://<bucket>/bronze/date=YYYY-MM-DD/<division>_<YYYY-MM-DD>.<ext>
```

Ejemplo:

```
s3://<bucket>/bronze/date=2026-08-01/electronica_2026-08-01.csv
s3://<bucket>/bronze/date=2026-08-01/supermercado_2026-08-01.xlsx
s3://<bucket>/bronze/date=2026-08-01/moda_2026-08-01.json
s3://<bucket>/bronze/date=2026-08-01/hogar_2026-08-01.csv
s3://<bucket>/bronze/date=2026-08-01/marketplace_2026-08-01.pdf
```

La división queda identificada en el nombre de archivo (necesaria para que la Lambda seleccione el parser correcto, ver SPEC-005).

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

- Se configura una **S3 Event Notification** (`s3:ObjectCreated:*`) sobre el prefijo `bronze/`, filtrada por patrón de nombre de archivo (`filter_prefix`/`filter_suffix`, ej. `electronica_` para la Lambda de Electrónica) para invocar la función Lambda correspondiente a cada división.
- No se utiliza SQS como buffer intermedio: cada archivo dispara una invocación independiente de su Lambda dedicada (modelo simple, adecuado para el volumen y propósito didáctico de esta demo).

---

# Ejecución automática de Lambda

- Cada Lambda se invoca una vez por archivo de su división subido a `bronze/` (filtrado por el patrón de nombre configurado en la notificación S3).
- Recibe el evento S3 (bucket y key del objeto creado) y descarga el archivo para procesarlo con su parser dedicado.

---

# Detección del tipo de archivo

- La selección de la función Lambda correcta ocurre a nivel de infraestructura (filtro de la S3 Event Notification por nombre de archivo), no dentro de la función.
- Dentro de cada Lambda, el formato es conocido de antemano (una función = un formato = un parser), por lo que no existe lógica de detección/enrutamiento en tiempo de ejecución.
- Si un archivo llega a `bronze/` sin coincidir con ningún patrón de nombre configurado, ninguna Lambda se invoca; el archivo queda huérfano en Bronze (ver "Flujo de errores").

---

# Conversión hacia formato estándar

- Cada Lambda aplica su parser dedicado (uno por formato/división) para transformar las filas del archivo de origen al esquema unificado Gold definido en SPEC-002.
- Reglas aplicadas durante la conversión (detalladas en SPEC-002):
  - Normalización de `date` al formato `YYYY-MM-DD`.
  - Asignación de `store` según la división de origen.
  - Recalculo de `total` como `quantity * price`.
- Filas que no puedan completarse según el esquema Gold se separan hacia el flujo de cuarentena; el resto del archivo continúa su procesamiento normal.

---

# Escritura en la capa Gold

- Las filas válidas y transformadas se escriben en formato **Parquet** en `gold/store=<division>/date=<fecha>/`.
- Reprocesar el mismo archivo de origen (mismo `bronze/date=.../<division>_<fecha>.<ext>`) **sobrescribe** el resultado correspondiente en Gold para esa partición división+fecha ("último gana"); no se contempla deduplicación ni versionado de escrituras.

---

# Flujo de errores (alto nivel)

| Nivel | Caso | Acción |
|-------|------|--------|
| Fila | Campo faltante, tipo inválido, fecha no parseable, cantidad/precio no numérico o negativo | La fila se envía a `quarantine/`; el resto del archivo continúa procesándose. |
| Archivo | Nombre de archivo no coincide con ningún patrón de notificación S3 configurado, archivo corrupto o ilegible | Si ninguna Lambda se invoca, el archivo queda sin procesar en Bronze (visible por ausencia de datos en Gold). Si la Lambda correcta se invoca pero no puede leer el archivo, se registra el error en CloudWatch Logs y el archivo completo no genera salida en Gold. Tratamiento detallado en SPEC-005. |
| Lambda | Excepción no controlada durante el procesamiento | Se registra en CloudWatch Logs de la función correspondiente; comportamiento de reintento sujeto a la configuración por defecto de Lambda ante invocaciones asíncronas desde S3. |

El detalle de implementación de validaciones, logging y manejo de excepciones se profundiza en SPEC-005.

---

# Fuera de alcance

- Orquestación automática o scheduling de la generación diaria de archivos (ver evoluciones futuras en SPEC-001).
- Uso de SQS, colas de mensajería o dead-letter queues.
- Deduplicación o versionado de archivos reprocesados.
- Reintentos avanzados o backoff configurado manualmente más allá del comportamiento por defecto de Lambda.
