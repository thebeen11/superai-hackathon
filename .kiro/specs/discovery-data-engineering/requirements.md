# Requirements Document

## Introduction

This spec covers **Layer 1 (Discovery)** and **Layer 2 (Data Engineering)** of the Hedge
Fund AI Agent Council — the two lowest layers of the pipeline that turn a single
research-topic query into clean, labelled, source-anchored rows in Postgres. It
deliberately excludes the Analysts, Managers, Chairman, debate loop, backtest, and the
dashboard.

**Layer 1 — Discovery** is already implemented in `backend/app/discovery/` (`agent.py`,
`exa_source.py`, `youtube_source.py`) with shared shapes in `backend/app/models.py`. This
spec **formalizes the existing Discovery behaviour** so it is captured as verifiable
requirements rather than only as code.

**Layer 2 — Data Engineering** (the "Timo" cleaner/labeller) is **not yet built**. This
spec **drives its build**: it receives the `SourceItem`s produced by Discovery, redacts
noise, resolves entities to tickers, assigns MACRO/MICRO and industry labels, tags items
with general market themes, and persists cleaned, labelled rows to Postgres.

Both layers run on the locked architecture: **plain Python**, **AWS-only backend**
(App Runner + RDS Postgres + Bedrock for the MVP), managed with **uv**, exposed via
**FastAPI**. Discovery is plain Python for its fan-out, merge, and dedupe, and uses the
**Bedrock `converse` API** for a single step — refining or clarifying the topic query
before fan-out. Data Engineering is a reasoning layer that uses the **Bedrock `converse`
API** with **Pydantic** schemas. **LangGraph is not used** in either layer.

## Glossary

- **Discovery_Agent**: The Layer 1 component (`backend/app/discovery/agent.py`) that, given a topic query, optionally refines/clarifies it, fans out to source branches, merges results, and dedupes them. Plain Python apart from the LLM-backed Query_Refinement_Skill.
- **Query_Refinement_Skill**: The Discovery step that uses the Bedrock_Converse API to classify a topic query as clear or ambiguous, rewrite a clear-but-rough query for better search, or (in interactive mode) return clarifying questions when the query is too ambiguous.
- **Clarification mode**: The Discovery_Agent setting controlling ambiguous-query handling — `interactive` (pause and return clarifying questions to the Commander) or `auto-proceed` (skip the pause and proceed with a best-effort refined query). Defaults to `interactive`.
- **Exa_Branch**: The Discovery source branch (`exa_source.py`) that performs web search and content crawl via the Exa API.
- **YouTube_Branch**: The Discovery source branch (`youtube_source.py`) that performs video search via the YouTube Data API and fetches captions via `youtube-transcript-api`.
- **Source_Branch**: A generic term for either the Exa_Branch or the YouTube_Branch.
- **SourceItem**: A normalized unit of discovered content (web article or video transcript), defined in `backend/app/models.py`. Carries `source_type`, `title`, `url`, `text`, `author`, `published_at`, `segments`, and `retrieved_at`.
- **TranscriptSegment**: A timestamped slice of a video transcript, with `start` (seconds from start) and `text`.
- **SkippedSource**: A record of a source or branch that could not be ingested, carrying `source_type` and `reason`. Surfaced to the caller, never silently dropped.
- **DiscoveryResult**: The Discovery_Agent output for one topic query, containing the topic `query`, the merged `items` list, and the `skipped` list.
- **Data_Engineering_Agent**: The Layer 2 component ("Timo") that cleans, labels, and persists SourceItems. A reasoning layer using the Bedrock `converse` API.
- **Bedrock_Converse**: The Amazon Bedrock `converse` API (boto3) used by the Data_Engineering_Agent for reasoning, with output validated against a Pydantic schema.
- **Cleaned_Item**: A SourceItem after noise redaction, entity resolution, labelling, and theme assignment — the unit persisted to Postgres.
- **Noise_Redaction_Skill**: The Data Engineering skill that removes advertisement reads and filler text from item content.
- **Entity_Resolution_Skill**: The Data Engineering skill that maps slang and aliases to canonical tickers or entities (e.g. "Zuck"/"Meta"/"FB" → $META; "Powell"/"J-Pow"/"FOMC" → Federal_Reserve).
- **Label_Assignment_Skill**: The Data Engineering skill that tags each item with a MACRO-vs-MICRO label and an industry/sector label.
- **Theme_Assignment_Skill**: The Data Engineering skill that classifies each item against the Market_Theme_Taxonomy and assigns the applicable general market themes.
- **Market_Theme_Taxonomy**: The defined list of general market themes (for example, Healthcare, Technology, Solar, Oil & Gas) that the Theme_Assignment_Skill assigns from. Configured in the backend; not user-managed in this layer.
- **MACRO**: A label indicating economy-wide signal (feeds the dashboard stream in later layers).
- **MICRO**: A label indicating company-specific signal (feeds the stock-pick stream in later layers).
- **Postgres_Store**: The RDS Postgres database (single instance in the MVP) where Cleaned_Items are persisted. No embeddings or vector database in the MVP.
- **source_url**: The originating URL of an item or claim, required on every retained item.
- **timestamp_start**: The start time (seconds from video start) of the transcript segment supporting a video-derived claim, required on video-derived retained items.
- **published_at**: The ISO date a source was published, as provided by the source.
- **ingested_at**: The timestamp at which an item was ingested/persisted by the pipeline.

