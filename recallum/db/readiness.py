"""Deep database-readiness module for schema and runtime-role safety."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

_READINESS_SQL = text(
    """
    SELECT
        NOT role.rolsuper
        AND NOT role.rolbypassrls
        AND count(table_info.oid) = 4
        AND bool_and(table_info.relowner = role.oid)
        AND bool_and(
            table_info.relname NOT IN ('memories', 'memory_profiles')
            OR (table_info.relrowsecurity AND table_info.relforcerowsecurity)
        )
    FROM pg_roles AS role
    LEFT JOIN pg_class AS table_info
      ON table_info.relname IN ('users', 'api_keys', 'memories', 'memory_profiles')
     AND table_info.relnamespace = 'public'::regnamespace
    WHERE role.rolname = current_user
    GROUP BY role.rolsuper, role.rolbypassrls
    """
)


class DatabaseReadiness:
    """Own the PostgreSQL readiness policy behind one boolean interface."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def is_ready(self) -> bool:
        """Return False for unavailable, incomplete, or unsafe databases."""
        try:
            async with self._engine.connect() as connection:
                result = await connection.execute(_READINESS_SQL)
            return bool(result.scalar_one())
        except Exception:
            return False
