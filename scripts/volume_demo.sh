#!/bin/bash
# Task 4: prove named volumes keep data after the containers are deleted.
# First register a user and add a few notes in the browser, then run this
# from the project root (where docker-compose.yml is).
set -e
PROJECT="$(basename "$PWD")"
SQL="SELECT u.username, COUNT(n.id) AS notes FROM users u LEFT JOIN notes n ON n.user_id = u.id GROUP BY u.username;"

echo "1) Named volumes (pgdata = users + notes, redisdata = sessions + counters):"
docker volume ls | grep -E "pgdata|redisdata"
docker volume inspect "${PROJECT}_pgdata" | grep Mountpoint

echo "2) BEFORE: data in Postgres and Redis"
docker exec notes-db psql -U notesuser -d notesdb -c "$SQL"
echo "Visit counter: $(docker exec notes-redis redis-cli GET notes:page_visits)"
echo "Active sessions: $(docker exec notes-redis redis-cli --scan --pattern 'notes:session:*' | wc -l)"

echo "3) DELETE all containers (volumes are kept because we do NOT use -v):"
docker compose down
docker ps -a | grep notes- || echo "No notes containers exist now"

echo "4) Recreate containers:"
docker compose up -d
sleep 15

echo "5) AFTER: same data is still there:"
docker exec notes-db psql -U notesuser -d notesdb -c "$SQL"
echo "Visit counter: $(docker exec notes-redis redis-cli GET notes:page_visits)"
echo "Active sessions: $(docker exec notes-redis redis-cli --scan --pattern 'notes:session:*' | wc -l)"
echo "Refresh the browser: you are STILL logged in, because your session survived in Redis."