## Requirements

### Requirement 1: Topic Query Intake (Discovery)

**User Story:** As the Commander, I want to submit a single research-topic query, so that the system finds the relevant sources for me without my having to specify individual URLs or channels.

#### Acceptance Criteria

1. WHEN a topic query containing at least one non-whitespace character is submitted, THE Discovery_Agent SHALL trim leading and trailing whitespace from the query and initiate discovery using the trimmed query.
2. IF a submitted topic query is empty or contains only whitespace characters after trimming, THEN THE Discovery_Agent SHALL reject the query with a validation error indicating the query is empty and SHALL NOT initiate discovery.
3. WHEN a valid topic query is submitted, THE Discovery_Agent SHALL select and query each configured source in parallel autonomously, without requiring the Commander to specify source URLs or channels.
4. IF a submitted topic query exceeds 500 characters after trimming, THEN THE Discovery_Agent SHALL reject the query with a validation error indicating the maximum length is exceeded and SHALL NOT initiate discovery.

### Requirement 2: Query Refinement and Clarification (Discovery)

**User Story:** As the Commander, I want the system to refine a rough topic or ask me to clarify an ambiguous one before searching, so that discovery runs on a well-formed query and returns relevant sources.

#### Acceptance Criteria

1. WHEN a valid trimmed topic query is submitted, THE Query_Refinement_Skill SHALL evaluate the query via the Bedrock_Converse API and SHALL classify it as either clear or ambiguous, returning a result validated against a Pydantic schema.
2. WHERE the query is classified as clear, THE Query_Refinement_Skill SHALL produce a refined query optimized for source search, and THE Discovery_Agent SHALL dispatch the refined query to the Source_Branches.
3. WHERE the Query_Refinement_Skill produces a refined query, THE Discovery_Agent SHALL preserve the original submitted query alongside the refined query so the refinement is auditable.
4. THE Discovery_Agent SHALL accept a clarification mode of either interactive or auto-proceed, and WHERE no mode is provided THE Discovery_Agent SHALL apply the configured default of interactive.
5. IF the query is classified as ambiguous AND the clarification mode is interactive, THEN THE Discovery_Agent SHALL NOT dispatch the query to any Source_Branch and SHALL return one or more clarifying questions to the Commander.
6. IF the query is classified as ambiguous AND the clarification mode is auto-proceed, THEN THE Query_Refinement_Skill SHALL produce a best-effort refined query without returning clarifying questions, and THE Discovery_Agent SHALL dispatch that refined query to the Source_Branches and SHALL record that it proceeded without clarification.
7. WHEN the Commander submits a clarified query in response to the clarifying questions, THE Discovery_Agent SHALL re-run the Query_Refinement_Skill on the clarified query.
8. THE Discovery_Agent SHALL limit interactive clarification to a configured maximum number of rounds (default 2), and WHERE that maximum is reached THE Discovery_Agent SHALL proceed to fan-out using the most recent query.
9. IF the Bedrock_Converse call for query refinement fails after its configured retries, THEN THE Discovery_Agent SHALL fall back to dispatching the original trimmed query to the Source_Branches and SHALL record the refinement failure as a non-fatal reason.

### Requirement 3: Parallel Source Fan-Out (Discovery)

**User Story:** As the Commander, I want one query fanned out across web and video sources in parallel, so that discovery is fast and covers multiple source types.

#### Acceptance Criteria

