## Why

Crear un usuario, emitirle una API key o revocársela sólo es posible hoy entrando por consola al contenedor y ejecutando `recallum-admin`. Mientras el sistema tenga un único usuario eso es un inconveniente menor; en cuanto haya que dar de alta a alguien más, deja de serlo, y el sitio de administración quedaría con una sección vacía justo donde promete administrar.

Falta además la vista de conjunto. Un operador necesita saber cuántos usuarios hay, cuáles tienen credenciales activas, cuáles llevan tiempo sin aparecer y cómo está creciendo el sistema en total. Ninguna de esas preguntas se responde memoria a memoria, y ninguna requiere leer una sola memoria.

Esa distinción es lo que hace viable esta capacidad. La administración no necesita acceso al contenido, y la base de datos ya se lo impide: las políticas de `memories` no seleccionan nada sin contexto de usuario, y la tabla las aplica incluso a su propietario. La consola puede contar sin poder leer, y eso no depende de que la aplicación se porte bien.

## What Changes

- Restringir las operaciones de administración a usuarios marcados como administradores, rechazando al resto aunque tengan sesión válida.
- Permitir enumerar los usuarios del sistema con su estado de acceso y su actividad de credenciales.
- Permitir crear usuarios desde la web, con o sin acceso al sitio de administración.
- Permitir enumerar, emitir y revocar las API keys de cualquier usuario.
- Permitir conceder y retirar la condición de administrador, impidiendo que el sistema se quede sin ninguno.
- Ofrecer una vista agregada del sistema: número de usuarios, credenciales activas y revocadas, y volumen total de memorias por usuario, sin exponer su contenido.
- Mantener la imposibilidad de leer memorias ajenas como propiedad garantizada por la base de datos, no por la capa de aplicación.
- Exponer el estado operativo de las dependencias con el detalle que necesita un operador y que las sondas públicas no dan.

## Capabilities

### New Capabilities

- `web-admin-console`: Administración de usuarios, credenciales y estado del sistema desde el sitio web, con acceso al contenido de las memorias estructuralmente imposible.

### Modified Capabilities

Ninguna. Las herramientas MCP, la API de autoservicio y la lógica de memoria no cambian.

## Impact

- Reutiliza los servicios de identidad existentes; no añade lógica de gestión de usuarios ni de credenciales.
- Traslada a la web lo que hoy sólo existe en el CLI, que se conserva como vía de recuperación cuando no hay acceso web posible.
- Introduce el primer punto donde una operación depende de la condición de administrador, hasta ahora sin ningún uso.
- Los agregados de memorias se obtienen por usuario y con su contexto activo, de modo que la administración nunca abre una sesión capaz de leer contenido ajeno.
- Completa la superficie que consume el sitio de administración; no incluye borrado de usuarios ni de sus memorias.
