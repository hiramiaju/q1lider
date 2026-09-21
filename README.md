# +Q1LÍDER — versión Python + Flask

Conversión de la plataforma v2.2 de React/Vite + Express/TypeScript a un proyecto **Python + Flask**. Esta versión no necesita Node.js, npm, Vite, React, Express, Supabase ni servicios de Google.

## Qué conserva

- Login privado y roles: Administrador, Coordinador y Participante.
- Calendario principal con actividades oficiales y personales.
- Privacidad de actividades personales.
- Mis tareas.
- Actividades oficiales.
- Biblioteca de materiales con subida de archivos de hasta 25 MB.
- Comentarios **públicos** y **personales** en materiales.
- Mi espacio y notas privadas.
- Módulo de asistencia por fecha/actividad.
- Estados: Presente, Falta, Retardo y Justificada.
- Resumen acumulado de faltas y porcentaje de asistencia por alumno.
- Administración de usuarios y activación/desactivación.
- Notificaciones internas.
- Búsqueda global.
- Diseño responsive para desktop, tablet y celular.
- Base local JSON y carpeta local de uploads.

## Requisitos

- Python 3.11 o superior recomendado.
- Windows, macOS o Linux.

## Instalación en Windows

Abre PowerShell dentro de la carpeta del proyecto:

```powershell
cd D:\q1lider-flask
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

Abre:

```text
http://localhost:5000
```

### Usuario demo

```text
Correo: admin@q1lider.local
Contraseña: Q1Lider2026!
```

Los tres participantes demo usan la contraseña:

```text
Demo2026!
```

## Arranque rápido después de instalar

En Windows puedes ejecutar:

```powershell
.\.venv\Scripts\Activate.ps1
python app.py
```

También puedes usar `start.bat` si el entorno virtual ya está activo.

## Dónde se guardan los datos

```text
data/db.json
uploads/
```

El JSON se crea automáticamente la primera vez. Si no hay usuarios, Flask crea el administrador y datos demo automáticamente. **No existe `npm run seed`.**

## Migrar los datos de tu versión React/Express

La versión Flask entiende los hashes bcrypt y el formato JSON de la versión anterior. Si tu proyecto anterior está, por ejemplo, en `D:\q1lider-simple`, ejecuta:

```powershell
python migrate_node_data.py "D:\q1lider-simple"
```

El script:

1. Busca `D:\q1lider-simple\server\data\db.json`.
2. Crea backup del JSON actual de Flask.
3. Copia usuarios, actividades, tareas, materiales, asistencia y comentarios.
4. Copia también `server\uploads` si existe.

Después:

```powershell
python app.py
```

También puedes hacerlo manualmente copiando:

```text
VERSIÓN NODE/server/data/db.json  ->  VERSIÓN FLASK/data/db.json
VERSIÓN NODE/server/uploads/*     ->  VERSIÓN FLASK/uploads/*
```

## Reiniciar los datos demo

```powershell
python reset.py
```

Esto elimina los datos locales actuales y vuelve a crear el acceso demo.

## Responsive

- Desktop: sidebar completo y calendario mensual.
- Tablet: navegación compacta y layouts reacomodados.
- Celular: drawer lateral + navegación inferior, agenda móvil, formularios de una columna y modales tipo bottom sheet.
- Asistencia: controles grandes para marcar la lista desde teléfono.
- Administración: tabla de usuarios convertida en tarjetas en móvil.

## Estructura

```text
q1lider-flask/
├─ app.py
├─ db.py
├─ reset.py
├─ migrate_node_data.py
├─ requirements.txt
├─ Procfile
├─ data/
│  └─ db.json              # se crea automáticamente
├─ uploads/
├─ static/
│  ├─ css/styles.css
│  └─ js/app.js
└─ templates/
   ├─ base.html
   ├─ login.html
   ├─ calendar.html
   ├─ tasks.html
   ├─ activities.html
   ├─ material.html
   ├─ space.html
   ├─ attendance.html
   ├─ admin.html
   ├─ notifications.html
   └─ search.html
```

## Producción

Para producción cambia la clave de sesión con una variable de entorno:

```powershell
$env:Q1LIDER_SECRET="una-clave-larga-y-unica"
```

En Linux/macOS:

```bash
export Q1LIDER_SECRET="una-clave-larga-y-unica"
```

Con Gunicorn:

```bash
gunicorn app:app --bind 0.0.0.0:5000
```

El `Procfile` ya viene incluido para hosts compatibles.

## Nota sobre la validación de esta entrega

Los archivos Python fueron validados con `compileall` y todas las plantillas Jinja fueron compiladas sintácticamente. En el entorno donde se generó el ZIP no había acceso de red para descargar Flask mediante pip, por lo que no fue posible ejecutar el servidor Flask completo allí. El proyecto incluye `requirements.txt` para instalar las dependencias normalmente en tu equipo.
