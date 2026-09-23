# +Q1LÍDER — Flask Campus Académico v5.2

Versión en **Python + Flask + Jinja + CSS/JavaScript + JSON local**. No usa Next.js, React, Vite, Express, Supabase ni servicios de Google.

## Cambios principales de v5

### Contenido del módulo en cuadrícula
Cada módulo separa visualmente el material en tarjetas independientes y con fondos de color:

- Plan del módulo.
- Guía de estudio complementaria.
- Enunciado de caso práctico.
- Enunciado práctico para proyecto.
- Master class / clase grabada.
- Recurso complementario.

Cada recurso mantiene sus **comentarios públicos** y **comentarios personales (solo yo)**.

### Gestión real del módulo para Docente/Admin
Desde la misma pantalla del módulo un Docente o Administrador puede:

- Editar título, subtítulo y descripción del módulo.
- Subir documentos directamente al módulo.
- Agregar enlaces o videos externos.
- Elegir a qué apartado pertenece el contenido.
- Editar un material publicado.
- Reemplazar/agregar el archivo de un material.
- Cambiar de sección el material.
- Eliminar contenido.
- Administrar evaluaciones.

### Evaluaciones de un solo intento
Todas las evaluaciones son de **un solo intento para el alumno**.

1. El alumno abre la evaluación.
2. Contesta y presiona **Enviar evaluación**.
3. Se registra la calificación y se cierra el intento.
4. El alumno regresa a la sección de evaluaciones del módulo.
5. La tarjeta muestra **Evaluación enviada** y la calificación.
6. Ya no puede volver a abrir las preguntas.
7. Puede consultar una pantalla de resultado, pero no modificar sus respuestas.

El examen final conserva la regla adicional: **la encuesta del módulo debe completarse primero**.

### Docentes pueden editar evaluaciones
En **Exámenes**, Docente/Admin puede:

- Crear evaluaciones.
- Editar título y descripción.
- Cambiar módulo.
- Cambiar entre autoevaluación y examen final.
- Editar preguntas y respuestas correctas.
- Modificar el porcentaje que aporta a la calificación.
- Eliminar la evaluación.

Los intentos ya enviados por los alumnos permanecen registrados y cerrados.

### Actividades oficiales editables con imagen
En **Actividades**, Docente/Admin puede:

- Crear una actividad global +Q1LÍDER.
- Editar título y descripción.
- Cambiar fecha, horario y lugar.
- Cambiar prioridad y estado.
- Subir/reemplazar/quitar una imagen de portada.
- Eliminar actividades.

Los alumnos **no pueden crear actividades globales**. En su calendario solo pueden crear actividades personales. Esta restricción existe tanto en la interfaz como en el backend Flask.

## Funciones académicas incluidas

### Programa de 12 semanas / 6 módulos

- Módulo 1: semanas 1–2
- Módulo 2: semanas 3–4
- Módulo 3: semanas 5–6
- Módulo 4: semanas 7–8
- Módulo 5: semanas 9–10
- Módulo 6: semanas 11–12

Cada módulo integra:

1. Plan del módulo.
2. Guía de estudio complementaria.
3. Enunciado de caso práctico.
4. Entrega de caso práctico.
5. Foro de dudas.
6. Autoevaluaciones.
7. Enunciados prácticos para proyectos.
8. Master class / clases grabadas.
9. Encuesta de cierre.
10. Examen final.

### Asistencia y bloqueo

- Presente.
- Falta.
- Retardo.
- Justificada.
- Lista relacionada con módulo y semana.
- **3 faltas durante las 12 semanas bloquean automáticamente al alumno.**
- Si un Docente/Admin corrige la asistencia y el alumno baja de 3 faltas, el acceso se reactiva automáticamente.

### Kárdex y calificaciones

El Kárdex muestra por alumno:

- Los seis módulos.
- Calificación por módulo.
- Faltas.
- Estado de encuesta.
- Examen final.
- Promedio general.
- Estado de acceso.

Docente/Admin puede definir actividades calificables y su porcentaje. Los resultados de evaluaciones vinculadas se registran automáticamente.

### Administración

Separada en:

- Alumnos.
- Docentes.
- Admin.

## Instalación en Windows