1. WHEN discovery runs for a topic query, THE Discovery_Agent SHALL dispatch the query to the Exa_Branch and the YouTube_Branch so that both branches execute concurrently and the total fan-out wall-clock time does not exceed the running time of the slowest branch plus 1 second of scheduling overhead.
2. WHEN the Exa_Branch runs, THE Exa_Branch SHALL perform a web search returning at most the effective maximum-results-per-source count and SHALL crawl the textual content of each returned result into the SourceItem text field.
3. WHEN the YouTube_Branch runs, THE YouTube_Branch SHALL search for at most the effective maximum-results-per-source videos via the YouTube Data API and SHALL fetch captions for each returned video via the caption API.
4. WHEN the YouTube_Branch fetches captions for a video, THE YouTube_Branch SHALL store each caption line as a TranscriptSegment carrying a start time expressed as a non-negative number of seconds (greater than or equal to 0) measured from the video start and the corresponding non-empty segment text.
5. THE Discovery_Agent SHALL accept an optional maximum-results-per-source limit as an integer between 1 and 50 inclusive, and WHERE no limit is provided THE Discovery_Agent SHALL apply the configured default of 5 results per source.
6. IF a provided maximum-results-per-source limit is not an integer between 1 and 50 inclusive, THEN THE Discovery_Agent SHALL reject the request with a validation error and SHALL not dispatch the query to any Source_Branch.

### Requirement 4: Merge and Deduplicate (Discovery)

**User Story:** As the Commander, I want results from all sources merged into one normalized list without duplicates, so that downstream layers see a single clean set of sources.

#### Acceptance Criteria

1. WHEN all Source_Branches complete, THE Discovery_Agent SHALL merge their SourceItems into a single DiscoveryResult items list, preserving the relative order in which the items were collected from the branches.
2. WHEN merging SourceItems, THE Discovery_Agent SHALL compare each item's source_url as an exact, case-sensitive, full-string match against the source_urls of all already-included items, and SHALL exclude any item whose source_url matches an already-included item.
3. WHERE two or more SourceItems share the same source_url, THE Discovery_Agent SHALL retain only the first-encountered item in collection order and SHALL discard each subsequent matching item.
4. THE Discovery_Agent SHALL represent web results and video results using the same SourceItem shape, distinguished only by the value of the source_type field.
5. WHEN discovery completes, THE DiscoveryResult SHALL report a retained-item count equal to the number of items remaining in the items list after deduplication.

### Requirement 5: Skip-With-Reason Failure Handling (Discovery)

**User Story:** As the Commander, I want a missing key or a caption-less video to be skipped and surfaced rather than crashing the run, so that I always get whatever signal is available.

#### Acceptance Criteria

1. IF a Source_Branch cannot run because its required API key is missing, THEN THE Discovery_Agent SHALL record a SkippedSource carrying that branch's source_type and a non-empty, human-readable reason that identifies the missing key, and SHALL continue the run with the remaining branches.
2. IF a Source_Branch raises an unexpected error, THEN THE Discovery_Agent SHALL record a SkippedSource carrying that branch's source_type and a non-empty, human-readable reason, and SHALL continue the run with the remaining branches without propagating the error.
3. IF a discovered video has no available captions, where "no available captions" means no caption track exists or the fetched transcript yields zero non-whitespace TranscriptSegments, THEN THE YouTube_Branch SHALL exclude that video from its items list and SHALL continue processing the remaining videos.
4. WHEN discovery completes, THE DiscoveryResult SHALL include every recorded SkippedSource alongside the retained items, with exactly one SkippedSource entry recorded per skipped branch.
5. WHEN an Exa or YouTube result contains no usable text content, where "no usable text content" means the item text is empty or contains only whitespace, THE corresponding Source_Branch SHALL exclude that result from the items list.
6. WHEN discovery completes and every Source_Branch was skipped, THE Discovery_Agent SHALL return a DiscoveryResult containing an empty items list and one SkippedSource per skipped branch, and SHALL complete without raising an error.

### Requirement 6: Source Provenance and Staleness Metadata (Discovery)

**User Story:** As the Commander, I want every discovered item to carry its origin and timing metadata, so that downstream layers can audit and age-weight the evidence.

#### Acceptance Criteria

