# Imagen base oficial de AWS para funciones Lambda en Python 3.12.
# Ya incluye el runtime de Lambda (bootstrap) — solo hay que copiar el código
# e indicar el handler en CMD.
FROM public.ecr.aws/lambda/python:3.12

# DIVISION identifica qué división de negocio empaqueta esta imagen
# (electronica/supermercado/moda/marketplace). Una sola Dockerfile genérica
# sirve para las 4 divisiones: el build pasa --build-arg DIVISION=<división>
# (ver scripts/docker/docker_build.sh) y así se decide qué carpeta de código
# copiar (línea 21) sin duplicar este archivo por división.
ARG DIVISION
ENV DIVISION=${DIVISION}

# Dependencias Python primero, antes de copiar el código de la aplicación:
# así Docker reutiliza esta capa en cache entre builds mientras no cambien
# las dependencias, aunque el código de los handlers sí cambie.
COPY src/lambda_ingestion/requirements-lambda.txt .
RUN pip install -r requirements-lambda.txt --no-cache-dir

# Código compartido por todas las divisiones: utilidades comunes (parseo base,
# logging, escritura a S3) y el handler de transformación Silver -> Gold, que
# es el mismo para las 4 divisiones (ver SPEC-005).
COPY src/lambda_ingestion/common/ ${LAMBDA_TASK_ROOT}/lambda_ingestion/common/
COPY src/lambda_ingestion/transform/ ${LAMBDA_TASK_ROOT}/lambda_ingestion/transform/
COPY src/lambda_ingestion/__init__.py ${LAMBDA_TASK_ROOT}/lambda_ingestion/__init__.py

# Código específico de la división (parser + handler de ingesta Bronze ->
# Silver). Es la única copia que varía según el valor de DIVISION.
COPY src/lambda_ingestion/${DIVISION}/ ${LAMBDA_TASK_ROOT}/lambda_ingestion/${DIVISION}/
COPY src/__init__.py ${LAMBDA_TASK_ROOT}/src/__init__.py

# IMPORTANTE: Lambda exige que CMD use la forma "exec" (array JSON), y Docker
# NO sustituye variables de build/entorno dentro de esa forma (a diferencia de
# ENV/COPY/LABEL, que sí las sustituyen). Por eso __DIVISION__ abajo es un
# placeholder literal en texto, no una variable de Docker: scripts/docker/
# docker_build.sh lo reemplaza con `sed` (por ejemplo, por "electronica") en
# un Dockerfile temporal antes de ejecutar `docker build`, de modo que la
# imagen final ya queda con el handler correcto grabado.
#
# Esta misma imagen sirve para las 2 Lambdas de la división (ingesta y
# transformación): el CMD de abajo es el handler de ingesta por defecto, y
# Terraform sobreescribe el comando solo para la Lambda de transformación vía
# image_config.command — sin necesidad de construir una imagen aparte
# (ver SPEC-005).
CMD ["lambda_ingestion.__DIVISION__.handler.handler"]
