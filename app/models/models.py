from sqlalchemy import Column, Integer, String, Numeric, ForeignKey, TIMESTAMP
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

# 📌 Modelo para la tabla de Emisor
class CFDEmisor(Base):
    __tablename__ = "cfd_emisor"
    
    id_emisor = Column(Integer, primary_key=True, autoincrement=True)
    rfc = Column(String(15), nullable=False)
    nombre = Column(String(255), nullable=False)
    regimen_fiscal = Column(String(5), nullable=False)

# 📌 Modelo para la tabla de Receptor
class CFDReceptor(Base):
    __tablename__ = "cfd_receptor"

    id_receptor = Column(Integer, primary_key=True, autoincrement=True)
    rfc = Column(String(15), nullable=False)
    nombre = Column(String(255), nullable=False)
    domicilio_fiscal = Column(String(10))
    regimen_fiscal = Column(String(5), nullable=False)
    uso_cfdi = Column(String(5), nullable=False)

# 📌 Modelo para la tabla de Comprobante
class CFDComprobante(Base):
    __tablename__ = "cfd_comprobante"

    id_comprobante = Column(Integer, primary_key=True, autoincrement=True)
    version = Column(String(10), nullable=False)
    serie = Column(String(50))
    folio = Column(String(50))
    fecha = Column(TIMESTAMP, nullable=False)
    subtotal = Column(Numeric(19, 4), nullable=False)
    descuento = Column(Numeric(19, 4))
    moneda = Column(String(10), nullable=False)
    tipo_cambio = Column(Numeric(19, 6))
    total = Column(Numeric(19, 4), nullable=False)
    tipo_de_comprobante = Column(String(1), nullable=False)
    exportacion = Column(String(2))
    lugar_expedicion = Column(String(10))
    id_emisor = Column(Integer, ForeignKey("cfd_emisor.id_emisor"), nullable=False)
    id_receptor = Column(Integer, ForeignKey("cfd_receptor.id_receptor"), nullable=False)
    total_impuestos_trasladados = Column(Numeric(19, 4))

# 📌 Modelo para la tabla de Conceptos
class CFDConcepto(Base):
    __tablename__ = "cfd_concepto"

    id_concepto = Column(Integer, primary_key=True, autoincrement=True)
    id_comprobante = Column(Integer, ForeignKey("cfd_comprobante.id_comprobante"), nullable=False)
    clave_prod_serv = Column(String(10), nullable=False)
    cantidad = Column(Numeric(19, 4), nullable=False)
    clave_unidad = Column(String(10), nullable=False)
    descripcion = Column(String, nullable=False)
    valor_unitario = Column(Numeric(19, 4), nullable=False)
    importe = Column(Numeric(19, 4), nullable=False)
    descuento = Column(Numeric(19, 4))
    objeto_imp = Column(String(2))

# 📌 Modelo para la tabla de Impuestos Trasladados por Concepto
class CFDImpuestoTrasladadoConcepto(Base):
    __tablename__ = "cfd_impuesto_trasladado_concepto"

    id_impuesto_trasladado_concepto = Column(Integer, primary_key=True, autoincrement=True)
    id_concepto = Column(Integer, ForeignKey("cfd_concepto.id_concepto"), nullable=False)
    base = Column(Numeric(19, 4), nullable=False)
    impuesto = Column(String(3), nullable=False)
    tipo_factor = Column(String(10), nullable=False)
    tasa_o_cuota = Column(Numeric(19, 6))
    importe = Column(Numeric(19, 4))

# 📌 Modelo para la tabla de Impuestos Trasladados Generales
class CFDImpuestoTrasladadoGeneral(Base):
    __tablename__ = "cfd_impuesto_trasladado_general"

    id_impuesto_trasladado_general = Column(Integer, primary_key=True, autoincrement=True)
    id_comprobante = Column(Integer, ForeignKey("cfd_comprobante.id_comprobante"), nullable=False)
    base = Column(Numeric(19, 4), nullable=False)
    impuesto = Column(String(3), nullable=False)
    tipo_factor = Column(String(10), nullable=False)
    tasa_o_cuota = Column(Numeric(19, 6))
    importe = Column(Numeric(19, 4))