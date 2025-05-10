# Usar la imagen base de Python
FROM python:3.11

# Configurar variable de entorno para evitar buffering en logs
ENV PYTHONUNBUFFERED=1

# Definir el directorio de trabajo
WORKDIR /app

# Copiar solo el archivo de requerimientos primero
COPY requirements.txt ./

# Instalar dependencias
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el resto de la aplicación
COPY . .

# Exponer el puerto de FastAPI
EXPOSE 8000

# Ejecutar la aplicación
CMD ["python", "-m", "uvicorn", "app.app:app", "--host", "0.0.0.0", "--port", "8000"]