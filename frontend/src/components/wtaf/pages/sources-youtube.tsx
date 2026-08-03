"use client";
/* ============ WTAF — Sources › YouTube ============
 *
 * Standing subscriptions, as opposed to the rest of the Sources page, which is an audit
 * ledger of whatever a one-off discovery happened to read. Follow a channel and its new
 * videos keep arriving; when a transcript discusses something on the watchlist, the exact
 * moment shows up below as evidence you can open at the second it was said.
 *
 * This tab owns its own data (the global snapshot is assembled from `GET /items` and knows
 * nothing about subscriptions), so it fetches on mount and after every mutation.
 *
 * Following a channel and FETCHING it are separate: subscribing returns instantly, then the
 * ingest runs as a background job — minutes per video — streamed into the shell's Activity
 * Log. Closing the tab does not abandon it, and a reload reattaches to whatever is still
 * running.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import {
  addYoutubeChannelSubscription,
  deleteYoutubeChannel,
  getRunningYoutubeJobs,
  getYoutubeChannels,
  getYoutubeMatches,
  jobStreamPath,
  setYoutubeChannelEnabled,
  toYoutubeIngestReport,
  youtubeRefreshStreamPath,
} from "@/lib/api/wtaf";
import { useWtaf } from "@/providers/wtaf-provider";
import type { YoutubeChannel, YoutubeMatch } from "@/lib/types";
import { Card, Dot, EmptyState } from "../primitives";
import { Field, IconButton, ScanToggle } from "../shared";
import { fmtOffset, sourceHref } from "../source-link";

/** Videos pulled when a channel is first followed. Mirrors YOUTUBE_CHANNEL_BACKFILL. */
const BACKFILL = 5;

/** Optimistic overlay, same shape the watchlist page uses. */
type Overlay = Record<string, { enabled?: boolean }>;

