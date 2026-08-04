# INCIDENTE-001 - Trigger S3 silver/ -> Lambda transform no dispara

## Estado

Resuelto (2026-08-04) — ver "Resolución" al final del documento. Se descartó la
necesidad de abrir caso de soporte AWS: la causa raíz estaba en el propio
Terraform, no en la plataforma.

---

## Resumen

El pipeline E2E se ejecutó en AWS (cuenta `184670914470`, región `us-east-1`,
bucket `data-platform-dev-184670914470-datalake`) y se detuvo en la etapa
Silver: los objetos `silver/store=<division>/date=<fecha>/part-*.parquet` se
escriben correctamente, pero la Lambda de transformación (`transform-<division>`)
nunca se invoca automáticamente, por lo que nunca se generan objetos en `gold/`.

Se identificaron y resolvieron dos causas independientes durante la
investigación; **la segunda sigue sin solución conocida**:

1. **Bug de código (resuelto)** — `transform_handler_base.py` no inyectaba la
   fecha de partición Hive antes de validar las filas, causando que el 100%
   de las filas fueran a cuarentena (`cause=invalid_date`) y que
   `write_gold` nunca se invocara. Ver commit `718c856`.
2. **Trigger S3 -> Lambda roto (sin resolver)** — incluso con el fix
   desplegado, la notificación S3 configurada sobre el prefijo
   `silver/store=<division>/` no invoca la Lambda `transform-<division>`,
   ni con archivos generados por el pipeline real ni con `PutObject`
   manual vía AWS CLI. El trigger equivalente para `bronze/<division>/` ->
   `ingestion-<division>` sí funciona con normalidad.

---

## Cronología

| Hora (UTC) | Evento |
|---|---|
| — | Usuario reporta que el pipeline E2E se ejecutó y pide verificar en AWS. |
| — | Se confirma vía consola/API que el pipeline llega hasta Silver y no genera objetos en Gold. |
| 2026-08-03 22:48 | Se invoca `transform-electronica` (vía test E2E) contra un Silver real: `valid_rows: 0, invalid_rows: 341`, causa `invalid_date` en el 100% de las filas. |
| — | Se aísla la causa: `transform_handler_base.py` (versión desplegada, tag `e78f1c1`) llama a `validate_and_normalize(silver_row, ...)` sin inyectar `date` desde la partición Hive del key S3. `SILVER_SCHEMA` no incluye columna `date`, por lo que `parse_date(None)` devuelve `None` para toda fila. |
| — | Se confirma que el working tree ya tenía el fix (`row_with_date = {**silver_row, "date": partition_date}`) sin commitear ni desplegar. |
| 2026-08-04 ~03:10 | Se commitea el fix (excluyendo cambios no relacionados de retiro de un bucket de artifacts legacy) como `718c856`. |
| 2026-08-04 ~03:14 | Se reconstruyen y publican a ECR las 4 imágenes Docker (`electronica`, `supermercado`, `moda`, `marketplace`) con tag `718c856`. |
| 2026-08-04 03:15:44 | Usuario aplica `terraform apply` actualizando `image_uri` de las 8 Lambdas (4 ingestion + 4 transform) a `718c856`. Plan: 8 `update in-place`, 0 create, 0 destroy. |
| 2026-08-04 03:16:52 | Se reejecuta el test E2E. Ingestion procesa `bronze/electronica/...csv` correctamente (`valid_rows: 341`) y escribe a `silver/store=electronica/date=2026-08-02/part-2290d0f1-....parquet`. |
| 2026-08-04 03:16:54 – 03:18:54 | El test E2E espera 120s un objeto en `gold/store=electronica/...` y hace timeout. Las 4 divisiones fallan igual. |
| 2026-08-04 03:19 | Se confirma vía `describe-log-streams` que `transform-electronica` no tiene invocaciones nuevas: el log stream más reciente sigue siendo el de la corrida anterior (con el bug de `invalid_date`), sin actividad tras el deploy del fix. |
| 2026-08-04 03:19 | Métricas CloudWatch (`Invocations`, `Errors`) para `transform-electronica` en la ventana de la corrida: sin datapoints — la función no fue invocada en absoluto. |
| 2026-08-04 03:20 | Se revisa `get-bucket-notification-configuration`: las 8 reglas existen, con `LambdaFunctionArn`, `Events: s3:ObjectCreated:*` y `Filter.Key.FilterRules` correctos (`silver/store=electronica/` para transform-electronica). |
| 2026-08-04 03:20 | Se revisa `aws lambda get-policy` sobre `transform-electronica`: el resource policy `AllowS3InvokeTransform` existe, con `Principal: s3.amazonaws.com` y `Condition.ArnLike.AWS:SourceArn` apuntando al bucket correcto. |
| 2026-08-04 03:21 | **Invocación manual directa** (`aws lambda invoke` con el evento S3 sintetizado a mano) contra `transform-electronica`: **funciona correctamente** y escribe `gold/store=electronica/date=2026-08-02/part-b609e5db-....parquet`. Confirma que el código y el fix son correctos; el problema es exclusivamente el disparo automático. |
| 2026-08-04 03:20–03:22 | Se prueba un `PutObject` manual (copy-object) directo a `silver/store=electronica/...`: no genera ninguna invocación tras ~20s de espera. |
| 2026-08-04 03:22–03:23 | Se revisan posibles causas adicionales: encriptación del bucket (SSE-S3/AES256, sin KMS — descartada), versioning (deshabilitado — descartado), `EventBridgeConfiguration` del bucket (`null` — descartado), `Throttles`/concurrencia de la función (sin throttling, `UnreservedConcurrentExecutions: 400` — descartado), bucket policy (`NoSuchBucketPolicy` — descartado). |
| 2026-08-04 03:23 | Se compara la regla de notificación de `bronze/electronica/` (funciona) contra la de `silver/store=electronica/` (no funciona): estructuralmente idénticas salvo el prefijo. Se compara el resource policy de ambas Lambdas: estructuralmente idénticas salvo `Sid`/`Resource`. |
| 2026-08-04 03:24 | Se fuerza un refresh de la notification configuration (`put-bucket-notification-configuration` reescribiendo el mismo contenido). Se sube un archivo bronze fresco de prueba. |
| 2026-08-04 03:25 | Resultado: **ingestion sí se dispara automáticamente** con el archivo nuevo (`valid_rows: 341`, escribe a Silver). **Transform sigue sin dispararse** — confirmado con polling cada 10s durante ~90s sin cambios en `describe-log-streams`. |
| 2026-08-04 03:23–03:24 | Se prueba un segundo `PutObject` CLI directo a `silver/store=electronica/` (sin pasar por ninguna Lambda) tras el refresh: tampoco dispara, confirmado con 10 checks (~90s) sin cambios. |
| 2026-08-04 03:36 | Se recrea la notification configuration **desde cero**: primero `put-bucket-notification-configuration` con configuración vacía (`{}`), verificado que quedó vacía, luego se reconstruyen las 8 reglas idénticas a las originales. |
| 2026-08-04 03:36 | Se sube un tercer objeto de prueba directo a `silver/store=electronica/...` tras la recreación completa. |
| 2026-08-04 03:36–03:38 | Resultado: **sigue sin disparar**, confirmado con 12 checks cada 10s (2 minutos completos) sin ninguna invocación nueva registrada en CloudWatch Logs. |

