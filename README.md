# Vue 3 + Vite

## Docker deployment

Copy the examples without overwriting existing local environment files:

```sh
cp .env.example .env
cp backend/.env.example backend/.env
```

Set real credentials, especially `JWT_SECRET_KEY`, database passwords, CORS,
and provider keys, then run `docker compose up -d`.

The one-shot `migration` service runs `alembic upgrade head` before the API and
worker. Use `docker compose ps` and `docker compose logs -f backend worker migration`; the backend health endpoint is `http://localhost:8000/health`.
The frontend is at `http://localhost:8080`, proxies `/api/`, and uses an SPA
history fallback so routes such as `/chat` survive refreshes.

`VITE_API_BASE_URL` is injected at frontend image build time and defaults to
`/api`. MySQL, Redis AOF data, and uploads use named volumes. Redis AOF keeps
RQ jobs and lease state across normal restarts; back up MySQL and the
`rag-uploads` volume before upgrades or host maintenance.

This template should help get you started developing with Vue 3 in Vite. The template uses Vue 3 `<script setup>` SFCs, check out the [script setup docs](https://v3.vuejs.org/api/sfc-script-setup.html#sfc-script-setup) to learn more.

Learn more about IDE Support for Vue in the [Vue Docs Scaling up Guide](https://vuejs.org/guide/scaling-up/tooling.html#ide-support).
