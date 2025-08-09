# 🏠 Setup Sin Docker Desktop

Si no puedes usar Docker Desktop, aquí tienes **3 alternativas** para probar el proyecto:

## 🚀 Opción 1: Versión Simplificada (Más Rápida)

**Solo necesitas Python** - Sin bases de datos externas

```bash
# 1. Instala las dependencias mínimas
pip install fastapi uvicorn sqlite3 pydantic

# 2. Ejecuta la versión simplificada
python app_simple.py
```

**¡Listo!** La API estará en http://localhost:8000/docs

### ✨ Lo que incluye:
- ✅ Todos los endpoints principales
- ✅ Base de datos SQLite (sin instalación)
- ✅ Datos de ejemplo precargados
- ✅ Documentación Swagger completa

---

## 🛠️ Opción 2: Setup Local Completo

**Para la experiencia completa** con PostgreSQL y Redis

```bash
# 1. Ejecuta el setup automático
python setup_local.py

# 2. Instala PostgreSQL manualmente:
# Windows: https://www.postgresql.org/download/windows/
# Mac: brew install postgresql
# Ubuntu: sudo apt install postgresql postgresql-contrib

# 3. Crea la base de datos
# Ver instrucciones detalladas en LOCAL_SETUP.md

# 4. Inicia la aplicación
# Windows: start_local.bat
# Linux/Mac: ./start_local.sh
```

---

## 🧪 Opción 3: Solo Testing (Sin Servicios)

**Para ver el código funcionando** sin instalar nada

```bash
# Ejecuta las pruebas de funcionalidad
python test_without_services.py
```

### 📋 Lo que verás:
- ✅ Validación de modelos Pydantic
- ✅ Lógica de scraping (sin HTTP)
- ✅ Estructura de la API
- ✅ Demostración de características
- ✅ Ejemplos de endpoints

---

## 🌩️ Opción 4: Cloud Deploy (Recomendada)

### Railway (Gratis, Fácil)

1. Fork el repositorio en GitHub
2. Ve a [railway.app](https://railway.app) 
3. "Deploy from GitHub" → Selecciona tu fork
4. Railway detectará automáticamente el proyecto Python
5. La API estará disponible en una URL pública

### Heroku

```bash
# 1. Instala Heroku CLI
# 2. Crea Procfile
echo "web: uvicorn app.main:app --host=0.0.0.0 --port=\$PORT --app-dir backend" > Procfile

# 3. Deploy
git add .
git commit -m "Deploy to Heroku"
heroku create tu-auction-app
heroku addons:create heroku-postgresql:mini
git push heroku main
```

### Render, Fly.io, DigitalOcean App Platform
Todos soportan despliegue automático desde GitHub.

---

## 📊 Comparación de Opciones

| Opción | Tiempo Setup | Funcionalidad | Requisitos |
|---------|--------------|---------------|------------|
| Simplificada | 2 min | 80% | Solo Python |
| Local Completa | 15-30 min | 100% | Python + PostgreSQL |
| Solo Testing | 1 min | Demo | Solo Python |
| Cloud Deploy | 5-10 min | 100% | Cuenta GitHub |

---

## 🎯 ¿Cuál elegir?

### Para **probar rápidamente**:
```bash
python app_simple.py
```

### Para **desarrollo completo**:
```bash
python setup_local.py
```

### Para **ver el código**:
```bash
python test_without_services.py
```

### Para **uso en producción**:
**Deploy en Railway/Heroku**

---

## 🔧 Troubleshooting

### Error: "No module named 'fastapi'"
```bash
pip install fastapi uvicorn pydantic
```

### Error: "Port 8000 already in use"
```bash
# Cambia el puerto en el script:
uvicorn.run(app, host="0.0.0.0", port=8001)
```

### Error: Database connection
```bash
# Usa la versión simplificada con SQLite:
python app_simple.py
```

---

## 📞 Soporte

Si tienes problemas:

1. **Revisa** `test_without_services.py` para verificar que el código funciona
2. **Prueba** `app_simple.py` para una versión que siempre funciona  
3. **Consulta** los logs para errores específicos
4. **Considera** el deploy en cloud si el setup local es problemático

---

**¡El proyecto está 100% funcional sin Docker!** 🎉