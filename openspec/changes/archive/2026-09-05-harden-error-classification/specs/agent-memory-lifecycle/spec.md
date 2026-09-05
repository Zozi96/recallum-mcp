## MODIFIED Requirements

### Requirement: Deduplicación exacta
El sistema MUST evitar memorias activas duplicadas para el mismo usuario, ámbito y contenido
normalizado, y MUST registrar la fecha de reconfirmación cuando un contenido idéntico vuelve a
guardarse, exponiéndola en las respuestas como señal de frescura. La violación del índice de dedup
MUST clasificarse por el código estructurado del motor (SQLSTATE de PostgreSQL para violación de
unicidad) y por el nombre de la restricción cuando el driver lo expone, MUST NOT compararse por el
texto libre del mensaje de error.

#### Scenario: Recordar el mismo hecho dos veces
- **WHEN** un usuario guarda nuevamente una memoria activa con el mismo contenido normalizado y ámbito
- **THEN** el sistema devuelve la memoria existente y no crea una segunda fila

#### Scenario: Reconfirmación con huella temporal
- **WHEN** un contenido idéntico a una memoria activa vuelve a guardarse
- **THEN** la memoria existente registra la fecha de reconfirmación y las respuestas posteriores la incluyen

#### Scenario: Clasificación estructural de la colisión de dedup
- **WHEN** la base de datos rechaza una inserción por el índice de dedup activo
- **THEN** el sistema reconoce la colisión por su código SQLSTATE y restricción, y la reintenta como reconfirmación sin depender del texto del error

#### Scenario: Otro IntegrityError no se reintenta como dedup
- **WHEN** la base de datos lanza un `IntegrityError` por una restricción distinta a la de dedup
- **THEN** el error NO se reintenta ni se etiqueta como reconfirmación; se propaga