---

## Evidencia clave

- **Notification config** (`aws s3api get-bucket-notification-configuration`, idéntica antes y después de recrearla): 8 `LambdaFunctionConfigurations`, 4 para `bronze/<division>/` -> `ingestion-<division>`, 4 para `silver/store=<division>/` -> `transform-<division>`, todas con `Events: ["s3:ObjectCreated:*"]`.
- **Resource policy de la Lambda** (`aws lambda get-policy --function-name data-platform-dev-transform-electronica`):
  ```json
  {"Version":"2012-10-17","Id":"default","Statement":[{"Sid":"AllowS3InvokeTransform","Effect":"Allow","Principal":{"Service":"s3.amazonaws.com"},"Action":"lambda:InvokeFunction","Resource":"arn:aws:lambda:us-east-1:184670914470:function:data-platform-dev-transform-electronica","Condition":{"ArnLike":{"AWS:SourceArn":"arn:aws:s3:::data-platform-dev-184670914470-datalake"}}}]}
  ```
- **Invocación manual exitosa** (prueba de que el código funciona):
  ```
  aws lambda invoke --function-name data-platform-dev-transform-electronica \
    --payload fileb://test_event.json invoke_result.json
  # -> {"StatusCode": 200, "ExecutedVersion": "$LATEST"}
  # -> {"gold": ["s3://.../gold/store=electronica/date=2026-08-02/part-b609e5db-....parquet"], "quarantine": []}
  ```
- **Terraform state** (`terraform state show module.s3_data_lake.aws_s3_bucket_notification.data_lake_ingestion`) coincide exactamente con lo observado vía AWS CLI — no hay drift entre el state y la realidad.
- El trigger de `bronze/<division>/` -> `ingestion-<division>` funciona en todo momento, incluso en las mismas ventanas de tiempo en que `silver/store=<division>/` -> `transform-<division>` falla. Esto descarta explicaciones a nivel de cuenta/servicio que afectarían ambos triggers por igual (p. ej. un throttling global de S3 Event Notifications).

---

## Hipótesis descartadas

