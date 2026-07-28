## 1. Esquema y configuración

- [x] 1.1 Añadir migración Alembic que amplíe `users` con `password_hash` opcional e `is_admin` con valor por defecto falso, sin alterar el comportamiento de los usuarios existentes.
- [x] 1.2 Añadir en la misma migración la tabla `web_sessions` con hash del testigo, vencimiento por inactividad, vencimiento absoluto, enlace de rotación y marca de revocación.
- [x] 1.3 Actualizar los modelos declarativos de SQLAlchemy para reflejar el esquema, sin crear tablas desde la aplicación.
- [x] 1.4 Añadir la configuración validada del ámbito web: origen permitido, duración de la ventana de inactividad, tope absoluto, umbral de rotación y parámetros de derivación de clave.
- [x] 1.5 Añadir la dependencia de Argon2id y fijarla en el lockfile.

## 2. Contraseñas e identidad

- [x] 2.1 Implementar derivación y verificación de contraseña con Argon2id, aislada del `hash_token` existente para testigos aleatorios.
- [x] 2.2 Extender el repositorio de usuarios con asignación de contraseña, concesión de administración y búsqueda por correo para autenticación.
- [x] 2.3 Garantizar que la verificación de credenciales tarde lo mismo con correo inexistente que con contraseña incorrecta.
- [x] 2.4 Añadir pruebas unitarias de derivación, verificación y ausencia de distinción entre los dos modos de fallo.

## 3. Sesiones web

- [x] 3.1 Implementar el repositorio de sesiones web sobre `SessionProvider.admin()`, coherente con el trato que ya reciben usuarios y API keys.
- [x] 3.2 Implementar la creación de sesión con testigo aleatorio, persistencia únicamente del hash y cálculo de ambos vencimientos.
- [x] 3.3 Implementar la resolución de sesión que rechaza testigos caducados por inactividad, caducados en absoluto, revocados o desconocidos.
- [x] 3.4 Implementar la rotación al cruzar el umbral de la ventana de inactividad, evitando escribir en cada petición.
- [x] 3.5 Implementar la detección de reutilización de un testigo ya rotado y la revocación de la cadena completa.
- [x] 3.6 Implementar el cierre de sesión con invalidación en servidor.
- [x] 3.7 Añadir pruebas unitarias con reloj controlado para renovación, ambos vencimientos, umbral de rotación y reutilización de testigo.

## 4. Superficie HTTP

- [x] 4.1 Crear el router `/api/v1` y montarlo junto a los endpoints operativos existentes, sin tocar el mount de `/mcp`.
- [x] 4.2 Implementar inicio de sesión, cierre de sesión y consulta de identidad autenticada.
- [x] 4.3 Emitir la cookie de sesión como `HttpOnly`, `Secure`, `SameSite=Lax`, sin atributo `Domain` y con `Path` restringido a `/api/v1`.
- [x] 4.4 Implementar la dependencia de autenticación web que resuelve la sesión, aplica la rotación y expone la identidad a los endpoints.
- [x] 4.5 Aplicar la política de origen cruzado con credenciales únicamente a las rutas de `/api/v1`, con el origen del sitio declarado de forma exacta.
- [x] 4.6 Verificar que la validación de arranque sigue garantizando que MCP no expone nada distinto de herramientas.

## 5. Administración desde el CLI

- [x] 5.1 Añadir `recallum-admin set-password` con lectura interactiva de la contraseña, sin tomarla de un argumento.
- [x] 5.2 Añadir `recallum-admin grant-admin` y su operación inversa.
- [x] 5.3 Hacer que ambos comandos fallen de forma explícita ante un correo inexistente, sin crear el usuario.
- [x] 5.4 Añadir pruebas de los comandos nuevos.

## 6. Verificación de aislamiento

- [x] 6.1 Añadir prueba de integración que confirme que una sesión web no autoriza llamadas a herramientas MCP.
- [x] 6.2 Añadir prueba de integración que confirme que una API key no autentica peticiones de la API web.
- [x] 6.3 Añadir prueba de integración que confirme que revocar una credencial no afecta a la otra.
- [x] 6.4 Añadir prueba de integración que confirme que un administrador no obtiene memorias de otro usuario, ejercitando RLS con usuarios reales de PostgreSQL.
- [x] 6.5 Comprobar en un cliente real que la cookie no acompaña a peticiones dirigidas a `/mcp` ni a otros subdominios.

## 7. Documentación y despliegue

- [x] 7.1 Documentar en el runbook de operaciones el arranque del acceso web sobre el usuario ya existente en producción.
- [x] 7.2 Documentar las variables de entorno nuevas y el supuesto de que sitio y API comparten dominio registrable.
- [x] 7.3 Actualizar `CONTEXT.md` con el vocabulario de sesión web y administrador, y con el principio de que el contenido queda protegido por RLS mientras que la identidad se administra fuera de él.
