"use client";
/* ============ WTAF — Agent Console (who each agent is, how it thinks, what it may touch) ============ */
import { useCallback, useEffect, useMemo, useState } from "react";
import type { AccentKey } from "@/lib/types";
import { Card, EmptyState } from "../primitives";
import { PageHead } from "../shared";
import { AgentAvatar } from "../agents";
import { USE_MOCK } from "@/lib/api/client";
import {
  getAgents,
  getPrompts,
  resetPromptToDefault,
  saveMentalModels,
  savePrompt,
  type AgentView,
  type PromptView,
} from "@/lib/api/wtaf";
import { AgentRoster, GLOBAL_ID } from "../console/agent-roster";
import { EffectivePromptPanel } from "../console/effective-prompt";
import { LayerBadge, LayerEditor, type Busy, type LayerCtl } from "../console/layer-editor";
import { MentalModelsPanel } from "../console/mental-models-panel";
import { offlineAgents } from "../console/offline";
import { ToolsPanel } from "../console/tools-panel";

const SOUL_KEY = "soul.core";
const RULES_KEY = "rules.global";

const AGENT_TABS = ["Identity", "Mental Models", "Skills", "Tools", "Effective Prompt"] as const;
const GLOBAL_TABS = ["Soul", "Rules"] as const;
type Tab = (typeof AGENT_TABS)[number] | (typeof GLOBAL_TABS)[number];

