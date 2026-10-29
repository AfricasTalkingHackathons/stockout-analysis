# StockOut Alert — frontend

React 19 + Vite + TypeScript UI. See the [project README](../README.md) for architecture, demo accounts, Africa's Talking setup and how to run the full stack.

```bash
npm install
npm run dev          # http://localhost:5173, proxies /api to http://127.0.0.1:8000
npm test
npm run typecheck
npm run build
```

Set `VITE_API_URL` for a production build that talks to a remote API. Leave it empty in development so the Vite proxy is used.
