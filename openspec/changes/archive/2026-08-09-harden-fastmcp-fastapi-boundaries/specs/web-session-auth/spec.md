## MODIFIED Requirements

### Requirement: Inicio de sesión con credenciales verificadas
El sistema MUST verificar correo y contraseña antes de emitir una sesión, MUST almacenar la contraseña únicamente mediante una función de derivación de clave resistente a fuerza bruta, MUST NOT revelar si el fallo se debe al correo o a la contraseña y MUST aplicar presupuestos configurables por origen y por combinación origen-cuenta sin bloquear globalmente una cuenta.

#### Scenario: Credenciales válidas
- **WHEN** se envía un correo con contraseña asignada y la contraseña correcta dentro del presupuesto permitido
- **THEN** el sistema establece una sesión y devuelve la identidad autenticada

#### Scenario: Contraseña incorrecta o correo desconocido
- **WHEN** la contraseña no coincide o el correo no existe
- **THEN** el sistema rechaza el intento con una respuesta y un trabajo de verificación indistinguibles entre ambos casos

#### Scenario: Almacenamiento de la contraseña
- **WHEN** se inspecciona el registro del usuario
- **THEN** la contraseña no aparece en claro ni como resumen de una función de hash rápida de propósito general

#### Scenario: Presupuesto de login agotado
- **WHEN** un origen o una combinación origen-cuenta supera el número configurado de intentos fallidos
- **THEN** el sistema responde `429` con `Retry-After` sin verificar otra contraseña durante esa ventana y sin indicar cuál presupuesto se agotó

## ADDED Requirements

### Requirement: Entradas de autenticación acotadas
El sistema MUST imponer un máximo de bytes al cuerpo de autenticación y un máximo de longitud a cada contraseña antes de ejecutar la función de derivación.

#### Scenario: Cuerpo de login excesivo
- **WHEN** el cuerpo de login excede el límite configurado con o sin `Content-Length`
- **THEN** el sistema responde `413` antes de parsear el cuerpo completo o ejecutar Argon2

#### Scenario: Contraseña excesiva
- **WHEN** login o una confirmación sensible recibe una contraseña mayor al máximo documentado
- **THEN** el sistema rechaza la entrada como inválida sin ejecutar la verificación costosa

### Requirement: Atribución confiable del cliente
El sistema MUST usar el peer de red inmediato para atribuir límites y MUST procesar `X-Forwarded-For` sólo cuando el peer pertenece a un CIDR confiable configurado. En ese caso MUST recorrer la cadena de derecha a izquierda, omitir saltos que pertenezcan a CIDR confiables y seleccionar la primera IP no confiable; una cadena malformada MUST caer al peer inmediato.

#### Scenario: Header reenviado por peer no confiable
- **WHEN** un cliente directo envía `X-Forwarded-For` o `Forwarded`
- **THEN** el sistema ignora ese valor para rate limiting y observabilidad

#### Scenario: Petición desde Traefik permitido
- **WHEN** el peer pertenece a un CIDR de proxy permitido y envía una cadena válida de forwarding
- **THEN** el sistema deriva como cliente la primera IP no confiable al recorrer `X-Forwarded-For` de derecha a izquierda

#### Scenario: Valor falsificado antepuesto
- **WHEN** un atacante antepone una IP falsa a una cadena que Traefik completa con la IP real a su derecha
- **THEN** el sistema se detiene en la IP real no confiable y no usa el valor antepuesto

### Requirement: Respuestas web no cacheables
El sistema MUST marcar las respuestas de autenticación y todas las respuestas privadas de `/api/v1` como no almacenables por navegadores, proxies y caches compartidos.

#### Scenario: Respuesta de login o endpoint privado
- **WHEN** el servidor responde a login, logout o una ruta autenticada
- **THEN** la respuesta incluye `Cache-Control: no-store` y no habilita cache compartido