```powershell
cd D:\q1lider-flask-v5.2
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

Abre:

```text
http://localhost:5000
```

## Accesos demo

**Administrador**

```text
admin@q1lider.local
Q1Lider2026!
```

**Docente**

```text
docente@q1lider.local
Docente2026!
```

**Alumno**

```text
ana@q1lider.local
Demo2026!
```

## Actualizar desde Flask v4 sin perder datos

Antes de reemplazar la versión anterior haz copia de:

```text
data/db.json
uploads/
```

Después puedes sustituir el resto del proyecto con v5 y volver a colocar esas dos rutas. La estructura JSON continúa siendo compatible.

## Datos

```text
data/db.json
uploads/
```

No existe `npm install`, `npm run seed` ni configuración de Supabase.

## Validación de esta entrega

- Sintaxis Python validada con `py_compile`.
- Todas las plantillas Jinja parseadas sin errores.
- JavaScript validado con `node --check`.
- Referencias `url_for(...)` comparadas contra endpoints Flask.
- La instalación de Flask no está disponible en el entorno de generación, por lo que el arranque HTTP completo debe ejecutarse en tu PC después de `pip install -r requirements.txt`.


## Novedad v5.1 — Mi espacio editable por usuario

- Cada usuario puede crear, editar y eliminar sus **notas rápidas privadas**.
- Las notas se validan por propietario en Flask: otro usuario no puede editarlas ni borrarlas aunque manipule una URL.
- Cada usuario puede crear, editar y eliminar sus **actividades personales** directamente desde “Mi espacio”.
- Las actividades oficiales pueden verse desde “Mi espacio”, pero un participante no puede modificarlas.
- La edición de actividades personales reutiliza la protección del backend por propietario.
- La pantalla “Mi espacio” fue rediseñada con tarjetas, indicadores de privacidad y controles responsivos.

## Novedad v5.2 — Identidad oficial + tema por usuario

- Se integró `+q1lider.jpeg` como **logo principal** de la plataforma, incluyendo login, navegación y favicon.
- Se incluyeron las seis variantes institucionales del Instituto de la Juventud: Azul Corto/Largo, Blanco Corto/Largo y Color Corto/Largo.
- La interfaz selecciona automáticamente variantes adecuadas para fondo claro, oscuro, escritorio y móvil.
- Se agregó selector de **modo claro / modo oscuro**.
- La preferencia se guarda en `data/db.json` dentro del registro de cada usuario (`theme`), por lo que al volver a iniciar sesión recupera el último modo que utilizó.
- Las bases de datos de versiones anteriores son compatibles: a usuarios existentes se les asigna modo claro la primera vez y después se conserva su elección.
- La pantalla de inicio de sesión ya no muestra correos, contraseñas ni el bloque de accesos de demostración, y los campos aparecen vacíos.
- El modo oscuro se aplica a navegación, calendario, módulos, materiales, comentarios, actividades, administración, Kárdex, asistencia, evaluaciones, modales y Mi espacio.

## v5.4 · Usuarios +Q1 y padrón 2026

Esta versión incorpora el padrón limpio entregado en `+q1lider.xlsx`.

- Se detectaron **56 registros únicos** válidos.
- El sistema asigna un usuario con el formato `NombreApellido+q1` (sin acentos ni espacios).
- El alumno puede iniciar sesión con **correo o nombre de usuario**.
- Las cuentas cargadas desde el padrón usan una contraseña temporal individual y obligan a cambiarla en el primer acceso.
- Las contraseñas temporales se entregan en el archivo separado `+q1lider_registros_acomodados.xlsx`, hoja **Credenciales**. No se guardan en texto plano dentro del proyecto.
- Si copias un `data/db.json` anterior, el arranque agrega solamente los alumnos faltantes y conserva actividades, calificaciones, asistencia y demás información existente.
- Administración ahora incluye búsqueda por nombre, usuario, correo o teléfono, vista rápida de perfil y botón para copiar el nombre de usuario.

### Formato de usuario

Ejemplo:

```text
Miguel Lomeli → MiguelLomeli+q1
```

Cuando el nombre tiene varias palabras se utiliza el **primer nombre + primer apellido estimado** para mantener una regla cercana al formato habitual mexicano. Se eliminan acentos y espacios para facilitar el acceso.
