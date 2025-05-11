from fastapi import FastAPI, Depends, File, UploadFile, HTTPException
import xmltodict
import numpy as np
from scipy import stats
from sklearn.linear_model import LinearRegression
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.database import get_db
from app.models.models import CFDComprobante, CFDEmisor, CFDReceptor
from datetime import datetime
from app.routes.auth import auth_router
from sqlalchemy import text

app = FastAPI(title="Mi API", version="1.0", openapi_prefix="/api/")

app.include_router(auth_router, prefix="/auth", tags=["Authentication"])

# 📌 Manteniendo tus funciones actuales
@app.post("/procesar_xml")
async def procesar_xml(file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
    xml_content = await file.read()
    xml_str = xml_content.decode("utf-8").replace("cfdi:", "")
    data_dict = xmltodict.parse(xml_str)
    comprobante_data = data_dict.get("Comprobante", {})

    if not comprobante_data:
        return {"error": "No se pudo procesar el comprobante."}

    fecha_str = comprobante_data.get("@Fecha")
    if fecha_str:
        try:
            fecha = datetime.strptime(fecha_str, "%Y-%m-%dT%H:%M:%S")
        except ValueError:
            return {"error": "Formato de fecha incorrecto."}
    else:
        return {"error": "El campo Fecha es obligatorio."}

    emisor_data = comprobante_data.get("Emisor", {})
    rfc_emisor = emisor_data.get("@Rfc")
    nombre_emisor = emisor_data.get("@Nombre")
    regimen_fiscal_emisor = emisor_data.get("@RegimenFiscal")

    if not rfc_emisor or not nombre_emisor or not regimen_fiscal_emisor:
        return {"error": "El Emisor debe contener RFC, Nombre y Régimen Fiscal."}

    emisor = CFDEmisor(rfc=rfc_emisor, nombre=nombre_emisor, regimen_fiscal=regimen_fiscal_emisor)
    db.add(emisor)
    await db.commit()
    await db.refresh(emisor)

    return {"mensaje": "Archivo XML procesado correctamente"}

@app.post("/analizar_datos")
async def analizar_datos(db: AsyncSession = Depends(get_db)):
    # Obtener valores de la BD
    resultados = await db.execute(text("SELECT total FROM cfd_comprobante"))
    valores = [float(row[0]) for row in resultados.fetchall()]

    if not valores:
        return {"error": "No se encontraron datos suficientes en la base de datos."}

    datos_np = np.array(valores)

    resultado = {
        "media": float(np.mean(datos_np)),
        "mediana": float(np.median(datos_np)),
        "moda": [int(x) for x in stats.mode(datos_np, keepdims=False).mode.tolist()],
        "varianza": float(np.var(datos_np)),
        "desviacion_estandar": float(np.std(datos_np))
    }

    return {"estadisticas": resultado}

# 🗑️ Eliminar un Emisor por RFC
from sqlalchemy import text

@app.delete("/emisor/{rfc}")
async def eliminar_emisor(rfc: str, db: AsyncSession = Depends(get_db)):
    # Obtener ID del emisor con consulta segura
    emisor = await db.execute(text("SELECT id_emisor FROM cfd_emisor WHERE rfc = :rfc"), {"rfc": rfc})
    emisor_id = emisor.scalar()

    if not emisor_id:
        raise HTTPException(status_code=404, detail="Emisor no encontrado")

    # Eliminar dependencias antes de eliminar el emisor
    await db.execute(text("DELETE FROM cfd_impuesto_trasladado_general WHERE id_comprobante IN (SELECT id_comprobante FROM cfd_comprobante WHERE id_emisor = :emisor_id)"), {"emisor_id": emisor_id})
    await db.execute(text("DELETE FROM cfd_concepto WHERE id_comprobante IN (SELECT id_comprobante FROM cfd_comprobante WHERE id_emisor = :emisor_id)"), {"emisor_id": emisor_id})
    await db.execute(text("DELETE FROM cfd_impuesto_trasladado_concepto WHERE id_concepto IN (SELECT id_concepto FROM cfd_concepto WHERE id_comprobante IN (SELECT id_comprobante FROM cfd_comprobante WHERE id_emisor = :emisor_id))"), {"emisor_id": emisor_id})
    await db.execute(text("DELETE FROM cfd_comprobante WHERE id_emisor = :emisor_id"), {"emisor_id": emisor_id})

    # Finalmente, eliminar el emisor
    await db.execute(text("DELETE FROM cfd_emisor WHERE id_emisor = :emisor_id"), {"emisor_id": emisor_id})
    await db.commit()

    return {"mensaje": f"Emisor con RFC {rfc} eliminado correctamente"}

# 📊 Análisis Estadístico Descriptivo

@app.post("/analisis_descriptivo")
async def analisis_descriptivo(db: AsyncSession = Depends(get_db)):
    resultados = await db.execute(text("SELECT total FROM cfd_comprobante"))
    valores = [float(row[0]) for row in resultados.fetchall()]

    if not valores:
        return {"error": "No se encontraron datos suficientes en la base de datos."}

    return {
        "cantidad_registros": len(valores),  # Nuevo campo para verificar cuántos valores están siendo analizados
        "media": float(np.mean(valores)),
        "mediana": float(np.median(valores)),
        "varianza": float(np.var(valores)),
        "desviacion_estandar": float(np.std(valores))
    }


    datos_np = np.array(valores)

    # Asegurar que stats.mode siempre devuelva una lista
    moda_valores = stats.mode(datos_np, keepdims=False).mode
    moda_lista = moda_valores if isinstance(moda_valores, (list, np.ndarray)) else [moda_valores]

    resultado = {
        "media": float(np.mean(datos_np)),
        "mediana": float(np.median(datos_np)),
        "moda": [int(x) for x in moda_lista],
        "varianza": float(np.var(datos_np)),
        "desviacion_estandar": float(np.std(datos_np)),
        "minimo": int(np.min(datos_np)),
        "maximo": int(np.max(datos_np)),
        "rango": int(np.ptp(datos_np)),
        "percentiles": [float(x) for x in np.percentile(datos_np, [25, 50, 75]).tolist()]
    }

    return {"estadisticas_descriptivas": resultado}

# 🏆 Análisis Estadístico Inferencial
from sqlalchemy import text

@app.post("/analisis_inferencial")
async def analisis_inferencial(db: AsyncSession = Depends(get_db)):
    # Obtener datos históricos desde la base de datos
    grupo1_result = await db.execute(text("SELECT total FROM cfd_comprobante WHERE tipo_de_comprobante = 'I'"))
    grupo2_result = await db.execute(text("SELECT total FROM cfd_comprobante WHERE tipo_de_comprobante = 'E'"))
    
    grupo1 = [float(row[0]) for row in grupo1_result.fetchall()]
    grupo2 = [float(row[0]) for row in grupo2_result.fetchall()]

    if not grupo1 or not grupo2:
        return {"error": "No se encontraron suficientes datos en la base de datos."}

    # Aplicar prueba t de Student
    t_test = stats.ttest_ind(grupo1, grupo2, equal_var=False)
    
    return {
        "prueba_t": {
            "statistica": t_test.statistic,
            "p_valor": t_test.pvalue
        }
    }

# 🔮 Análisis Predictivo con Regresión Lineal
@app.post("/analisis_predictivo")
async def analisis_predictivo(db: AsyncSession = Depends(get_db)):
    # Obtener datos históricos
    datos_result = await db.execute(text("SELECT fecha, total FROM cfd_comprobante ORDER BY fecha ASC"))
    datos = [(row[0], float(row[1])) for row in datos_result.fetchall()]

    if not datos:
        return {"error": "No se encontraron datos suficientes en la base de datos."}

    # Preparar datos para la regresión
    fechas = np.array([dato[0].timestamp() for dato in datos]).reshape(-1, 1)  # Convertir fecha a timestamp
    valores = np.array([dato[1] for dato in datos])

    modelo = LinearRegression()
    modelo.fit(fechas, valores)
    predicciones = modelo.predict(fechas).tolist()

    return {
        "coeficiente": modelo.coef_.tolist(),
        "intercepto": modelo.intercept_.tolist(),
        "predicciones": predicciones
    }