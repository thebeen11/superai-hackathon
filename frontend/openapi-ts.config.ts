import { defineConfig } from "@hey-api/openapi-ts";

// Generates a typed client from the backend's committed OpenAPI schema.
// Run `pnpm gen:api` after regenerating `backend/openapi.json`.
export default defineConfig({
  input: "../backend/openapi.json",
  output: {
    path: "src/lib/api/generated",
  },
  plugins: ["@hey-api/client-fetch", "@hey-api/sdk", "@hey-api/typescript"],
});
