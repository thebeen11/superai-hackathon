This is a [Next.js](https://nextjs.org) project bootstrapped with [`create-next-app`](https://nextjs.org/docs/app/api-reference/cli/create-next-app).

## Getting Started

First, run the development server:

```bash
npm run dev
# or
yarn dev
# or
pnpm dev
# or
bun dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser to see the result.

You can start editing the page by modifying `app/page.tsx`. The page auto-updates as you edit the file.

> Use **pnpm** (never npm/yarn) and keep `--webpack` on `dev` (LocatorJS depends on it).

## Backend integration (OpenAPI)

The dashboard runs on mock data by default and swaps to the real FastAPI backend
through a single env var:

```bash
# frontend/.env.local  (gitignored)
NEXT_PUBLIC_API_URL=http://localhost:8000
```

- **Unset** → `USE_MOCK` is true, the whole dashboard renders from `src/lib/mock-data.ts`.
- **Set** → `getSnapshot()` pulls `GET /items` and `src/lib/api/adapter.ts` derives the
  source-anchored slices (Sources, Trackers, Watchlist, Signal Volume). The remaining
  sections (ACE, debate, ledger, predictions, indicators) stay on mock until backend
  Tiers 3–5 (Andie / Freddy / Winston) exist. The topbar field then acts as a live
  discovery search: a topic runs `POST /discover` → `POST /dataeng/process`, then refreshes.

### Regenerating the typed client

The typed client in `src/lib/api/generated/` is produced by
[`@hey-api/openapi-ts`](https://heyapi.dev) from the committed `backend/openapi.json`:

```bash
# 1. (backend) refresh the schema after changing any route
cd ../backend && uv run python scripts/dump_openapi.py
# 2. (frontend) regenerate the typed client + types
cd ../frontend && pnpm gen:api
```

Both `backend/openapi.json` and `src/lib/api/generated/` are committed, so the build
never needs the backend running.

This project uses [`next/font`](https://nextjs.org/docs/app/building-your-application/optimizing/fonts) to automatically optimize and load [Geist](https://vercel.com/font), a new font family for Vercel.

## Learn More

To learn more about Next.js, take a look at the following resources:

- [Next.js Documentation](https://nextjs.org/docs) - learn about Next.js features and API.
- [Learn Next.js](https://nextjs.org/learn) - an interactive Next.js tutorial.

You can check out [the Next.js GitHub repository](https://github.com/vercel/next.js) - your feedback and contributions are welcome!

## Deploy on Vercel

The easiest way to deploy your Next.js app is to use the [Vercel Platform](https://vercel.com/new?utm_medium=default-template&filter=next.js&utm_source=create-next-app&utm_campaign=create-next-app-readme) from the creators of Next.js.

Check out our [Next.js deployment documentation](https://nextjs.org/docs/app/building-your-application/deploying) for more details.