1. THE Discovery_Agent SHALL populate every retained SourceItem with a non-empty source_url that identifies the origin of the item.
2. WHERE a video SourceItem is produced, THE YouTube_Branch SHALL populate it with TranscriptSegments, each carrying a timestamp_start expressed as a non-negative number of seconds from the start of the video and the corresponding non-empty segment text.
3. WHERE a source provides a publication date, THE producing Source_Branch SHALL populate the SourceItem published_at field with that date formatted as an ISO 8601 date.
4. IF a source provides no publication date, THEN THE producing Source_Branch SHALL leave the SourceItem published_at field unset (null) and SHALL retain the item.
5. THE Discovery_Agent SHALL record a retrieved_at value as a UTC timestamp on every SourceItem at the time of ingestion.
6. IF a candidate SourceItem has a missing or empty source_url, THEN THE Discovery_Agent SHALL exclude that item from the retained items list.

### Requirement 7: Receive Discovery Output (Data Engineering)

**User Story:** As Timo the data engineer, I want to receive the discovered SourceItems, so that I can begin cleaning and labelling them.

#### Acceptance Criteria

1. WHEN a DiscoveryResult is received as input, THE Data_Engineering_Agent SHALL accept its SourceItems list and begin processing the items in that list.
2. WHILE processing a SourceItems list, THE Data_Engineering_Agent SHALL process each SourceItem independently such that the outcome of processing any one item does not halt or alter the processing of the remaining items.
3. IF processing of an individual SourceItem fails, THEN THE Data_Engineering_Agent SHALL record a failure entry carrying that item's source_url and a non-empty, human-readable reason, SHALL exclude that item from persistence, and SHALL continue processing the remaining items.
4. IF the input SourceItems list is empty, THEN THE Data_Engineering_Agent SHALL complete without persisting any rows and SHALL report a processed-item count of zero.
5. WHEN processing of all SourceItems in the input list completes, THE Data_Engineering_Agent SHALL report the count of successfully persisted items and the count of failed items.

### Requirement 8: Noise Redaction (Data Engineering)

**User Story:** As Timo, I want advertisement reads and filler removed from each item, so that downstream analysis works on signal rather than noise.

#### Acceptance Criteria

1. WHEN the Data_Engineering_Agent processes a SourceItem, THE Noise_Redaction_Skill SHALL remove advertisement reads (promotional or sponsorship passages) and filler content (greetings, sign-offs, and non-financial conversational asides) from the item text and SHALL produce redacted item text.
2. THE Noise_Redaction_Skill SHALL retain in the redacted item text every passage of the original item text that conveys financial or investment signal, where signal content is any passage referencing a company, ticker, market, macro-economic indicator, or investment decision.
3. WHERE a video SourceItem carries TranscriptSegments, THE Noise_Redaction_Skill SHALL preserve, for each surviving passage of redacted text, the timestamp_start of the TranscriptSegment from which that passage originated.
4. IF the redacted item text produced by the Noise_Redaction_Skill is empty or contains only whitespace characters (the entire item was noise), THEN THE Data_Engineering_Agent SHALL exclude that SourceItem from further processing and from persistence, and SHALL record the exclusion with a non-empty, human-readable reason indicating the item contained no retained signal content.

### Requirement 9: Entity Resolution (Data Engineering)

**User Story:** As Timo, I want slang and aliases mapped to canonical tickers, so that mentions of the same entity are consistently identified across sources.

#### Acceptance Criteria

1. WHEN the Data_Engineering_Agent processes a SourceItem, THE Entity_Resolution_Skill SHALL map every recognized company slang or alias occurrence in the item text to its canonical ticker (for example, "Zuck", "Meta", and "FB" map to $META).
2. WHEN the Data_Engineering_Agent processes a SourceItem, THE Entity_Resolution_Skill SHALL map every recognized macro-entity alias occurrence in the item text to its canonical entity (for example, "Powell", "J-Pow", and "FOMC" map to Federal_Reserve).
3. WHEN a SourceItem text contains aliases for two or more distinct entities, THE Entity_Resolution_Skill SHALL resolve each distinct entity and SHALL attach the complete set of resolved canonical entities to the Cleaned_Item, with each distinct canonical entity represented exactly once regardless of how many aliases mapped to it.
4. IF a SourceItem text contains no recognized company alias and no recognized macro-entity alias, THEN THE Entity_Resolution_Skill SHALL attach an empty resolved-entity set to the Cleaned_Item and SHALL retain the item.
5. IF a token or phrase in the item text is not a recognized company or macro-entity alias, THEN THE Entity_Resolution_Skill SHALL NOT map it to any canonical ticker or entity.

