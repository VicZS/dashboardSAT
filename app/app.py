from fastapi import FastAPI, Depends, File, UploadFile
import xmltodict
import numpy as np
from scipy import stats
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.database import get_db
from app.models.models import CFDComprobante, CFDEmisor, CFDReceptor, CFDConcepto, CFDImpuestoTrasladadoConcepto, CFDImpuestoTrasladadoGeneral
from datetime import datetime

from fastapi import FastAPI
from app.routes.auth import auth_router

from app.security.jwt_handler import get_password_hash, verify_password, create_access_token

app = FastAPI(title="Mi API", version="1.0", openapi_prefix="/api/")

app.include_router(auth_router, prefix="/auth", tags=["Authentication"])

@app.post("/procesar_xml")
async def procesar_xml(file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
    xml_content = await file.read()  # Leer archivo XML
    xml_str = xml_content.decode("utf-8")  # Convertir a texto UTF-8
    
    # Eliminar prefijos "cfdi:" para facilitar el procesamiento del XML
    xml_str = xml_str.replace("cfdi:", "")  

    # Convertir XML a diccionario
    data_dict = xmltodict.parse(xml_str)

    # Extraer datos del Comprobante
    comprobante_data = data_dict.get("Comprobante", {})

    # Validación previa
    if not comprobante_data:
        return {"error": "No se pudo procesar el comprobante. Verifica la estructura del XML."}

    # Extraer y convertir la fecha
    fecha_str = comprobante_data.get("@Fecha")
    if fecha_str:
        try:
            fecha = datetime.strptime(fecha_str, "%Y-%m-%dT%H:%M:%S")
        except ValueError:
            return {"error": "Formato de fecha incorrecto en el XML."}
    else:
        return {"error": "El campo Fecha es obligatorio."}

    # Extraer datos del Emisor
    emisor_data = comprobante_data.get("Emisor", {})
    rfc_emisor = emisor_data.get("@Rfc")
    nombre_emisor = emisor_data.get("@Nombre")
    regimen_fiscal_emisor = emisor_data.get("@RegimenFiscal")

    if not rfc_emisor or not nombre_emisor or not regimen_fiscal_emisor:
        return {"error": "El Emisor debe contener RFC, Nombre y Régimen Fiscal."}

    # Insertar Emisor en PostgreSQL
    emisor = CFDEmisor(rfc=rfc_emisor, nombre=nombre_emisor, regimen_fiscal=regimen_fiscal_emisor)
    db.add(emisor)
    await db.commit()
    await db.refresh(emisor)

    # Extraer datos del Receptor
    receptor_data = comprobante_data.get("Receptor", {})
    rfc_receptor = receptor_data.get("@Rfc")
    nombre_receptor = receptor_data.get("@Nombre")
    domicilio_fiscal_receptor = receptor_data.get("@DomicilioFiscalReceptor")
    regimen_fiscal_receptor = receptor_data.get("@RegimenFiscalReceptor")
    uso_cfdi = receptor_data.get("@UsoCFDI")

    if not rfc_receptor or not nombre_receptor or not regimen_fiscal_receptor or not uso_cfdi:
        return {"error": "El Receptor debe contener RFC, Nombre, Régimen Fiscal y UsoCFDI."}

    # Insertar Receptor en PostgreSQL
    receptor = CFDReceptor(rfc=rfc_receptor, nombre=nombre_receptor, domicilio_fiscal=domicilio_fiscal_receptor,
                           regimen_fiscal=receptor_data.get("@RegimenFiscalReceptor"), uso_cfdi=uso_cfdi)
    db.add(receptor)
    await db.commit()
    await db.refresh(receptor)

    # Extraer datos del comprobante
    moneda = comprobante_data.get("@Moneda")
    tipo_cambio = float(comprobante_data.get("@TipoCambio", "1.0"))  
    tipo_de_comprobante = comprobante_data.get("@TipoDeComprobante")
    subtotal = float(comprobante_data.get("@SubTotal", "0.0"))  
    total = float(comprobante_data.get("@Total", "0.0"))  
    descuento = float(comprobante_data.get("@Descuento", "0.0"))

    # Insertar comprobante en PostgreSQL
    comprobante = CFDComprobante(
        version=comprobante_data.get("@Version", "4.0"),
        serie=comprobante_data.get("@Serie", "A"),
        folio=comprobante_data.get("@Folio", "000001"),
        fecha=fecha,
        subtotal=subtotal,
        descuento=descuento,
        moneda=moneda,
        tipo_cambio=tipo_cambio,
        total=total,
        tipo_de_comprobante=tipo_de_comprobante,
        id_emisor=emisor.id_emisor,
        id_receptor=receptor.id_receptor
    )
    db.add(comprobante)
    await db.commit()
    await db.refresh(comprobante)

    return {"mensaje": "Archivo XML procesado correctamente", "nombre_archivo": file.filename}

@app.post("/analizar_datos")
async def analizar_datos(datos: dict):
    valores = datos.get("valores", [])
    if not isinstance(valores, list) or not all(isinstance(x, (int, float)) for x in valores):
        return {"error": "Debes enviar una lista de números válidos."}

    datos_np = np.array(valores)
    
    resultado = {
        "media": np.mean(datos_np),
        "mediana": np.median(datos_np),
        "moda": stats.mode(datos_np, keepdims=False).mode.tolist(),
        "varianza": np.var(datos_np),
        "desviacion_estandar": np.std(datos_np)
    }

    return {"estadisticas": resultado}