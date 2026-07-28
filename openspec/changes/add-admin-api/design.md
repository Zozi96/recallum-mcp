## Context

El aislamiento de Recallum no es una convención de la aplicación, es una propiedad del esquema. `memories` tiene `FORCE ROW LEVEL SECURITY` con una política que compara `user_id` contra `app.current_user_id`, y el rol de aplicación se crea `NOSUPERUSER NOBYPASSRLS`. `SessionProvider.admin()` no fija esa variable, de modo que la comparación se hace contra `NULL` y ninguna memoria resulta seleccionable.

`api_keys` está en un régimen distinto a propósito: RLS habilitado pero sin `FORCE`, y el rol de aplicación es dueño de las tablas. El bypass de propietario es lo que permite la búsqueda por hash previa a la autenticación, y de paso lo que hace administrable la tabla. `users` no tiene RLS.

El reparto actual es exacto: `memory_repo` usa `for_user()` en sus diez métodos, `user_repo` y `api_key_repo` usan `admin()` en todos los suyos.

`add-web-session-auth` introdujo `is_admin`, que hasta ahora no condiciona ninguna operación.

El despliegue tiene un único usuario, que es a la vez operador y dueño de memorias.

## Goals / Non-Goals

**Goals:**

- Llevar a la web la administración de usuarios y credenciales que hoy sólo existe en el CLI.
- Dar al operador una vista agregada del sistema.
- Que la imposibilidad de leer memorias ajenas siga siendo una garantía de la base de datos.
- Impedir que el sistema quede sin ningún administrador.
- Conservar el CLI como vía de recuperación.

**Non-Goals:**

- Borrar usuarios o sus memorias.
- Leer, buscar, editar o exportar memorias de otros usuarios.
- Roles intermedios o permisos granulares.
- Suplantación de usuarios para soporte.
- Invitaciones, correo saliente o registro autónomo.
- Auditoría con garantías de no repudio.

## Decisions

### La administración se apoya en la separación de sesiones que ya existe

No se introduce ningún acceso nuevo a la base de datos. Las operaciones sobre usuarios y credenciales usan `admin()`, exactamente como ya hacen `user_repo` y `api_key_repo`, y las agregaciones sobre memorias usan `for_user()` como todo lo demás.

La consecuencia es que el reparto entre las dos sesiones sigue siendo legible de un vistazo, y que un endpoint mal ubicado se detecta mirando qué sesión abre. Esa correspondencia entre la forma de la API y la forma del acceso a datos es la principal defensa de esta capacidad, más que cualquier comprobación de permisos.

### Los agregados de memorias se obtienen usuario a usuario, no con una consulta global

Un recuento global sería la consulta natural, pero bajo `admin()` devuelve cero por diseño, y las salidas para evitarlo son todas peores. Una política adicional gobernada por una variable convertiría una barrera dura en una convención. Una función con privilegios elevados tampoco serviría, porque `FORCE` somete también al propietario. Contadores mantenidos por disparadores introducen deriva entre el contador y la realidad.

Se opta por recorrer los usuarios y agregar cada uno en su propio contexto. Es una consulta por usuario, lo que con la escala actual es irrelevante, y tiene la propiedad de que la administración nunca abre una sesión capaz de ver contenido ajeno: sólo obtiene números calculados dentro del ámbito de cada usuario.

Cuando el número de usuarios haga que esto duela, la salida es materializar los recuentos, y ese cambio no altera lo que ve quien consulta.

### La condición de administrador restringe, pero no es lo que protege

Las rutas de administración exigen `is_admin` y rechazan a cualquier otro usuario autenticado. Conviene ser claro sobre qué aporta esa comprobación: impide que un usuario ordinario gestione credenciales ajenas o vea la lista de usuarios.

Lo que **no** aporta es la protección del contenido. Aunque la comprobación se eliminara por error, ninguna ruta de administración podría devolver una memoria ajena, porque ninguna abre una sesión capaz de seleccionarla. La autorización delimita capacidades administrativas; el aislamiento del contenido lo sostiene PostgreSQL.

### Emitir credenciales exige la contraseña del administrador

Se extiende la decisión ya tomada para las keys propias. Una sesión web caduca; una API key no. Si una sesión de administrador bastara para emitir credenciales a cualquier usuario, robarla durante su ventana de validez permitiría acuñar accesos permanentes a varias cuentas.

Revocar no la exige, igual que en autoservicio: la operación que reduce acceso no debe tener fricción.

Crear un usuario tampoco la exige. Un usuario recién creado no tiene credenciales ni contraseña, así que por sí solo no otorga ningún acceso.

### El sistema no puede quedarse sin administradores

Retirar la condición de administrador se rechaza cuando dejaría el sistema sin ninguno. Con un único operador, la operación que se bloquea es precisamente la que lo dejaría fuera de su propia consola.

Es una comprobación barata que evita un fallo cuya única salida sería entrar por consola al contenedor. El CLI se conserva justamente para ese tipo de recuperación, pero preferimos no necesitarlo.

### Borrar usuarios queda fuera

`users` tiene borrado en cascada hacia `memories` y `api_keys`. Un borrado desde la web sería un botón que destruye de forma irreversible todo el contenido de una persona, y ninguna confirmación en la interfaz compensa eso.

Mientras no exista una estrategia de retirada pensada, con exportación previa o desactivación reversible, la operación se queda en el CLI, donde exige acceso al servidor y una intención explícita.

### Desactivar un usuario se resuelve revocando sus credenciales

No se añade un estado de usuario desactivado. Revocar todas sus API keys y dejarlo sin contraseña produce el efecto deseado con los mecanismos que ya existen y sin introducir un estado nuevo que todas las consultas tendrían que tener en cuenta.

Si más adelante hace falta distinguir "sin acceso" de "retirado", será un cambio con su propia justificación.

### El estado operativo para el operador es distinto de las sondas públicas

`/readyz` responde a un orquestador y omite detalles a propósito. Un operador necesita algo más: qué dependencia falla, desde cuándo, y si el modelo de embeddings configurado coincide con el que produjo los vectores almacenados, porque esa discordancia hace que la similitud vectorial deje de tener sentido sin que nada se rompa visiblemente.

Esa información se expone sólo a administradores autenticados, y sin credenciales ni cadenas de conexión.

## Risks / Trade-offs

- **Los agregados hacen una consulta por usuario.** Irrelevante ahora, con salida conocida cuando deje de serlo.
- **La consola es casi vacía con un solo usuario.** Es la última change de la secuencia por eso mismo; su valor aparece con el segundo.
- **Pedir la contraseña para emitir keys añade fricción.** Coherente con autoservicio y sobre una operación poco frecuente.
- **No poder borrar usuarios desde la web deja una operación sólo en el CLI.** Preferido frente a exponer una destrucción irreversible en un navegador.
- **`is_admin` es binario.** Suficiente mientras haya un operador; introducir roles ahora sería diseñar sin caso de uso.

## Open Questions

- Si el operador debe poder asignar contraseña a otro usuario o si eso debe seguir siendo exclusivo del CLI.
- Si la lista de usuarios debe mostrar la fecha de último uso de credenciales, sabiendo que se actualiza con granularidad de un minuto.
- Si el estado operativo debe incluir el recuento de vectores con modelo de embeddings distinto del configurado, o basta con señalar que existen.
- Si conviene registrar las acciones administrativas antes de que haya más de un operador.
