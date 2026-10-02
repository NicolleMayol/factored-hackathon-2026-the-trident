"""Bronze: las 13 fuentes de `landing`, 1:1 con el origen (ADR-22).

Sin reglas de negocio, sin dedup, sin recortes. Solo las tres columnas de servicio que exige ADR-22:
`_ingested_at`, `_source_file` y `_rescued_data`. Las columnas prohibidas (gender, marital_status,
date_of_birth) están aquí porque bronze es copia fiel; el recorte es de gold.
"""
import dlt
from pyspark.sql import functions as F

import schemas

CATALOG = spark.conf.get("medallon.catalog", "hackathon")  # noqa: F821  (spark lo inyecta el pipeline)
LANDING = spark.conf.get("medallon.landing")               # noqa: F821


def _tabla_bronze(fuente: str) -> None:
    @dlt.table(
        name=f"{CATALOG}.bronze.{fuente}",
        comment=f"Copia 1:1 de landing/{fuente} (ADR-22). Poblada por Auto Loader en CSV con multiLine (ADR-23).",
        table_properties={"quality": "bronze", "delta.enableChangeDataFeed": "false"},
    )
    def _():
        lector = spark.readStream.format("cloudFiles")  # noqa: F821
        for k, v in schemas.opciones(fuente).items():
            lector = lector.option(k, v)
        return (
            lector.load(schemas.ruta(LANDING, fuente))
            .withColumn("_ingested_at", F.current_timestamp())
            .withColumn("_source_file", F.col("_metadata.file_path"))
        )

    _.__name__ = f"bronze_{fuente}"


for _fuente in schemas.FUENTES:
    _tabla_bronze(_fuente)