- Bug en el código de la Lambda de transform (descartado: invocación manual funciona).
- Config de notificación incorrecta o con drift respecto a Terraform (descartado: verificado idéntica vía API y state).
- Resource policy faltante o mal condicionado (descartado: presente y estructuralmente igual al de ingestion, que sí funciona).
- Bucket policy bloqueando el prefijo `silver/` (descartado: no existe bucket policy, `NoSuchBucketPolicy`).
- EventBridge notifications compitiendo o reemplazando las de Lambda (descartado: `EventBridgeConfiguration: null`).
- Encriptación KMS requiriendo permisos adicionales para que S3 publique el evento (descartado: bucket usa SSE-S3/AES256, no KMS).
- Throttling o límite de concurrencia de Lambda bloqueando la invocación silenciosamente (descartado: sin throttles registrados, `UnreservedConcurrentExecutions: 400` disponibles).
- Config "stale"/no propagada tras el último `terraform apply` (descartado: se forzó un refresh completo — vaciar y reconstruir la notification configuration desde cero — sin efecto).
- Problema específico de cómo escribe la Lambda de ingestion a Silver (multipart upload, metadata, content-type) (descartado: un `PutObject` CLI simple y directo tampoco dispara el trigger).

---

## Hipótesis no descartadas / pendientes de investigar

- Algún control a nivel de cuenta u organización AWS (AWS Config Rule, Service Control Policy, guardrail de Control Tower/Landing Zone) que intercepte o bloquee silenciosamente notificaciones S3 para el patrón de prefijo `store=<division>/` específicamente. Es la única diferencia estructural identificada entre el prefijo que funciona (`bronze/<division>/`) y el que no (`silver/store=<division>/`) — en particular el carácter `=` dentro del prefijo, aunque este debería ser válido según la documentación de S3 Event Notifications.
- Problema interno de AWS S3 en la suscripción de notificación para este bucket/prefijo específico, no visible ni corregible vía la API pública (candidato a abrir caso de soporte AWS).
- Posible incompatibilidad o bug de la versión del provider Terraform AWS (`hashicorp/aws` `5.100.0`, ver `infra/.terraform.lock.hcl`) al gestionar múltiples `lambda_function` dentro de un único `aws_s3_bucket_notification` con prefijos similares — aunque la recreación manual vía AWS CLI (fuera de Terraform) tampoco resolvió el problema, lo que apunta más a un comportamiento de la plataforma S3 que del provider.

---

## Impacto

- El pipeline productivo (event-driven, sin intervención manual) **no completa la etapa Silver -> Gold** para ninguna de las 4 divisiones.
- Workaround disponible pero no automatizado: invocar manualmente cada Lambda `transform-<division>` con el evento S3 sintetizado a partir del key recién escrito en Silver. Verificado funcional para `electronica` (ver evidencia arriba).

---

## Próximos pasos sugeridos

1. Abrir caso de soporte AWS adjuntando esta cronología, especialmente la comparación entre el prefijo que funciona y el que no, y la prueba de invocación manual exitosa.
2. Revisar (si existen) SCPs, Config Rules o guardrails a nivel de Organización AWS que puedan afectar `PutBucketNotificationConfiguration` o la entrega de eventos para prefijos con `=`.
3. Como prueba adicional de bajo costo: crear una regla de notificación temporal con un prefijo sin el carácter `=` (p. ej. renombrar a `silver-electronica/` en un bucket de prueba) para aislar si el carácter es la causa.
4. Evaluar automatizar el workaround (invocación manual con el evento S3 reconstruido) como mitigación temporal si el diagnóstico con AWS toma tiempo, documentando que es un parche y no la arquitectura event-driven prevista en SPEC-003/SPEC-004.
5. Una vez resuelto, volver a correr `tests/e2e/test_pipeline_aws.py` como criterio de cierre del incidente.

---

## Referencias

- Commit del fix de código: `718c856` — "fix: inyectar la fecha de partición Hive antes de validar filas Silver->Gold"
- `src/lambda_ingestion/common/transform_handler_base.py`
- `infra/modules/s3_data_lake/main.tf` (`aws_s3_bucket_notification.data_lake_ingestion`)
- `infra/modules/lambda_ingestion/main.tf` (`aws_lambda_permission.allow_s3_invoke_transform`)
- `tests/e2e/test_pipeline_aws.py`
- `specs/pipeline/SPEC-003_Pipeline_Procesamiento.md` (flujo esperado Bronze -> Silver -> Gold)
- `specs/pipeline/SPEC-004_Infraestructura_Terraform.md`

---

## Resolución

**Causa raíz real: un `depends_on` mal cableado en Terraform, no un problema de
plataforma AWS.**

En `infra/modules/s3_data_lake/main.tf` (versión previa a esta resolución), el
recurso `aws_s3_bucket_notification.data_lake_ingestion` tenía:

