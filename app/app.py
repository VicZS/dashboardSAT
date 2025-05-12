from fastapi import FastAPI, Depends, File, UploadFile, HTTPException, Query
from fastapi.responses import JSONResponse
import xmltodict
import numpy as np
from scipy import stats
from sklearn.linear_model import LinearRegression
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, date
from typing import Optional
from pydantic import conint
from sqlalchemy import text

from app.database.database import get_db
from app.models.models import CFDComprobante, CFDEmisor, CFDReceptor, CFDConcepto, CFDImpuestoTrasladadoGeneral, CFDImpuestoTrasladadoConcepto
from app.routes.auth import auth_router

from typing import Dict

from typing import Annotated
from pydantic import conint
from fastapi import Query, Depends
from sqlalchemy.ext.asyncio import AsyncSession



app = FastAPI(title="API de Análisis CFDI", version="1.0", openapi_prefix="/api/")

app.include_router(auth_router, prefix="/auth", tags=["Authentication"])

@app.post("/procesar_xml")
async def procesar_xml(file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
    # Leer y parsear el archivo XML
    xml_content = await file.read()
    xml_str = xml_content.decode("utf-8").replace("cfdi:", "")
    data_dict = xmltodict.parse(xml_str)
    comprobante_data = data_dict.get("Comprobante", {})

    # Validación de datos del comprobante
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

    # Datos del Emisor
    emisor_data = comprobante_data.get("Emisor", {})
    rfc_emisor = emisor_data.get("@Rfc")
    nombre_emisor = emisor_data.get("@Nombre")
    regimen_fiscal_emisor = emisor_data.get("@RegimenFiscal")
    
    if not rfc_emisor or not nombre_emisor or not regimen_fiscal_emisor:
        return {"error": "El Emisor debe contener RFC, Nombre y Régimen Fiscal."}

    # Crear el registro del Emisor
    emisor = CFDEmisor(rfc=rfc_emisor, nombre=nombre_emisor, regimen_fiscal=regimen_fiscal_emisor)
    db.add(emisor)
    await db.commit()
    await db.refresh(emisor)

    # Datos del Receptor
    receptor_data = comprobante_data.get("Receptor", {})
    rfc_receptor = receptor_data.get("@Rfc")
    nombre_receptor = receptor_data.get("@Nombre")
    regimen_fiscal_receptor = receptor_data.get("@RegimenFiscalReceptor")
    uso_cfdi = receptor_data.get("@UsoCFDI")
    
    if not rfc_receptor or not nombre_receptor or not regimen_fiscal_receptor or not uso_cfdi:
        return {"error": "El Receptor debe contener RFC, Nombre, Régimen Fiscal y Uso CFDI."}

    # Crear el registro del Receptor
    receptor = CFDReceptor(
        rfc=rfc_receptor,
        nombre=nombre_receptor,
        regimen_fiscal=regimen_fiscal_receptor,
        uso_cfdi=uso_cfdi
    )
    db.add(receptor)
    await db.commit()
    await db.refresh(receptor)

    # Crear el registro del Comprobante
    comprobante = CFDComprobante(
        version=comprobante_data.get("@Version"),
        serie=comprobante_data.get("@Serie"),
        folio=comprobante_data.get("@Folio"),
        fecha=fecha,
        subtotal=float(comprobante_data.get("@SubTotal")),
        descuento=float(comprobante_data.get("@Descuento", 0)),
        moneda=comprobante_data.get("@Moneda"),
        tipo_cambio=float(comprobante_data.get("@TipoCambio", 1)),
        total=float(comprobante_data.get("@Total")),
        tipo_de_comprobante=comprobante_data.get("@TipoDeComprobante"),
        exportacion=comprobante_data.get("@Exportacion"),
        lugar_expedicion=comprobante_data.get("@LugarExpedicion"),
        id_emisor=emisor.id_emisor,
        id_receptor=receptor.id_receptor,
        total_impuestos_trasladados=float(comprobante_data.get("Impuestos", {}).get("@TotalImpuestosTrasladados", 0))
    )
    db.add(comprobante)
    await db.commit()
    await db.refresh(comprobante)

    # Procesar los Conceptos
    conceptos_data = comprobante_data.get("Conceptos", {}).get("Concepto", [])
    if not isinstance(conceptos_data, list):
        conceptos_data = [conceptos_data]

    for concepto_data in conceptos_data:
        concepto = CFDConcepto(
            id_comprobante=comprobante.id_comprobante,
            clave_prod_serv=concepto_data.get("@ClaveProdServ"),
            cantidad=float(concepto_data.get("@Cantidad")),
            clave_unidad=concepto_data.get("@ClaveUnidad"),
            descripcion=concepto_data.get("@Descripcion"),
            valor_unitario=float(concepto_data.get("@ValorUnitario")),
            importe=float(concepto_data.get("@Importe")),
            descuento=float(concepto_data.get("@Descuento", 0)),
            objeto_imp=concepto_data.get("@ObjetoImp")
        )
        db.add(concepto)
        await db.commit()
        await db.refresh(concepto)

        # Procesar impuestos trasladados por concepto
        impuestos_data = concepto_data.get("Impuestos", {}).get("Traslados", {}).get("Traslado", [])
        if not isinstance(impuestos_data, list):
            impuestos_data = [impuestos_data]

        for impuesto_data in impuestos_data:
            impuesto_concepto = CFDImpuestoTrasladadoConcepto(
                id_concepto=concepto.id_concepto,
                base=float(impuesto_data.get("@Base")),
                impuesto=impuesto_data.get("@Impuesto"),
                tipo_factor=impuesto_data.get("@TipoFactor"),
                tasa_o_cuota=float(impuesto_data.get("@TasaOCuota")),
                importe=float(impuesto_data.get("@Importe"))
            )
            db.add(impuesto_concepto)

        await db.commit()

    # Procesar impuestos generales
    impuestos_data = comprobante_data.get("Impuestos", {}).get("Traslados", {}).get("Traslado", [])
    if not isinstance(impuestos_data, list):
        impuestos_data = [impuestos_data]

    for impuesto_data in impuestos_data:
        impuesto_general = CFDImpuestoTrasladadoGeneral(
            id_comprobante=comprobante.id_comprobante,
            base=float(impuesto_data.get("@Base")),
            impuesto=impuesto_data.get("@Impuesto"),
            tipo_factor=impuesto_data.get("@TipoFactor"),
            tasa_o_cuota=float(impuesto_data.get("@TasaOCuota")),
            importe=float(impuesto_data.get("@Importe"))
        )
        db.add(impuesto_general)

    await db.commit()

    return {"mensaje": "Archivo XML procesado correctamente"}

@app.delete("/emisor/{rfc}")
async def eliminar_emisor(rfc: str, db: AsyncSession = Depends(get_db)):
    emisor = await db.execute(text("SELECT id_emisor FROM cfd_emisor WHERE rfc = :rfc"), {"rfc": rfc})
    emisor_id = emisor.scalar()

    if not emisor_id:
        raise HTTPException(status_code=404, detail="Emisor no encontrado")

    await db.execute(text("DELETE FROM cfd_impuesto_trasladado_general WHERE id_comprobante IN (SELECT id_comprobante FROM cfd_comprobante WHERE id_emisor = :emisor_id)"), {"emisor_id": emisor_id})
    await db.execute(text("DELETE FROM cfd_concepto WHERE id_comprobante IN (SELECT id_comprobante FROM cfd_comprobante WHERE id_emisor = :emisor_id)"), {"emisor_id": emisor_id})
    await db.execute(text("DELETE FROM cfd_impuesto_trasladado_concepto WHERE id_concepto IN (SELECT id_concepto FROM cfd_concepto WHERE id_comprobante IN (SELECT id_comprobante FROM cfd_comprobante WHERE id_emisor = :emisor_id))"), {"emisor_id": emisor_id})
    await db.execute(text("DELETE FROM cfd_comprobante WHERE id_emisor = :emisor_id"), {"emisor_id": emisor_id})
    await db.execute(text("DELETE FROM cfd_emisor WHERE id_emisor = :emisor_id"), {"emisor_id": emisor_id})
    await db.commit()

    return {"mensaje": f"Emisor con RFC {rfc} eliminado correctamente"}

@app.get("/estadisticas")
async def obtener_estadisticas(
    fecha_inicio: Optional[date] = Query(None, description="Fecha de inicio (YYYY-MM-DD)"),
    fecha_fin: Optional[date] = Query(None, description="Fecha de fin (YYYY-MM-DD)"),
    year: Optional[int] = Query(None, description="Año específico"),
    month: Optional[int] = Query(None, description="Mes específico (1-12)"),
    day: Optional[int] = Query(None, description="Día específico (1-31)"),
    db: AsyncSession = Depends(get_db)
):
    query = text("""
        SELECT total, fecha 
        FROM cfd_comprobante
        WHERE 1=1
    """)
    params = {}
    
    if fecha_inicio and fecha_fin:
        query = text(str(query) + " AND fecha BETWEEN :fecha_inicio AND :fecha_fin")
        params.update({"fecha_inicio": fecha_inicio, "fecha_fin": fecha_fin})
    elif year is not None:
        if month is not None:
            if day is not None:
                query = text(str(query) + " AND EXTRACT(YEAR FROM fecha) = :year AND EXTRACT(MONTH FROM fecha) = :month AND EXTRACT(DAY FROM fecha) = :day")
                params.update({"year": year, "month": month, "day": day})
            else:
                query = text(str(query) + " AND EXTRACT(YEAR FROM fecha) = :year AND EXTRACT(MONTH FROM fecha) = :month")
                params.update({"year": year, "month": month})
        else:
            query = text(str(query) + " AND EXTRACT(YEAR FROM fecha) = :year")
            params.update({"year": year})
    
    resultados = await db.execute(query, params)
    datos = resultados.fetchall()
    
    if not datos:
        raise HTTPException(status_code=404, detail="No se encontraron datos para los filtros aplicados")
    
    valores = [float(row[0]) for row in datos]
    fechas = [row[1] for row in datos]
    datos_np = np.array(valores)
    moda_result = stats.mode(datos_np, keepdims=False)
    moda = moda_result.mode.tolist()
    if isinstance(moda, (int, float)):
        moda = [moda]
    
    estadisticas = {
        "cantidad_registros": len(valores),
        "media": float(np.mean(datos_np)),
        "mediana": float(np.median(datos_np)),
        "moda": [float(x) for x in moda],
        "varianza": float(np.var(datos_np)),
        "desviacion_estandar": float(np.std(datos_np)),
        "minimo": float(np.min(datos_np)),
        "maximo": float(np.max(datos_np)),
        "rango": float(np.ptp(datos_np)),
        "percentiles": {
            "25": float(np.percentile(datos_np, 25)),
            "50": float(np.percentile(datos_np, 50)),
            "75": float(np.percentile(datos_np, 75))
        }
    }
    
    return {
        "filtros_aplicados": {
            "fecha_inicio": fecha_inicio,
            "fecha_fin": fecha_fin,
            "year": year,
            "month": month,
            "day": day
        },
        "estadisticas": estadisticas,
        "primer_registro": fechas[0].isoformat(),
        "ultimo_registro": fechas[-1].isoformat()
    }


    return await obtener_estadisticas(db=db)

@app.get("/registros")
async def obtener_registros(
    fecha_inicio: Optional[date] = Query(None, description="Fecha de inicio (YYYY-MM-DD)"),
    fecha_fin: Optional[date] = Query(None, description="Fecha de fin (YYYY-MM-DD)"),
    year: Optional[int] = Query(None, description="Año específico"),
    month: Optional[int] = Query(None, description="Mes específico (1-12)"),
    day: Optional[int] = Query(None, description="Día específico (1-31)"),
    limit: int = Query(100, description="Límite de registros"),
    offset: int = Query(0, description="Desplazamiento"),
    db: AsyncSession = Depends(get_db)
):
    query = text("""
        SELECT 
            c.id_comprobante, c.fecha, c.total, c.tipo_de_comprobante,
            e.rfc as rfc_emisor, e.nombre as nombre_emisor,
            r.rfc as rfc_receptor, r.nombre as nombre_receptor
        FROM cfd_comprobante c
        JOIN cfd_emisor e ON c.id_emisor = e.id_emisor
        JOIN cfd_receptor r ON c.id_receptor = r.id_receptor
        WHERE 1=1
    """)
    params = {}
    
    if fecha_inicio and fecha_fin:
        query = text(str(query) + " AND c.fecha BETWEEN :fecha_inicio AND :fecha_fin")
        params.update({"fecha_inicio": fecha_inicio, "fecha_fin": fecha_fin})
    elif year is not None:
        if month is not None:
            if day is not None:
                query = text(str(query) + " AND EXTRACT(YEAR FROM c.fecha) = :year AND EXTRACT(MONTH FROM c.fecha) = :month AND EXTRACT(DAY FROM c.fecha) = :day")
                params.update({"year": year, "month": month, "day": day})
            else:
                query = text(str(query) + " AND EXTRACT(YEAR FROM c.fecha) = :year AND EXTRACT(MONTH FROM c.fecha) = :month")
                params.update({"year": year, "month": month})
        else:
            query = text(str(query) + " AND EXTRACT(YEAR FROM c.fecha) = :year")
            params.update({"year": year})
    
    query = text(str(query) + " ORDER BY c.fecha DESC LIMIT :limit OFFSET :offset")
    params.update({"limit": limit, "offset": offset})
    
    resultados = await db.execute(query, params)
    registros = resultados.fetchall()
    
    if not registros:
        raise HTTPException(status_code=404, detail="No se encontraron registros para los filtros aplicados")
    
    registros_formateados = []
    for row in registros:
        registros_formateados.append({
            "id_comprobante": row[0],
            "fecha": row[1].isoformat(),
            "total": float(row[2]),
            "tipo_comprobante": row[3],
            "emisor": {
                "rfc": row[4],
                "nombre": row[5]
            },
            "receptor": {
                "rfc": row[6],
                "nombre": row[7]
            }
        })
    
    return {
        "filtros_aplicados": {
            "fecha_inicio": fecha_inicio,
            "fecha_fin": fecha_fin,
            "year": year,
            "month": month,
            "day": day,
            "limit": limit,
            "offset": offset
        },
        "total_registros": len(registros_formateados),
        "registros": registros_formateados
    }

@app.get("/registros/dia/{year}/{month}/{day}")
async def registros_por_dia(
    year: Annotated[int, conint(ge=2000, le=2100)],
    month: Annotated[int, conint(ge=1, le=12)],
    day: Annotated[int, conint(ge=1, le=31)],
    limit: int = Query(100, description="Límite de registros"),
    offset: int = Query(0, description="Desplazamiento"),
    db: AsyncSession = Depends(get_db)
):
    return await obtener_registros(year=year, month=month, day=day, limit=limit, offset=offset, db=db)

@app.get("/registros/mes/{year}/{month}")
async def registros_por_mes(
    year: Annotated[int, conint(ge=2000, le=2100)],
    month: Annotated[int, conint(ge=1, le=12)],
    limit: int = Query(100, description="Límite de registros"),
    offset: int = Query(0, description="Desplazamiento"),
    db: AsyncSession = Depends(get_db)
):
    return await obtener_registros(year=year, month=month, limit=limit, offset=offset, db=db)

@app.get("/registros/ano/{year}")
async def registros_por_ano(
    year: Annotated[int, conint(ge=2000, le=2100)],
    limit: int = Query(100, description="Límite de registros"),
    offset: int = Query(0, description="Desplazamiento"),
    db: AsyncSession = Depends(get_db)
):
    return await obtener_registros(year=year, limit=limit, offset=offset, db=db)

@app.get("/registros/todos")
async def registros_todos(
    limit: int = Query(100, description="Límite de registros"),
    offset: int = Query(0, description="Desplazamiento"),
    db: AsyncSession = Depends(get_db)
):
    return await obtener_registros(limit=limit, offset=offset, db=db)

@app.get("/estadisticas/tipo-comprobante")
async def estadisticas_por_tipo_comprobante(
    tipo: str = Query(..., description="Tipo de comprobante (I, E, etc.)"),
    db: AsyncSession = Depends(get_db)
):
    query = text("SELECT total FROM cfd_comprobante WHERE tipo_de_comprobante = :tipo")
    resultados = await db.execute(query, {"tipo": tipo})
    valores = [float(row[0]) for row in resultados.fetchall()]
    
    if not valores:
        raise HTTPException(status_code=404, detail=f"No se encontraron comprobantes del tipo {tipo}")
    
    datos_np = np.array(valores)
    
    return {
        "tipo_comprobante": tipo,
        "cantidad": len(valores),
        "media": float(np.mean(datos_np)),
        "mediana": float(np.median(datos_np)),
        "desviacion_estandar": float(np.std(datos_np))
    }

@app.get("/estadisticas/emisor/{rfc}")
async def estadisticas_por_emisor(
    rfc: str,
    db: AsyncSession = Depends(get_db)
):
    query = text("""
        SELECT c.total 
        FROM cfd_comprobante c
        JOIN cfd_emisor e ON c.id_emisor = e.id_emisor
        WHERE e.rfc = :rfc
    """)
    resultados = await db.execute(query, {"rfc": rfc})
    valores = [float(row[0]) for row in resultados.fetchall()]
    
    if not valores:
        raise HTTPException(status_code=404, detail=f"No se encontraron comprobantes para el emisor con RFC {rfc}")
    
    datos_np = np.array(valores)
    
    return {
        "rfc_emisor": rfc,
        "cantidad": len(valores),
        "total_general": float(np.sum(datos_np)),
        "promedio": float(np.mean(datos_np))
    }

@app.post("/analisis_inferencial")
async def analisis_inferencial(db: AsyncSession = Depends(get_db)):
    grupo1_result = await db.execute(text("SELECT total FROM cfd_comprobante WHERE tipo_de_comprobante = 'I'"))
    grupo2_result = await db.execute(text("SELECT total FROM cfd_comprobante WHERE tipo_de_comprobante = 'E'"))
    
    grupo1 = [float(row[0]) for row in grupo1_result.fetchall()]
    grupo2 = [float(row[0]) for row in grupo2_result.fetchall()]

    if not grupo1 or not grupo2:
        return {"error": "No se encontraron suficientes datos en la base de datos."}

    t_test = stats.ttest_ind(grupo1, grupo2, equal_var=False)
    
    return {
        "prueba_t": {
            "statistica": t_test.statistic,
            "p_valor": t_test.pvalue
        }
    }

# 🔮 Análisis Predictivo con Regresión Lineal (existente)
@app.post("/analisis_predictivo")
async def analisis_predictivo(db: AsyncSession = Depends(get_db)):
    datos_result = await db.execute(text("SELECT fecha, total FROM cfd_comprobante ORDER BY fecha ASC"))
    datos = [(row[0], float(row[1])) for row in datos_result.fetchall()]

    if not datos:
        return {"error": "No se encontraron datos suficientes en la base de datos."}

    fechas = np.array([dato[0].timestamp() for dato in datos]).reshape(-1, 1)
    valores = np.array([dato[1] for dato in datos])

    modelo = LinearRegression()
    modelo.fit(fechas, valores)
    predicciones = modelo.predict(fechas).tolist()

    return {
        "coeficiente": modelo.coef_.tolist(),
        "intercepto": modelo.intercept_.tolist(),
        "predicciones": predicciones
    }