### Requirement 10: Label Assignment (Data Engineering)

**User Story:** As Timo, I want each item tagged MACRO or MICRO and tagged with an industry, so that later layers can route the item to the correct stream.

#### Acceptance Criteria

1. WHEN the Data_Engineering_Agent processes a SourceItem, THE Label_Assignment_Skill SHALL assign exactly one of the labels MACRO or MICRO to the item.
2. WHEN the Data_Engineering_Agent processes a SourceItem, THE Label_Assignment_Skill SHALL assign exactly one industry label, selected from the project's defined sector list (for example, Technology, Financials, Energy), as the item's primary industry.
3. WHERE a SourceItem's content matches more than one sector in the project's defined sector list, THE Label_Assignment_Skill SHALL assign the single most prominent sector as the primary industry label and SHALL NOT assign more than one industry label.
4. IF the Label_Assignment_Skill cannot match a SourceItem to any sector in the project's defined sector list, THEN THE Label_Assignment_Skill SHALL assign an "Unclassified" industry label and SHALL retain the item.
5. THE Label_Assignment_Skill SHALL attach the assigned MACRO/MICRO label and the industry label to the Cleaned_Item.

### Requirement 11: Theme Assignment (Data Engineering)

**User Story:** As Timo, I want each item tagged with general market themes, so that items are grouped by the broad investment themes the council tracks.

#### Acceptance Criteria

1. WHEN the Data_Engineering_Agent processes a SourceItem, THE Theme_Assignment_Skill SHALL classify the item against the defined Market_Theme_Taxonomy (for example, Healthcare, Technology, Solar, Oil & Gas) and assign each applicable theme.
2. WHERE a SourceItem's content matches two or more themes in the Market_Theme_Taxonomy, THE Theme_Assignment_Skill SHALL assign all matching distinct themes, with each distinct theme represented at most once.
3. WHERE a SourceItem matches no theme in the Market_Theme_Taxonomy, THE Theme_Assignment_Skill SHALL assign no theme and SHALL retain the item.
4. THE Theme_Assignment_Skill SHALL assign only themes that exist in the defined Market_Theme_Taxonomy and SHALL NOT invent a theme outside it.
5. THE Theme_Assignment_Skill SHALL attach the assigned themes to the Cleaned_Item.

### Requirement 12: Bedrock Reasoning with Schema Enforcement (Data Engineering)

**User Story:** As an engineer, I want Data Engineering reasoning to run through the Bedrock converse API with enforced output schemas, so that the layer is AWS-native and produces structured, validated output.

#### Acceptance Criteria

1. WHERE a Data Engineering skill requires reasoning, THE Data_Engineering_Agent SHALL invoke the Bedrock_Converse API to perform that reasoning.
2. WHEN the Bedrock_Converse API returns a result, THE Data_Engineering_Agent SHALL validate the result against the Pydantic schema defined for that skill.
3. IF the Bedrock_Converse result fails Pydantic schema validation, THEN THE Data_Engineering_Agent SHALL retry the request up to 3 additional attempts (4 attempts total for the item).
4. IF a Bedrock_Converse request fails with a transient service error (for example, throttling or timeout), THEN THE Data_Engineering_Agent SHALL retry the request up to 3 additional attempts (4 attempts total for the item).
5. IF the retry attempts for an item are exhausted, THEN THE Data_Engineering_Agent SHALL mark the item as failed, SHALL preserve the original SourceItem without persisting a partial Cleaned_Item, and SHALL surface the failure with a non-empty, human-readable reason distinguishing a schema-validation failure from a transient service error.
6. THE Data_Engineering_Agent SHALL perform its reasoning without using LangGraph and without using a general agent framework.

### Requirement 13: No-Orphan-Data Hallucination Guardrail (Data Engineering)

**User Story:** As the Commander, I want every retained item and claim to be traceable to a source, so that I can audit the system and trust that nothing was fabricated.

#### Acceptance Criteria

