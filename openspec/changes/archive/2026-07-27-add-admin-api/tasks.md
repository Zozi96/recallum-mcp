## 1. Autorización de administración

- [x] 1.1 Crear el módulo de rutas de administración bajo `/api/v1/admin`, montado en el router `/api/v1` existente.
- [x] 1.2 Implementar la dependencia que exige sesión válida con condición de administrador y rechaza al resto.
- [x] 1.3 Aplicarla a todas las rutas de administración de forma que ninguna pueda quedar sin ella por olvido.
- [x] 1.4 Añadir pruebas de acceso denegado sin sesión y con sesión de usuario ordinario.

## 2. Usuarios

- [x] 2.1 Extender el repositorio de usuarios con la enumeración y el recuento de administradores.
- [x] 2.2 Implementar la enumeración con correo, alta, condición de administrador, existencia de acceso web y número de credenciales activas.
- [x] 2.3 Implementar la creación de usuarios reutilizando el servicio existente, rechazando correos duplicados.
- [x] 2.4 Implementar la concesión y retirada de la condición de administrador.
- [x] 2.5 Rechazar la retirada que dejaría el sistema sin ningún administrador.
- [x] 2.6 Añadir pruebas de duplicado de correo, estado inicial del usuario creado y bloqueo de la retirada del último administrador.

## 3. Credenciales

- [x] 3.1 Implementar la enumeración de las keys de cualquier usuario, sin secretos.
- [x] 3.2 Implementar la emisión para cualquier usuario con verificación previa de la contraseña del administrador, devolviendo el secreto una única vez.
- [x] 3.3 Implementar la revocación de cualquier key sin exigir contraseña.
- [x] 3.4 Añadir pruebas de que sin contraseña válida no se emite ninguna key y de que una key revocada deja de autenticar llamadas MCP.

## 4. Agregados del sistema

- [x] 4.1 Implementar el recuento de usuarios y el reparto de credenciales activas y revocadas sobre la sesión de administración.
- [x] 4.2 Implementar el volumen de memorias por usuario recorriendo los usuarios y agregando cada uno en su propio contexto.
- [x] 4.3 Exponer el endpoint de agregados sin ningún contenido de memorias.
- [x] 4.4 Añadir prueba de integración con dos usuarios reales que confirme recuentos correctos y ausencia total de contenido.
- [x] 4.5 Añadir prueba de que un usuario sin memorias aparece con volumen cero.

## 5. Estado operativo

- [x] 5.1 Implementar el estado detallado de base de datos y servicio de embeddings para administradores.
- [x] 5.2 Añadir la detección de vectores cuyo modelo de embeddings no coincide con el configurado.
- [x] 5.3 Añadir prueba de que la respuesta no contiene credenciales ni cadenas de conexión.

## 6. Verificación del aislamiento

- [x] 6.1 Añadir prueba de integración que confirme que ninguna ruta de administración devuelve memorias de otro usuario.
- [x] 6.2 Añadir prueba que confirme que la sesión de administración no selecciona ninguna fila de memorias, con independencia de la lógica de aplicación.
- [x] 6.3 Revisar que ninguna ruta de administración abre una sesión de base de datos con contexto de un usuario distinto del propio administrador.
- [x] 6.4 Confirmar que no existe ninguna operación de borrado de usuarios en la API web.

## 7. Contrato y documentación

- [x] 7.1 Incluir las rutas de administración en el contrato exportado que consume el sitio web.
- [x] 7.2 Documentar que el CLI sigue siendo la vía de recuperación cuando no hay acceso web posible.
- [x] 7.3 Documentar por qué el borrado de usuarios permanece fuera de la web.
