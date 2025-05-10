import numpy as np
from scipy import stats

def calcular_estadisticas(datos):
    """
    Calcula estadísticas básicas de una lista de números.
    :param datos: Lista de números.
    :return: Diccionario con media, mediana, moda, varianza y desviación estándar.
    """
    if not datos:
        return {"error": "Lista vacía, no se pueden calcular estadísticas."}

    datos_np = np.array(datos)
    
    return {
        "media": np.mean(datos_np),
        "mediana": np.median(datos_np),
        "moda": stats.mode(datos_np, keepdims=False).mode,
        "varianza": np.var(datos_np),
        "desviacion_estandar": np.std(datos_np)
    }