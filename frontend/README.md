# Frontend

Next.js (TypeScript) app for the SuperAI Hackathon project.

## Tech Stack

- **Framework:** Next.js
- **Language:** TypeScript
- **Styling:** TODO (e.g. Tailwind CSS)

## Setup

```bash
pnpm install
```

## Running

```bash
pnpm dev
```

The app runs at http://localhost:3000.

## Scripts

| Command         | Description           |
| --------------- | --------------------- |
| `pnpm dev`      | Start the dev server  |
| `pnpm build`    | Build for production  |
| `pnpm start`    | Run the production build |
| `pnpm lint`     | Lint the codebase     |

## Environment Variables

Create a `.env.local` file in this directory:

```bash
# NEXT_PUBLIC_API_URL=http://localhost:8000
```

## Project Structure

```
frontend/
├── app/            # App Router pages & layouts
├── components/     # Reusable UI components
├── public/         # Static assets
└── package.json
```
