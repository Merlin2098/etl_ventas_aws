# SPEC-007 - Generadores de Datos Sintéticos

## Estado

Borrador v0.1 (Línea Base)

---

# Objetivo

Definir el script Python que genera los datasets sintéticos de ventas para las 5 divisiones de RetailCorp (ver SPEC-002), en los formatos de origen correspondientes (CSV, Excel, JSON, PDF), y los sube a la capa Bronze del Data Lake (ver SPEC-003).

---

# Librerías a utilizar (criterio de decisión)

| Necesidad | Librería elegida | Alternativa considerada | Por qué |
|-----------|-------------------|--------------------------|---------|
| Datos falsos realistas (nombres de producto, categorías, direcciones) | **Faker** | `random.choice` sobre listas fijas (stdlib) | Ya está declarada en el proyecto (`requirements-dev.txt`); da variedad realista sin mantener catálogos curados a mano. Se promueve a dependencia de **runtime** (ver "Cambios a requirements.txt") porque los generadores no son código de test. |
| Escritura CSV | **csv (stdlib)** | pandas `to_csv` | CSV es el formato más simple de los cuatro; no amerita traer pandas solo para esto. Se usa `csv.DictWriter` directamente, alineado con la política de simplicidad (Policy 008 — preferir stdlib antes que dependencias). |
| Escritura Excel (.xlsx) | **openpyxl** | XlsxWriter | Ambas ya están en `requirements.txt`. Se elige openpyxl por ser la que ya se usa como motor de lectura de Excel en otras partes del framework (`fastexcel`/`openpyxl` en `requirements.txt`), evitando tener dos librerías distintas de Excel en el proyecto sin necesidad. |
| Escritura JSON | **json (stdlib)** | — | Sin alternativa relevante; `json.dump` cubre el caso por completo. |
| Escritura PDF | **reportlab** | fpdf2 | Ninguna de las dos estaba en el proyecto. Se elige reportlab por soporte maduro de tablas (`reportlab.platypus.Table`), necesario para producir un PDF con estructura tabular que luego `pdfplumber` (SPEC-005) pueda extraer de forma confiable vía `extract_table()`. Se agrega como nueva dependencia de runtime. |
| Subida a S3 | **boto3** | — | Ya está en `requirements.txt` (sección cloud); es el cliente estándar del framework para AWS. |

## Cambios a `requirements.txt` / `requirements-dev.txt`

- Mover `faker` de `requirements-dev.txt` a la sección `local` de `requirements.txt` (deja de ser solo dependencia de testing).
- Agregar `reportlab` a la sección `local` de `requirements.txt`.
- No se requieren más cambios: `openpyxl`, `boto3` ya están declarados.

---

# Estructura del script

Siguiendo `ai/skills/python/python_project_guidance.md` (lógica en `src/`, orquestación visible en `scripts/`):

```
scripts/
└── generate_sales.py          # entrypoint CLI único, parametrizado por --division

src/
└── generators/
    ├── __init__.py
    ├── common.py                # Faker seed, catálogo de categorías/productos, inyección de errores
    ├── schema.py                 # dataclass SaleRecord (campos "de origen", antes de normalizar)
    ├── writers/
    │   ├── csv_writer.py         # electronica, hogar
    │   ├── excel_writer.py       # supermercado
    │   ├── json_writer.py        # moda
    │   └── pdf_writer.py         # marketplace
    └── divisions.py               # mapeo division -> (writer, formato de fecha, extension)
```

---

# Entrypoint CLI

Un único script parametrizado, no 5 scripts separados:

```
python scripts/generate_sales.py --division electronica --date 2026-08-01
python scripts/generate_sales.py --division all --date 2026-08-01   # las 5 en secuencia
```

| Argumento | Descripción | Default |
|-----------|-------------|---------|
| `--division` | `electronica`, `supermercado`, `moda`, `hogar`, `marketplace`, o `all` (ejecuta las 5 en secuencia) | Requerido |
| `--date` | Fecha de negocio a generar (`YYYY-MM-DD`) | Fecha de ejecución (hoy) |
| `--rows` | Cantidad de filas a generar | 200-500 (ver SPEC-002) |
| `--error-rate` | Proporción de filas con errores intencionales (0.0-1.0) | 0.05 (5%, ver "Errores intencionales") |
| `--upload / --no-upload` | Si se sube el archivo generado a S3 Bronze o solo se escribe localmente | `--upload` |
| `--output-dir` | Carpeta local donde se escribe el archivo antes de subir (o en vez de subir con `--no-upload`) | `./generated/` |

`--division all` invoca internamente la misma lógica de generación por cada división, en el orden de la tabla de SPEC-002 (Electrónica, Supermercado, Moda, Hogar, Marketplace), consistente con SPEC-003 ("el presentador corre cada script o los cinco en secuencia").

---

