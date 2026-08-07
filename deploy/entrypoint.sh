#!/bin/sh
# Migrate, then serve. Both halves live here, so the image has exactly one way
# to start and nothing outside it can reorder the two.
#
# Compose can express "migrate first" with a one-shot service and
# `depends_on: service_completed_successfully`. A managed single-service
# deployment (Dokploy on Swarm) cannot: it offers one container definition, so
# the ordering has to live where a redeploy cannot forget it. Putting the
# alembic command in the deployment's *run command* field instead produces a
# container that migrates, exits 0, and is restarted forever while nothing ever
# listens -- a failure that reports success.
#
# The server command is written out here rather than left as a Dockerfile CMD
# precisely because CMD is what those fields replace. There is no CMD to
# override, so the only way to skip the migration is to replace the entrypoint
# itself, which is explicit and hard to do by accident.
#
# `exec` matters: Granian replaces this shell as PID 1, so SIGTERM reaches it
# directly and the lifespan shutdown (telemetry flush, engine dispose) runs.
set -eu

serve() {
    exec uv run --no-sync granian \
        --interface asgi --factory --host 0.0.0.0 --port 8000 \
        recallum.app:create_app
}

if [ "${RECALLUM_SKIP_MIGRATIONS:-0}" = "1" ]; then
    # Escape hatch for diagnosis: serve without touching the schema, e.g. to
    # inspect a container whose database is unreachable or mid-restore.
    echo "entrypoint: RECALLUM_SKIP_MIGRATIONS=1 -- skipping alembic" >&2
    serve
fi

attempts="${RECALLUM_MIGRATION_ATTEMPTS:-10}"
delay="${RECALLUM_MIGRATION_RETRY_SECONDS:-3}"
attempt=1

# Swarm has no `depends_on`, so on a cold start PostgreSQL may still be
# accepting no connections. Retrying also absorbs the rare concurrent-boot
# race when more than one replica migrates at once: the loser fails, retries,
# and finds the schema already at head.
until uv run --no-sync alembic upgrade head; do
    if [ "$attempt" -ge "$attempts" ]; then
        echo "entrypoint: migrations failed after ${attempt} attempts; refusing to start" >&2
        # Exit non-zero on purpose. Serving against a schema the code does not
        # expect is worse than being down, and a non-zero exit is visible in
        # `docker service ps` where an exit-0 restart loop is not.
        exit 1
    fi
    echo "entrypoint: migration attempt ${attempt}/${attempts} failed; retrying in ${delay}s" >&2
    attempt=$((attempt + 1))
    sleep "$delay"
done

serve
