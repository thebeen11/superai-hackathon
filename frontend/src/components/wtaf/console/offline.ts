/**
 * Offline roster for the Agent Console.
 *
 * With no API configured (USE_MOCK) the console still renders the council from the
 * static topology in `lib/tiers.ts` so the page can be demoed without a backend —
 * read-only, with no prompt text (the layers live server-side).
 */
import type { AgentView } from "@/lib/api/wtaf";
import { tierTopology } from "@/lib/tiers";

export function offlineAgents(): AgentView[] {
  return tierTopology.flatMap((t) =>
    t.squad.map((a) => ({
      id: a.id,
      name: a.name,
      role: a.role,
      tier: t.n,
      tier_label: t.label,
      glyph: a.glyph,
      accent: a.accent,
      tools: a.tools.map((name) => ({
        name,
        description: "Declared in the frontend topology — connect the API for the real tool spec.",
        io: "—",
        module: "lib/tiers.ts",
      })),
      skill_keys: [],
      personality_key: `personality.${a.id}`,
      mental_models: [],
      available_mental_models: [],
    })),
  );
}