```hcl
depends_on = [var.lambda_permission_dependency]
```

Y en `infra/main.tf`, `lambda_permission_dependency` se poblaba así:

```hcl
lambda_permission_dependency = merge(
  module.lambda_ingestion.function_names,
  module.lambda_ingestion.transform_function_names,
)
```

Dos problemas independientes en esas tres líneas:

1. **El `depends_on` apuntaba a nombres de función, no a los recursos
   `aws_lambda_permission`.** Un `depends_on` sobre un valor que no referencia
   el recurso de permisos no crea ninguna arista de dependencia con
   `aws_lambda_permission` — Terraform no tenía garantía de que los 8 permisos
   existieran antes de registrar las 8 reglas de notificación.
2. **El `merge()` de dos mapas con las mismas claves de división (`electronica`,
   `moda`, ...) colapsaba 8 entradas en 4**: las de `transform_function_names`
   pisaban a las de `function_names`. Aun si el `depends_on` hubiera apuntado a
   los recursos correctos, solo habría cubierto la mitad del pipeline.

**Por qué esto explica exactamente el síntoma observado**, incluyendo lo que
parecía inexplicable durante la investigación:

- **Ingestion funcionaba, transform no.** No fue casualidad ni el carácter
  `=`. En la creación inicial, Terraform crea las 8 reglas de notificación en
  una sola llamada a `PutBucketNotificationConfiguration`. S3 valida los
  permisos **en el momento de esa llamada**. Los `aws_lambda_permission` de
  ingestion se crearon antes por orden fortuito del grafo de recursos; los de
  transform no tenían esa garantía.
- **Las 8 reglas aparecían en `get-bucket-notification-configuration` y
  coincidían con el state** (líneas 49, 66 y 78 de este documento). Eso era
  correcto — la configuración *se escribió* — y es justo lo que despistó la
  investigación: el problema no era la config almacenada, sino que la
  suscripción de entrega de eventos para esas 4 reglas nunca quedó activa del
  lado de S3.
- **Recrear la notificación a mano no lo arregló** (líneas 58-60). Coherente:
  recrearla vía CLI reescribe la misma configuración, pero eso no repara el
  vínculo de entrega si S3 lo rechazó silenciosamente en su momento de
  creación original.

**Hipótesis del carácter `=` descartada con evidencia interna del propio
repo**, sin necesidad de caso de soporte AWS: los prefijos
`quarantine/store=<division>/` y `gold/store=<division>/` usan el mismo
carácter `=` en sus rutas de escritura y nunca presentaron problema. S3 admite
`=` en `filter_prefix` (y en el patrón de eventos de EventBridge) sin
restricción — la evidencia listada en "Hipótesis no descartadas / pendientes
de investigar" (línea 99 original) señalaba una diferencia estructural real
entre `bronze/` y `silver/store=`, pero la diferencia relevante nunca fue el
carácter: fue que las 4 reglas de `transform-*` cayeron del lado equivocado
del bug de `merge()`.

### Solución adoptada

Se migró el mecanismo de trigger de notificación S3 directa a **EventBridge**
(Opción C evaluada durante el diagnóstico): el bucket publica eventos
`Object Created` al bus de eventos de la cuenta (`aws_s3_bucket_notification`
con `eventbridge = true`), y 8 reglas de EventBridge (una por división y por
etapa, en el nuevo módulo `infra/modules/eventbridge/`) enrutan cada evento a
su Lambda, con su propio `aws_lambda_permission` scopeado al ARN de la regla.

Esta migración no es solo un rodeo al bug — lo corrige de raíz para esta
*clase* de problema: `source_arn = aws_cloudwatch_event_rule...arn` es una
referencia real de Terraform, así que **es** la arista de dependencia que
antes faltaba. Regla y permiso viven en el mismo módulo, por lo que no hay
forma de que ese ordenamiento vuelva a romperse en silencio entre módulos.

Detalle completo del diseño en SPEC-003 ("Eventos de S3 y enrutamiento con
EventBridge") y SPEC-004 (sección `modules/eventbridge`, y la nota sobre
Policy 010 aplicada a la nueva dirección de la dependencia).

### Criterio de cierre

`tests/e2e/test_pipeline_aws.py` en verde para las 4 divisiones (no solo
`electronica`), con objetos Gold nuevos en
`gold/store=<division>/date=2026-08-02/`, según el paso 5 de "Próximos pasos
sugeridos" de este mismo documento. Verificado adicionalmente por las nuevas
aserciones de `tests/aws/test_smoke.py` sobre reglas, targets y permisos de
EventBridge — la clase de verificación que, de haber existido antes, habría
detectado este incidente en el propio `terraform apply` en vez de en la
corrida E2E.
