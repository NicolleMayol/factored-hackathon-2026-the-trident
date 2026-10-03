"""Bronze: las 13 fuentes de `landing`, 1:1 con el origen (ADR-22).

Sin reglas de negocio, sin dedup, sin recortes. Solo las tres columnas de servicio que exige ADR-22:
`_ingested_at`, `_source_file` y `_rescued_data`. Las columnas prohibidas (gender, marital_status,
date_of_birth) están aquí porque bronze es copia fiel; el recorte es de gold.

Dos formas de leer, porque el origen tiene dos formas (ADR-23):

  - Las 7 fuentes **particionadas** (`<tabla>/year=/month=/day=/`) son hechos que solo crecen:
    tabla de streaming con Auto Loader, que procesa lo nuevo en cada corrida.
  - Las 6 fuentes de la **raíz** son un archivo suelto por tabla y el diccionario las declara
    `monthly_snapshot` o `full_snapshot`: el archivo se reemplaza entero, no se le añaden filas.
    Van como vista materializada en lote. Auto Loader además no las admite: exige un directorio y
    falla con `CloudInvalidPathException: Input path is not a directory` (medido 2026-10-03).
"""
from pyspark import pipelines as dp
from pyspark.sql import functions as F

import schemas

CATALOG = spark.conf.get("medallon.catalog", "hackathon")  # noqa: F821  (spark lo inyecta el pipeline)
LANDING = spark.conf.get("medallon.landing")               # noqa: F821

COMENTARIO = "Copia 1:1 de landing/{0} (ADR-22). CSV con multiLine y escape de comilla doble (ADR-23)."
PROPIEDADES = {"quality": "bronze", "delta.enableChangeDataFeed": "false"}


def _con_servicio(df):
    """Las tres columnas que ADR-22 exige en bronze. `_rescued_data` la añade el lector."""
    return (
        df.withColumn("_ingested_at", F.current_timestamp())
          .withColumn("_source_file", F.col("_metadata.file_path"))
    )


def _streaming(fuente: str) -> None:
    """Hecho particionado: solo crece, así que se ingiere de forma incremental."""

    @dp.table(name=f"{CATALOG}.bronze.{fuente}", comment=COMENTARIO.format(fuente), table_properties=PROPIEDADES)
    def _leer():
        lector = spark.readStream.format("cloudFiles")  # noqa: F821
        for k, v in schemas.opciones(fuente).items():
            lector = lector.option(k, v)
        return _con_servicio(lector.load(schemas.ruta(LANDING, fuente)))


def _snapshot(fuente: str) -> None:
    """Dimensión o referencia: un archivo que se reemplaza entero en cada carga."""

    @dp.table(name=f"{CATALOG}.bronze.{fuente}", comment=COMENTARIO.format(fuente), table_properties=PROPIEDADES)
    def _leer():
        lector = spark.read.format("csv")  # noqa: F821
        for k, v in schemas.opciones(fuente, streaming=False).items():
            lector = lector.option(k, v)
        return _con_servicio(lector.load(schemas.ruta(LANDING, fuente)))


for _fuente in schemas.PARTICIONADAS:
    _streaming(_fuente)

for _fuente in schemas.RAIZ:
    _snapshot(_fuente)