# Selección de writer por división

`src/generators/divisions.py` centraliza el mapeo, evitando un `if/elif` disperso en el entrypoint:

```python
DIVISIONS = {
    "electronica":  DivisionConfig(writer=write_csv,   date_format="%d/%m/%Y", ext="csv"),
    "supermercado": DivisionConfig(writer=write_excel,  date_format="%m-%d-%Y", ext="xlsx"),
    "moda":         DivisionConfig(writer=write_json,   date_format="iso8601",  ext="json"),
    "hogar":        DivisionConfig(writer=write_csv,    date_format="%Y/%m/%d", ext="csv"),
    "marketplace":  DivisionConfig(writer=write_pdf,    date_format="texto_libre", ext="pdf"),
}
```

El formato de fecha por división refleja la heterogeneidad definida en SPEC-002 ("Fechas" — varía por división de forma realista); cada writer es responsable de formatear `date` según su propia convención antes de escribirla en el archivo de origen.

---

# Generación de filas

Cada fila generada, antes de pasar por el writer específico, se modela como:

```python
@dataclass
class SaleRecord:
    sale_id: str        # uuid4, ver SPEC-002
    date: datetime.date
    category: str
    product: str
    quantity: int
    price: Decimal
    # total NO se incluye: se calcula en la Lambda (SPEC-002/005), no en el generador
```

- `category` y `product` se obtienen de un catálogo curado por división en `common.py` (ej. Electrónica: "Audio", "Computación", "Telefonía"; productos ligados a esa categoría vía Faker (`fake.word()` combinado con listas de referencia, o `fake.catch_phrase()` como nombre de producto simulado) para mantener nombres plausibles sin depender de un dataset real de productos.
- `quantity`: entero aleatorio 1-10.
- `price`: decimal aleatorio dentro de un rango por categoría (ej. Electrónica más caro que Moda), usando `Faker.pydecimal` o `random.uniform` con redondeo a 2 decimales.
- `store` **no** se genera aquí: lo asigna la Lambda según la división de origen (SPEC-002).
- `total` **no** se genera aquí: se recalcula en la Lambda (SPEC-002, "Reglas básicas de transformación").

---

# Errores intencionales

Implementado en `common.py` como una función `maybe_corrupt(row: dict, error_rate: float) -> dict`, aplicada antes de pasar la fila al writer:

| Tipo de error | Ejemplo de corrupción aplicada |
|----------------|----------------------------------|
| Campo faltante | Eliminar `product` o `category` de la fila. |
| Tipo inválido | Reemplazar `quantity` por un string no numérico (`"N/A"`). |
| Fecha mal formateada | Escribir la fecha en un formato distinto al esperado por esa división, o como texto libre inválido (`"ayer"`). |
| Valor negativo | `quantity` o `price` negativo. |
| Encoding irregular (solo CSV) | Insertar un carácter fuera de UTF-8/Latin-1 en `product`. |

- La proporción de filas corrompidas por archivo es `--error-rate` (default 5%), aplicada por muestreo aleatorio sobre el total de filas (`--rows`).
- El tipo de corrupción a aplicar en cada fila afectada se elige aleatoriamente entre los tipos de la tabla anterior (equiprobable), salvo "Encoding irregular", que solo aplica a Electrónica y Hogar (divisiones CSV).
- Este comportamiento es el que SPEC-002 y SPEC-006 asumen como fuente de las filas que terminan en `quarantine/`.

---

# Carga hacia Amazon S3

- Tras escribir el archivo localmente en `--output-dir`, si `--upload` está activo (default), el script lo sube a Bronze usando boto3, con la convención de nombre definida en SPEC-003:

```
s3://<bucket>/bronze/date=<fecha>/<division>_<fecha>.<ext>
```

- El nombre de bucket se lee de una variable de entorno (`DATA_BUCKET`), nunca hardcodeado (Policy 003 — Configuration Over Hardcoding), consistente con el resto del framework.
- La subida es un `PutObject` simple (`boto3.client("s3").upload_file(...)`), sin multipart, alineado con SPEC-003.

---

# Reproducibilidad

- El script acepta `--seed` (opcional) para fijar la semilla de Faker y `random`, permitiendo regenerar exactamente el mismo dataset en ensayos previos al webinar.
- Sin `--seed`, cada ejecución genera datos distintos (comportamiento por defecto para simular variabilidad real).

---

# Fuera de alcance

- Generación de datos para más de una fecha en una sola invocación (`--date` es siempre una fecha única; generar un rango histórico queda como evolución futura).
- Validación de que el archivo generado es "parseable" por la Lambda correspondiente antes de subirlo — la corrupción intencional es exactamente lo que debe fallar validación en el pipeline (SPEC-005), no en el generador.
- Simulación de llegada fuera de horario o con delay artificial (los archivos se suben inmediatamente tras generarse).