export function AgentConsole() {
  const [prompts, setPrompts] = useState<Record<string, PromptView>>({});
  const [agents, setAgents] = useState<AgentView[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<Record<string, Busy>>({});
  const [notice, setNotice] = useState<Record<string, string>>({});
  const [selectedId, setSelectedId] = useState<string>(GLOBAL_ID);
  const [tab, setTab] = useState<Tab>("Soul");
  const [togglePending, setTogglePending] = useState(false);
  // Bumped on every mutation so the composed-prompt preview refetches.
  const [version, setVersion] = useState(0);

  useEffect(() => {
    if (USE_MOCK) {
      setAgents(offlineAgents());
      return;
    }
    let alive = true;
    Promise.all([getPrompts(), getAgents()])
      .then(([rows, roster]) => {
        if (!alive) return;
        setPrompts(Object.fromEntries(rows.map((p) => [p.key, p])));
        setDrafts(Object.fromEntries(rows.map((p) => [p.key, p.current_text])));
        setAgents(roster);
      })
      .catch((e) => alive && setError(e?.message ?? "Failed to load the console"));
    return () => {
      alive = false;
    };
  }, []);

  // Fold a returned PromptView back into local state (after save / reset).
  const apply = useCallback((view: PromptView) => {
    setPrompts((prev) => ({ ...prev, [view.key]: view }));
    setDrafts((d) => ({ ...d, [view.key]: view.current_text }));
    setVersion((v) => v + 1);
  }, []);

  const mutate = useCallback(
    async (key: string, kind: Exclude<Busy, undefined>, run: () => Promise<PromptView>) => {
      setBusy((b) => ({ ...b, [key]: kind }));
      setNotice((n) => ({ ...n, [key]: "" }));
      try {
        apply(await run());
        setNotice((n) => ({
          ...n,
          [key]: kind === "save" ? "Saved · applies on next run" : "Reset to default",
        }));
      } catch (e) {
        setNotice((n) => ({
          ...n,
          [key]: `${kind === "save" ? "Save" : "Reset"} failed: ${(e as Error)?.message ?? "error"}`,
        }));
      } finally {
        setBusy((b) => ({ ...b, [key]: undefined }));
      }
    },
    [apply],
  );

  const ctl: LayerCtl = useMemo(
    () => ({
      prompts,
      drafts,
      busy,
      notice,
      readOnly: USE_MOCK,
      setDraft: (key, text) => setDrafts((d) => ({ ...d, [key]: text })),
      save: (key) => void mutate(key, "save", () => savePrompt(key, drafts[key] ?? "")),
      reset: (key) => void mutate(key, "reset", () => resetPromptToDefault(key)),
    }),
    [prompts, drafts, busy, notice, mutate],
  );

  const agent = agents?.find((a) => a.id === selectedId) ?? null;
  const customizedCount = Object.values(prompts).filter((p) => p.is_overridden).length;
  const customizedGlobals = [SOUL_KEY, RULES_KEY].filter((k) => prompts[k]?.is_overridden).length;

  function select(id: string) {
    setSelectedId(id);
    setTab(id === GLOBAL_ID ? "Soul" : "Identity");
  }

  async function toggleModel(key: string, enabled: boolean) {
    if (!agent) return;
    const next = enabled
      ? [...agent.mental_models, key]
      : agent.mental_models.filter((k) => k !== key);
    setTogglePending(true);
    try {
      const updated = await saveMentalModels(agent.id, next);
      setAgents((prev) => (prev ?? []).map((a) => (a.id === updated.id ? updated : a)));
      setVersion((v) => v + 1);
    } catch (e) {
      setNotice((n) => ({ ...n, [key]: `Toggle failed: ${(e as Error)?.message ?? "error"}` }));
    } finally {
      setTogglePending(false);
    }
  }

  const tabs = selectedId === GLOBAL_ID ? GLOBAL_TABS : AGENT_TABS;

  return (
    <div>
      <PageHead
        title="Agent Console"
        sub={
          agents
            ? `${agents.length} agents · soul · mental models · rules · ${customizedCount} customized`
            : "loading the council…"
        }
      />

      {error && (
        <Card className="span12">
          <EmptyState label="Couldn't load the console" sub={error} />
        </Card>
      )}

      {USE_MOCK && (
        <Card className="span12" style={{ marginBottom: 13 }}>
          <EmptyState
            label="Live API not connected — read-only"
            sub="Set NEXT_PUBLIC_API_URL to edit souls, rules, frameworks and skills."
          />
        </Card>
      )}

      {!error && agents === null && <Card className="span12" loading />}

      {!error && agents !== null && (
        <div style={{ display: "flex", alignItems: "flex-start", gap: 14 }}>
          <div
            style={{
              width: 232,
              flexShrink: 0,
              position: "sticky",
              top: 0,
              maxHeight: "calc(100vh - 130px)",
              overflowY: "auto",
              paddingRight: 2,
            }}
          >
            <AgentRoster
              agents={agents}
              selectedId={selectedId}
              customizedGlobals={customizedGlobals}
              onSelect={select}
            />
          </div>

          <div style={{ flex: 1, minWidth: 0 }}>
            <Card pad={false}>
              <Header agent={agent} prompts={prompts} />

              <div
                style={{
                  display: "flex",
                  gap: 4,
                  padding: "0 18px",
                  borderBottom: "1px solid var(--stroke)",
                }}
              >
                {tabs.map((t) => (
                  <button
                    key={t}
                    type="button"
                    onClick={() => setTab(t)}
                    style={{
                      padding: "9px 12px",
                      fontSize: 12,
                      fontWeight: tab === t ? 600 : 400,
                      background: "transparent",
                      border: "none",
                      borderBottom:
                        "2px solid " + (tab === t ? "var(--blue-bright)" : "transparent"),
                      color: tab === t ? "var(--t-hi)" : "var(--t-lo)",
                      cursor: "pointer",
                      marginBottom: -1,
                    }}
                  >
                    {t}
                  </button>
                ))}
              </div>

              <div className="card-pad">
                {selectedId === GLOBAL_ID ? (
                  <GlobalPanel ctl={ctl} tab={tab} agentCount={agents.length} />
                ) : agent ? (
                  <AgentPanel
                    agent={agent}
                    ctl={ctl}
                    tab={tab}
                    version={version}
                    togglePending={togglePending}
                    onToggleModel={toggleModel}
                    onOpenGlobals={() => select(GLOBAL_ID)}
                  />
                ) : (
                  <EmptyState label="Select an agent" sub="Pick a member of the council." />
                )}
              </div>
            </Card>
          </div>
        </div>
      )}
    </div>
  );
}

/* ---- detail header: who you're editing ---- */
function Header({
  agent,
  prompts,
}: {
  agent: AgentView | null;
  prompts: Record<string, PromptView>;
}) {
  const chips = agent
    ? [
        ["soul", "inherited"],
        ["rules", "inherited"],
        ["mental_model", `${agent.mental_models.length} frameworks`],
        ["personality", prompts[agent.personality_key]?.is_overridden ? "voice · edited" : "voice"],
        ["skill", `${agent.skill_keys.length} skills`],
      ]
    : [
        ["soul", "one soul"],
        ["rules", "one rulebook"],
      ];

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 13, padding: "16px 18px 14px" }}>
      <AgentAvatar
        a={{
          glyph: agent?.glyph ?? "§",
          accent: (agent?.accent as AccentKey) ?? "chair",
        }}
        size={42}
      />
      <div style={{ minWidth: 0 }}>
        <div className="display" style={{ fontSize: 17, fontWeight: 600 }}>
          {agent?.name ?? "Council-wide"}
        </div>
        <div className="mono" style={{ fontSize: 11, color: "var(--t-mid)", marginTop: 2 }}>
          {agent ? `T${agent.tier} · ${agent.role}` : "the soul and rules every agent inherits"}
        </div>
      </div>
      <div style={{ marginLeft: "auto", display: "flex", gap: 6, flexWrap: "wrap", justifyContent: "flex-end" }}>
        {chips.map(([layer, label]) => (
          <LayerBadge key={layer} layer={layer} label={label} />
        ))}
      </div>
    </div>
  );
}