1. THE Data_Engineering_Agent SHALL retain on every Cleaned_Item a non-empty source_url that exactly matches the source_url of the originating SourceItem.
2. WHERE a Cleaned_Item is derived from a video, THE Data_Engineering_Agent SHALL retain on each claim derived from that video a timestamp_start expressed as a non-negative number of seconds (greater than or equal to 0) measured from the start of the video and corresponding to the TranscriptSegment that supports the claim.
3. IF a Cleaned_Item or claim has a missing or empty source_url, OR a video-derived claim has a missing or negative timestamp_start, THEN THE Data_Engineering_Agent SHALL drop that item or claim before persistence, SHALL NOT persist the dropped item or claim to the Postgres_Store, and SHALL surface the dropped item or claim with a non-empty, human-readable reason identifying the missing source_url or timestamp_start.
4. IF the text of a claim is not present in the originating SourceItem text (for a video-derived claim, in the text of the TranscriptSegment at the associated timestamp_start), THEN THE Data_Engineering_Agent SHALL drop that claim before persistence, SHALL NOT persist the dropped claim to the Postgres_Store, and SHALL surface the dropped claim with a non-empty, human-readable reason indicating the content was not found in the source.

### Requirement 14: Staleness Metadata (Data Engineering)

**User Story:** As the Commander, I want every persisted item to carry publication and ingestion timing, so that later layers can weight evidence by freshness.

#### Acceptance Criteria

1. WHERE a source provided a publication date, THE Data_Engineering_Agent SHALL persist the published_at value on the Cleaned_Item formatted as an ISO 8601 date.
2. IF a source provided no publication date, THEN THE Data_Engineering_Agent SHALL persist the Cleaned_Item with a null published_at value and SHALL retain the item.
3. WHEN a Cleaned_Item is persisted, THE Data_Engineering_Agent SHALL set its ingested_at value to the UTC timestamp at the moment of persistence.
4. THE Data_Engineering_Agent SHALL persist a non-null ingested_at timestamp on every Cleaned_Item.

### Requirement 15: Persistence to Postgres (Data Engineering)

**User Story:** As Timo, I want cleaned and labelled rows persisted to Postgres, so that downstream layers can query the prepared data.

#### Acceptance Criteria

1. WHEN a SourceItem has been cleaned, entity-resolved, labelled, and theme-assigned, THE Data_Engineering_Agent SHALL persist the resulting Cleaned_Item as exactly one row in the Postgres_Store.
2. THE Data_Engineering_Agent SHALL persist Cleaned_Items to plain Postgres without using embeddings or a vector database.
3. THE persisted Cleaned_Item row SHALL include the source_url, the MACRO/MICRO label, the industry label, the assigned themes, the resolved entities, the published_at value where the source provided one (and an unset/null value otherwise), and the ingested_at timestamp.
4. WHERE a Cleaned_Item is derived from a video, THE persisted row SHALL include the timestamp_start, expressed as a non-negative number of seconds (greater than or equal to 0) from the video start, for each retained claim.
5. IF a Cleaned_Item whose source_url already matches a row persisted in the Postgres_Store is submitted for persistence, THEN THE Data_Engineering_Agent SHALL update the existing row in place rather than insert a new row, so that exactly one row per unique source_url exists in the Postgres_Store.
6. IF a write to the Postgres_Store fails, THEN THE Data_Engineering_Agent SHALL roll back the write so that no partial row is persisted for that Cleaned_Item, SHALL mark the item as failed and surface it to the caller with a non-empty, human-readable reason, and SHALL continue persisting the remaining items.

### Requirement 16: Platform and Tooling Constraints

**User Story:** As an engineer, I want both layers built on the locked AWS-only stack and tooling, so that the implementation matches the project's architecture decisions.

#### Acceptance Criteria

1. THE Discovery_Agent and Data_Engineering_Agent SHALL run as components of a single FastAPI backend service, both reachable through that service's interface.
2. THE backend service SHALL declare and resolve all of its Python dependencies through uv, with every dependency pinned to an exact version in a uv-managed lock file.
3. THE backend service SHALL target an AWS-only MVP deployment that uses AWS App Runner for compute, AWS RDS Postgres for storage, and Amazon Bedrock for reasoning, and SHALL use no other compute, storage, or reasoning provider.
4. THE backend service SHALL NOT depend on any non-AWS third-party SaaS provider (for example, Pinecone, Supabase, or OpenAI) for its compute, storage, or reasoning functions, with the exception of the discovery source providers (the Exa API, the YouTube Data API, and the caption API) used by the Source_Branches for content retrieval.
5. WHEN the Discovery_Agent fans out to sources, merges, and deduplicates results, THE Discovery_Agent SHALL perform those steps using plain Python only and SHALL NOT invoke any LLM.
6. THE Discovery_Agent SHALL invoke an LLM only for the Query_Refinement_Skill, and SHALL do so via the Amazon Bedrock_Converse API.
