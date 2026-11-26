# BalkanTranslate Frontend

React + TypeScript + Vite + Tailwind CSS client for BalkanTranslate.

## Development

```bash
npm ci --legacy-peer-deps
npm run dev
```

By default, Vite proxies `/translate` and `/health` to `http://localhost:8000` (configurable via `VITE_PROXY_TARGET`).

## Environment Variables

| Variable | Description | Default |
| :--- | :--- | :--- |
| `VITE_API_URL` | Base URL of the FastAPI gateway (baked in at build time) | `""` (same-origin / proxy) |
| `VITE_PROXY_TARGET` | Dev server proxy target for `/translate` and `/health` | `http://localhost:8000` |

## Scripts

- `npm run dev` — Start Vite dev server
- `npm run build` — Type-check (`tsc -b`) and build production bundle
- `npm run lint` — Run ESLint
- `npm test` — Run SSE parser tests (Node 22.18+)
- `npm run preview` — Preview production build locally
