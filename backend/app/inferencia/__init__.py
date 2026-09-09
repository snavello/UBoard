"""Inferencia del modelo semantico (fase 2).

En capas, como pide la especificacion (§1.3): primero `heuristicas.py`
(deterministas, baratas, con confianza y evidencia: claves primarias,
relaciones, tipos semanticos, metricas obvias, dimensiones de tiempo);
despues Claude solo para lo semantico (paso 11). `fusion.py` mezcla una
propuesta nueva con el modelo que ya trabajo el usuario, respetando lo
confirmado y lo rechazado. `tarea.py` lo corre en la cola.
"""