function fmtWhen(iso?: string): string {
  if (!iso) return "never";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "never";
  const mins = Math.round((Date.now() - d.getTime()) / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  if (mins < 60 * 24) return `${Math.round(mins / 60)}h ago`;
  return d.toLocaleDateString(undefined, { day: "2-digit", month: "short" });
}

function fmtSubs(n?: number): string | null {
  if (n == null) return null;
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M subs`;
  if (n >= 1_000) return `${Math.round(n / 1_000)}K subs`;
  return `${n} subs`;
}

function Notice({ text, tone = "error" }: { text: string; tone?: "error" | "ok" }) {
  return (
    <div
      className="mono"
      style={{
        fontSize: 10.5,
        marginTop: 4,
        color: tone === "error" ? "var(--down)" : "var(--t-lo)",
      }}
    >
      {text}
    </div>
  );
}

/* ---------------- add form ---------------- */

function AddChannel({
  onFollowed,
}: {
  onFollowed: (channel: YoutubeChannel) => void;
}) {
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);

  async function submit() {
    const id = value.trim();
    if (!id || busy) return;
    setBusy(true);
    setNotice(null);
    setOk(null);
    try {
      // Resolves in well under a second — the fetching is a background job kicked off by
      // the parent, so this never sits waiting on transcripts.
      const channel = await addYoutubeChannelSubscription(id);
      setValue("");
      setOk(`Following ${channel.name} — fetching its recent videos…`);
      onFollowed(channel);
    } catch (e) {
      setNotice((e as Error)?.message ?? "Could not follow that channel");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <Field label="Channel URL, @handle, or channel id">
        <div style={{ display: "flex", gap: 8 }}>
          <input
            className="r-input"
            style={{ flex: 1 }}
            placeholder="@Bloomberg"
            value={value}
            disabled={busy}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") void submit();
            }}
          />
          <button
            type="button"
            className="primary-btn"
            disabled={busy || !value.trim()}
            style={{ opacity: busy || !value.trim() ? 0.5 : 1 }}
            onClick={() => void submit()}
          >
            {busy ? "Following…" : "Follow"}
          </button>
        </div>
      </Field>
      {notice && <Notice text={notice} />}
      {ok && <Notice text={ok} tone="ok" />}
      <div className="mono" style={{ fontSize: 10, color: "var(--t-faint)", marginTop: 8 }}>
        Reading a video takes a few minutes, so fetching runs in the background — watch it in
        the Activity Log; you can leave this page. New videos are pulled once a day; ⟳ checks
        a channel now. Transcripts are metered, so following one backfills its {BACKFILL} most
        recent videos.
      </div>
    </div>
  );
}

/* ---------------- channel row ---------------- */

function ChannelRow({
  channel,
  last,
  onToggle,
  onDelete,
  onRefresh,
  pending,
  fetching,
  notice,
  confirming,
  setConfirming,
}: {
  channel: YoutubeChannel;
  last: boolean;
  onToggle: () => void;
  onDelete: () => void;
  onRefresh: () => void;
  pending: boolean;
  /** A background ingest is running for this channel. */
  fetching: boolean;
  notice?: string;
  confirming: boolean;
  setConfirming: (id: string | null) => void;
}) {
  const subs = fmtSubs(channel.subscriberCount);
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 12,
        padding: "10px 0",
        borderBottom: last ? "none" : "1px solid var(--stroke)",
        // A paused channel is present but visibly not pulling.
        opacity: channel.enabled ? 1 : 0.55,
      }}
    >
      {channel.thumbnail ? (
        // eslint-disable-next-line @next/next/no-img-element -- remote avatar, no loader configured
        <img
          src={channel.thumbnail}
          alt=""
          width={30}
          height={30}
          style={{ borderRadius: 99, flexShrink: 0, objectFit: "cover" }}
        />
      ) : (
        <span
          className="chip mono"
          style={{ width: 30, height: 30, borderRadius: 99, justifyContent: "center", flexShrink: 0, fontSize: 11 }}
        >
          {channel.name.slice(0, 1).toUpperCase()}
        </span>
      )}

      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 12.5, fontWeight: 500, color: "var(--t-hi)" }}>{channel.name}</div>
        <div className="mono" style={{ fontSize: 10, color: "var(--t-lo)", marginTop: 3 }}>
          {[
            channel.handle,
            subs,
            `${channel.videoCount} video${channel.videoCount === 1 ? "" : "s"}`,
            `checked ${fmtWhen(channel.lastPolledAt)}`,
          ]
            .filter(Boolean)
            .join(" · ")}
        </div>
        {fetching && (
          <div
            className="mono"
            style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 10, marginTop: 4, color: "var(--blue-bright)" }}
          >
            <Dot tone="var(--blue-bright)" pulse />
            reading new videos — see the Activity Log
          </div>
        )}
        {channel.lastError && <Notice text={channel.lastError} />}
        {notice && <Notice text={notice} />}
      </div>

      {confirming ? (
        <div style={{ display: "flex", gap: 6 }}>
          <IconButton title="Confirm unfollow" onClick={onDelete} disabled={pending} danger>
            ✓
          </IconButton>
          <IconButton title="Cancel" onClick={() => setConfirming(null)} disabled={pending}>
            ✕
          </IconButton>
        </div>
      ) : (
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <ScanToggle
            on={channel.enabled}
            pending={pending}
            onToggle={onToggle}
            titleOn="Polling on — click to pause"
            titleOff="Polling paused — click to resume"
          />
          <IconButton
            title={fetching ? "Already fetching" : "Check for new videos now"}
            onClick={onRefresh}
            disabled={pending || fetching}
          >
            ⟳
          </IconButton>
          <IconButton
            title="Unfollow channel"
            onClick={() => setConfirming(channel.channelId)}
            disabled={pending}
          >
            🗑
          </IconButton>
        </div>
      )}
    </div>
  );
}

/* ---------------- matches ---------------- */

function MatchRow({ match, last }: { match: YoutubeMatch; last: boolean }) {
  const at = match.timestampStart;
  return (
    <div
      style={{
        padding: "10px 0",
        borderBottom: last ? "none" : "1px solid var(--stroke)",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span
          className="chip mono"
          style={{
            fontSize: 9.5,
            color: "var(--orange-bright)",
            borderColor: "color-mix(in oklch, var(--orange) 40%, transparent)",
          }}
        >
          {match.ticker}
        </span>
        <span className="mono" style={{ fontSize: 9.5, color: "var(--t-faint)" }}>
          {Math.round(match.relevance * 100)}% relevance
        </span>
      </div>
      <a
        href={sourceHref(match.videoUrl, at)}
        target="_blank"
        rel="noreferrer"
        style={{
          display: "block",
          fontSize: 12.5,
          color: "var(--t-hi)",
          lineHeight: 1.45,
          marginTop: 5,
          textDecoration: "none",
        }}
        title={match.title}
      >
        “{match.quote}” ↗
      </a>
      <div className="mono" style={{ fontSize: 10, color: "var(--t-lo)", marginTop: 3 }}>
        {[match.channelName, match.title, at != null && at > 0 ? fmtOffset(at) : null]
          .filter(Boolean)
          .join(" · ")}
      </div>
    </div>
  );
}

/* ---------------- page ---------------- */

export function SourcesYoutube() {
  const [channels, setChannels] = useState<YoutubeChannel[] | null>(null);
  const [matches, setMatches] = useState<YoutubeMatch[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [overlay, setOverlay] = useState<Overlay>({});
  const [pending, setPending] = useState<Record<string, boolean>>({});
  const [notice, setNotice] = useState<Record<string, string>>({});
  const [confirming, setConfirming] = useState<string | null>(null);

  const revalidate = useCallback(async () => {
    try {
      const [c, m] = await Promise.all([
        getYoutubeChannels(),
        getYoutubeMatches({ limit: 50 }),
      ]);
      setChannels(c);
      setMatches(m);
      setLoadError(null);
    } catch (e) {
      setLoadError((e as Error)?.message ?? "Could not load YouTube sources");
      setChannels((prev) => prev ?? []);
    }
  }, []);

  // Channels with an ingest in flight. Cleared when the stream resolves, so the row's
  // indicator tracks the real job rather than a local guess.
  const [fetching, setFetching] = useState<Record<string, boolean>>({});
  const { runLiveJob } = useWtaf();

  /**
   * Follow a background ingest to completion, refreshing the list when it lands.
   *
   * The work belongs to the server, not this component: if the stream drops (navigation,
   * network) the job keeps running and is picked up again by the reattach effect below.
   */
  const followJob = useCallback(
    async (channelId: string, path: string) => {
      setFetching((f) => ({ ...f, [channelId]: true }));
      setNotice((n) => {
        const next = { ...n };
        delete next[channelId];
        return next;
      });
      try {
        // The stream's `result` frame is the backend's raw snake_case payload, so map it
        // rather than annotating it as camelCase and reading undefined fields.
        const raw = await runLiveJob<Parameters<typeof toYoutubeIngestReport>[0]>(path);
        const report = toYoutubeIngestReport(raw);
        if (report.errors.length) {
          setNotice((n) => ({ ...n, [channelId]: report.errors[0] }));
        }
      } catch (e) {
        setNotice((n) => ({ ...n, [channelId]: (e as Error)?.message ?? "Fetch failed" }));
      } finally {
        setFetching((f) => ({ ...f, [channelId]: false }));
        await revalidate();
      }
    },
    [runLiveJob, revalidate],
  );

  // Reattach to ingests still running from a previous page view — a reload mid-backfill
  // should show the work continuing, not an idle row. Runs once per mount.
  const reattachedRef = useRef(false);
  useEffect(() => {
    void revalidate();
    if (reattachedRef.current) return;
    reattachedRef.current = true;
    void getRunningYoutubeJobs()
      .then((jobs) => {
        for (const job of jobs) {
          if (job.channelId) void followJob(job.channelId, jobStreamPath(job.jobId));
        }
      })
      .catch(() => { /* no jobs endpoint / offline — nothing to reattach to */ });
  }, [revalidate, followJob]);

  const clearOverlay = (id: string) =>
    setOverlay((o) => {
      const next = { ...o };
      delete next[id];
      return next;
    });

  /** Mutate → revalidate → drop the overlay; revert and show an inline notice on failure. */
  async function mutate(id: string, optimistic: Overlay[string], run: () => Promise<unknown>) {
    setOverlay((o) => ({ ...o, [id]: { ...o[id], ...optimistic } }));
    setPending((p) => ({ ...p, [id]: true }));
    setNotice((n) => {
      const next = { ...n };
      delete next[id];
      return next;
    });
    try {
      await run();
      await revalidate();
      clearOverlay(id);
    } catch (e) {
      clearOverlay(id);
      setNotice((n) => ({ ...n, [id]: (e as Error)?.message ?? "Action failed" }));
    } finally {
      setPending((p) => ({ ...p, [id]: false }));
      setConfirming(null);
    }
  }

  const rows = (channels ?? []).map((c) => ({ ...c, ...overlay[c.channelId] }));
  const loading = channels === null;

  return (
    <div className="grid12">
      <Card title="Follow a channel" sub="its new videos become council evidence" className="span12">
        <AddChannel
          onFollowed={(channel) => {
            // Show the row straight away, then stream its backfill in the background.
            void revalidate();
            void followJob(
              channel.channelId,
              youtubeRefreshStreamPath(channel.channelId, BACKFILL),
            );
          }}
        />
      </Card>

      <Card
        title="Channels"
        sub={rows.length ? `${rows.filter((c) => c.enabled).length} of ${rows.length} polling` : undefined}
        className="span12"
        loading={loading}
      >
        {loadError && <Notice text={loadError} />}
        {!loading && rows.length === 0 ? (
          <EmptyState
            label="Not following any channels"
            sub="Add a YouTube channel above to start pulling its transcripts"
          />
        ) : (
          <div style={{ display: "flex", flexDirection: "column" }}>
            {rows.map((c, i) => (
              <ChannelRow
                key={c.channelId}
                channel={c}
                last={i === rows.length - 1}
                pending={!!pending[c.channelId]}
                fetching={!!fetching[c.channelId]}
                notice={notice[c.channelId]}
                confirming={confirming === c.channelId}
                setConfirming={setConfirming}
                onToggle={() =>
                  void mutate(c.channelId, { enabled: !c.enabled }, () =>
                    setYoutubeChannelEnabled(c.channelId, !c.enabled),
                  )
                }
                onDelete={() =>
                  void mutate(c.channelId, {}, () => deleteYoutubeChannel(c.channelId))
                }
                onRefresh={() =>
                  void followJob(c.channelId, youtubeRefreshStreamPath(c.channelId))
                }
              />
            ))}
          </div>
        )}
      </Card>

      <Card
        title="Watchlist evidence"
        sub={
          matches.length
            ? `${matches.length} moment${matches.length === 1 ? "" : "s"} matched to your watchlist`
            : undefined
        }
        className="span12"
        loading={loading}
      >
        {!loading && matches.length === 0 ? (
          <EmptyState
            label="No watchlist matches yet"
            sub="When a followed channel discusses a ticker you track, the moment shows up here"
          />
        ) : (
          <div style={{ display: "flex", flexDirection: "column" }}>
            {matches.map((m, i) => (
              <MatchRow
                key={`${m.videoId}-${m.ticker}`}
                match={m}
                last={i === matches.length - 1}
              />
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