/* ---- council-wide: SOUL.md + the rulebook ---- */
function GlobalPanel({
  ctl,
  tab,
  agentCount,
}: {
  ctl: LayerCtl;
  tab: Tab;
  agentCount: number;
}) {
  const isSoul = tab === "Soul";
  return (
    <LayerEditor
      ctl={ctl}
      promptKey={isSoul ? SOUL_KEY : RULES_KEY}
      rows={14}
      hint={
        isSoul
          ? `The core essence prepended to every agent's system prompt — one identity carried by all ${agentCount} agents, every run.`
          : `Global constraints placed above every persona and task. All ${agentCount} agents obey them, and the task's output contract is the only thing that outranks them.`
      }
    />
  );
}

/* ---- one agent: identity, mind, skills, tools, and the composed result ---- */
function AgentPanel({
  agent,
  ctl,
  tab,
  version,
  togglePending,
  onToggleModel,
  onOpenGlobals,
}: {
  agent: AgentView;
  ctl: LayerCtl;
  tab: Tab;
  version: number;
  togglePending: boolean;
  onToggleModel: (key: string, enabled: boolean) => void;
  onOpenGlobals: () => void;
}) {
  if (tab === "Mental Models") {
    return (
      <MentalModelsPanel
        agent={agent}
        ctl={ctl}
        onToggle={onToggleModel}
        pending={togglePending}
      />
    );
  }
  if (tab === "Tools") return <ToolsPanel agent={agent} />;
  if (tab === "Effective Prompt") return <EffectivePromptPanel agent={agent} version={version} />;

  if (tab === "Skills") {
    if (agent.skill_keys.length === 0) {
      return (
        <EmptyState
          label="No LLM skill"
          sub={`${agent.name} runs deterministic tools only — nothing to instruct.`}
        />
      );
    }
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
        <div style={{ fontSize: 11.5, color: "var(--t-lo)", lineHeight: 1.5 }}>
          The standard operating procedure for each reasoning step {agent.name} owns — what to do
          and what to return. Identity layers are prepended to these at run time.
        </div>
        {agent.skill_keys.map((k) => (
          <LayerEditor key={k} ctl={ctl} promptKey={k} rows={9} />
        ))}
      </div>
    );
  }

  // Identity: this agent's voice, plus what it inherits from the council.
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
      <LayerEditor
        ctl={ctl}
        promptKey={agent.personality_key}
        rows={6}
        hint={`How ${agent.name} sounds. Tone only — it never overrides the rules or the task's output contract.`}
      />
      <Inherited ctl={ctl} onOpen={onOpenGlobals} />
    </div>
  );
}

/* ---- read-only preview of the two global layers, with a jump to edit them ---- */
function Inherited({ ctl, onOpen }: { ctl: LayerCtl; onOpen: () => void }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 9 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 9 }}>
        <div className="label-xs">Inherited from the council</div>
        <button
          type="button"
          onClick={onOpen}
          className="mono"
          style={{
            fontSize: 10.5,
            padding: "3px 9px",
            borderRadius: 8,
            background: "transparent",
            border: "1px solid var(--stroke)",
            color: "var(--t-mid)",
            cursor: "pointer",
          }}
        >
          edit council-wide →
        </button>
      </div>
      {[SOUL_KEY, RULES_KEY].map((key) => {
        const p = ctl.prompts[key];
        if (!p) return null;
        return (
          <div
            key={key}
            style={{
              padding: "10px 13px",
              borderRadius: 10,
              background: "var(--inset)",
              border: "1px solid var(--stroke)",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 5 }}>
              <LayerBadge layer={p.layer} />
              <span style={{ fontSize: 12, fontWeight: 600 }}>{p.label}</span>
            </div>
            <div
              className="mono"
              style={{
                fontSize: 11,
                lineHeight: 1.55,
                color: "var(--t-lo)",
                display: "-webkit-box",
                WebkitLineClamp: 3,
                WebkitBoxOrient: "vertical",
                overflow: "hidden",
              }}
            >
              {p.current_text}
            </div>
          </div>
        );
      })}
    </div>
  );
}
