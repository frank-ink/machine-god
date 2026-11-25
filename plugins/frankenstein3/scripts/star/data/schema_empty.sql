-- PHASE 19: schema-only dump of unified.db (structure only, zero rows).
-- Used by star_cli.py::_emptiness_db_generate() as the last-resort bootstrap when
-- unified.db is missing and no pointer/fallback-copy/snapshot could be
-- found (self-healing, PHASE 19 point 5).
--
-- Regeneration recipe (needed after any real schema change -- new table,
-- new column, new index/trigger/FTS5 virtual table): a plain `sqlite3
-- unified.db ".schema"` dump does NOT work as-is here -- it includes
-- `sqlite_sequence` (auto-created by AUTOINCREMENT) and FTS5 shadow tables
-- (`<name>_data/_idx/_docsize/_config/_content`, auto-created by their
-- `CREATE VIRTUAL TABLE ... USING fts5(...)` statement) as literal CREATE
-- TABLE statements -- replaying those verbatim fails with sqlite3's
-- "object name reserved for internal use" (found empirically building this
-- file). Filter them out first:
--
--   python3 - <<'EOF'
--   import sqlite3
--   c = sqlite3.connect("unified.db")
--   rows = c.execute("SELECT type, name, sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY rowid").fetchall()
--   vtabs = [n for t, n, s in rows if t == "table" and s.strip().upper().startswith("CREATE VIRTUAL TABLE")]
--   shadow = {v + suf for v in vtabs for suf in ("_data", "_idx", "_docsize", "_config", "_content")}
--   out = [s.strip() + ";" for t, n, s in rows
--          if n != "sqlite_sequence" and not n.startswith("sqlite_") and n not in shadow]
--   open("data/schema_empty.sql", "w", encoding="utf-8").write(
--       "-- (this header)\nPRAGMA foreign_keys=OFF;\n\n" + "\n".join(out) + "\n")
--   EOF
--
-- Verify after regenerating: `sqlite3 /tmp/t.db < data/schema_empty.sql &&
-- sqlite3 /tmp/t.db "PRAGMA integrity_check;"` must print `ok`.
PRAGMA foreign_keys=OFF;

CREATE TABLE active_turns(session_id TEXT PRIMARY KEY REFERENCES sessions(session_id),user_id TEXT NOT NULL REFERENCES users(user_id),turn_id TEXT NOT NULL UNIQUE REFERENCES turns(turn_id),episode_id TEXT NOT NULL UNIQUE REFERENCES workspace_episodes(episode_id),causal_id TEXT NOT NULL UNIQUE,generation INTEGER NOT NULL,resource_refs TEXT NOT NULL DEFAULT '[]',effect_id TEXT REFERENCES effects(effect_id),outcome TEXT,workspace_selected INTEGER NOT NULL DEFAULT 0,started_at REAL NOT NULL);
CREATE TABLE enrichment (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            article_id   TEXT NOT NULL,
            source_url   TEXT,
            kind          TEXT,
            excerpt       TEXT,
            fetched_at    TEXT,
            hash         TEXT
        );
CREATE TABLE architect_engine_log(log_id TEXT PRIMARY KEY,ts REAL NOT NULL,process TEXT NOT NULL,engine TEXT NOT NULL,lane TEXT,model TEXT,glm_failed_reason TEXT,duration_ms REAL);
CREATE TABLE architect_engine_state(id INTEGER PRIMARY KEY CHECK(id=1),glm_confirmed INTEGER NOT NULL DEFAULT 0,series_error INTEGER NOT NULL DEFAULT 0,last_updated REAL);
CREATE TABLE article (
            id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            title TEXT,
            source TEXT,
            source_hash TEXT,
            date TEXT,
            metadata TEXT,       -- JSON, verbatim source metadata
            open_questions TEXT,   -- JSON array
            evidenced INTEGER,
            generated_at TEXT
        , thin INTEGER DEFAULT 0, last_processed TEXT, time_source TEXT, host TEXT, last_from TEXT, from_source TEXT, logical_id TEXT, id_source TEXT, epistemic_class TEXT, status TEXT, scope TEXT, tags TEXT, confidence REAL, project TEXT, project_kind TEXT, sphere TEXT, origin TEXT DEFAULT 'measured' CHECK (origin IN ('measured','user')), expire INTEGER DEFAULT 0, protected INTEGER DEFAULT 0);
CREATE TABLE article_sphere (
            article_id TEXT NOT NULL,
            sphere TEXT NOT NULL,
            evidence TEXT,
            PRIMARY KEY (article_id, sphere)
        );
CREATE TABLE article_search_text (
                id INTEGER PRIMARY KEY,
                article_id TEXT NOT NULL UNIQUE,
                title TEXT,
                text TEXT,
                bubble TEXT,
                indexed TEXT NOT NULL
            );
CREATE TABLE lane_position (
        key TEXT PRIMARY KEY, value TEXT NOT NULL, time TEXT NOT NULL);
CREATE TABLE lane_run (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        time TEXT NOT NULL, kind TEXT NOT NULL, lane TEXT, model TEXT,
        goal_id TEXT, duration_ms REAL, http INTEGER,
        token_on INTEGER, token_off INTEGER,
        result TEXT NOT NULL,        -- accepted | rejected | error
        verification TEXT,                 -- why rejected
        answer TEXT
    );
CREATE TABLE lane_livestreak(
  lane TEXT PRIMARY KEY,
  series INTEGER NOT NULL DEFAULT 0,
  last_error REAL,
  last_result TEXT
);
CREATE TABLE lane_usage(
  lane TEXT NOT NULL,
  process TEXT NOT NULL,
  tag TEXT NOT NULL,
  inquiries INTEGER NOT NULL DEFAULT 0,
  token INTEGER NOT NULL DEFAULT 0,
  error INTEGER NOT NULL DEFAULT 0,
  finally REAL NOT NULL,
  PRIMARY KEY(lane, process, tag)
);
CREATE TABLE processing (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        article_id TEXT NOT NULL,
        field TEXT NOT NULL,
        alt_value TEXT,
        new_value TEXT,
        author TEXT,
        time TEXT NOT NULL,
        origin TEXT NOT NULL DEFAULT 'user' CHECK (origin = 'user')
    );
CREATE TABLE causal_episodes(causal_id TEXT PRIMARY KEY,episode_id TEXT REFERENCES workspace_episodes(episode_id),effect_id TEXT REFERENCES effects(effect_id),observation_turn_id TEXT REFERENCES turns(turn_id),outcome_hash TEXT,credit REAL NOT NULL DEFAULT 0,reentered INTEGER NOT NULL DEFAULT 0,ts REAL NOT NULL);
CREATE TABLE checkpoints(checkpoint_id TEXT PRIMARY KEY,ts REAL NOT NULL,state_hash TEXT NOT NULL,note TEXT NOT NULL);
CREATE TABLE file (
                id INTEGER PRIMARY KEY,
                checksum TEXT NOT NULL UNIQUE,
                title TEXT,                 -- Filename of the FIRST seen find location (display only)
                kind TEXT NOT NULL,          -- 'text' | 'binary'
                full_text_indexed INTEGER NOT NULL DEFAULT 0,
                size INTEGER,
                text TEXT,                  -- Full text, stored ONCE
                indexed TEXT NOT NULL
            );
CREATE TABLE durable_memory(memory_id TEXT PRIMARY KEY,kind TEXT NOT NULL,subject TEXT NOT NULL,value TEXT NOT NULL,source_turn_id TEXT REFERENCES turns(turn_id),user_id TEXT,ts REAL NOT NULL,provenance TEXT NOT NULL);
CREATE TABLE effects(effect_id TEXT PRIMARY KEY,episode_id TEXT REFERENCES workspace_episodes(episode_id),user_id TEXT NOT NULL,capability TEXT NOT NULL,target TEXT NOT NULL,argv TEXT,requested_generation INTEGER NOT NULL,status TEXT NOT NULL,outcome TEXT,ts REAL NOT NULL,verified_at REAL);
CREATE TABLE entityos_work_package (
  work_package_id   TEXT PRIMARY KEY,
  orderer  TEXT NOT NULL,          -- gabriel | user-b, from the tested state
  session_id TEXT NOT NULL,
  task    TEXT NOT NULL,          -- Caveman: what needs to be done
  target      TEXT,                   -- the thing: file, service, table
  why      TEXT,                   -- the justification, so a human can verify
  stand      TEXT NOT NULL,          -- open | running | finished | failed | rejected
  result   TEXT,
  evidence      TEXT,                   -- WITH WHAT does the executor prove it is done
  created   REAL NOT NULL,
  changed  REAL NOT NULL
);
CREATE TABLE entityos_article_assignment(
  article_id TEXT PRIMARY KEY,
  belongs TEXT NOT NULL,           -- gabriel | user-b | together | unknown
  reason TEXT NOT NULL,
  security REAL NOT NULL,        -- 0..1
  captured REAL NOT NULL
);
CREATE TABLE entityos_successes(
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL,               -- success | failure
  title TEXT NOT NULL,
  effect TEXT,                    -- what it specifically changed
  evidence TEXT NOT NULL,             -- Measurement/observation. No entry without evidence.
  belongs TEXT,                    -- gabriel | user-b | together
  since_zero INTEGER NOT NULL DEFAULT 0,
  date TEXT NOT NULL,
  captured REAL NOT NULL
);
CREATE TABLE entityos_profile(
  user_id TEXT NOT NULL,
  field TEXT NOT NULL,
  value TEXT NOT NULL,
  origin TEXT NOT NULL,          -- owner | iar.frank.ink | derived | measured
  evidence TEXT,
  captured REAL NOT NULL,
  PRIMARY KEY(user_id, field)
);
CREATE TABLE entityos_projects(
  project TEXT PRIMARY KEY,
  belongs TEXT,                    -- gabriel | user-b | together
  built_from TEXT,                 -- may differ: possession is not authorship
  stand TEXT NOT NULL,             -- running | completed | failed | resting
  success TEXT,                     -- successful | not_successful | open
  since_zero INTEGER NOT NULL DEFAULT 0,
  description TEXT,
  evidence TEXT,
  origin TEXT NOT NULL,
  captured REAL NOT NULL
);
CREATE TABLE entityos_hosts(
  host TEXT PRIMARY KEY,
  belongs_to TEXT,
  first_review REAL NOT NULL,
  last_seen REAL NOT NULL,
  generation INTEGER,
  healthy INTEGER NOT NULL DEFAULT 0,
  boot_id TEXT,
  module TEXT NOT NULL DEFAULT '{}',
  source TEXT NOT NULL DEFAULT 'heartbeat'
);
CREATE TABLE eos_architect_receipts(receipt_id TEXT PRIMARY KEY,ts REAL NOT NULL,hypothesis_id TEXT NOT NULL,hypothesis_source TEXT NOT NULL,hypothesis_text TEXT NOT NULL,branch TEXT,reproduced INTEGER NOT NULL,finding TEXT,safer_frame INTEGER,frame_reason TEXT,test_bed_before TEXT,test_bed_afterwards TEXT,not_worse INTEGER,not_worse_reason TEXT,report_before_hash TEXT,report_afterwards_hash TEXT,canary_status TEXT,judgment TEXT NOT NULL,live_switched INTEGER NOT NULL DEFAULT 0,hint TEXT);
CREATE TABLE eos_evaluations(evaluation_id TEXT PRIMARY KEY,turn_id TEXT NOT NULL,session_id TEXT NOT NULL,user_id TEXT NOT NULL,value INTEGER NOT NULL CHECK(value IN (-1,1)),question_turn_id TEXT,question_hash TEXT,question_length INTEGER,answer_hash TEXT NOT NULL,answer_length INTEGER NOT NULL,model TEXT,ts REAL NOT NULL,UNIQUE(turn_id, user_id));
CREATE TABLE eos_bug_hypotheses(bug_id TEXT PRIMARY KEY,user_id TEXT NOT NULL,ts REAL NOT NULL,description TEXT NOT NULL,wo TEXT,status TEXT NOT NULL DEFAULT 'OPEN' CHECK(status IN ('OPEN','REPRODUCED','REFUTED','FIXED')),finding TEXT);
CREATE TABLE error (
            id TEXT PRIMARY KEY,
            kind TEXT NOT NULL CHECK (kind IN ('sql', 'shell', 'python', 'data', 'provenance', 'method')),
            trigger_pattern TEXT NOT NULL,
            was_happened TEXT NOT NULL,
            how_recognized TEXT NOT NULL,
            how_avoided TEXT NOT NULL,
            severity TEXT NOT NULL CHECK (severity IN ('high', 'medium', 'low')),
            evidence TEXT NOT NULL,
            source TEXT NOT NULL,
            recognized_at TEXT,
            confirmed_through TEXT
        );
CREATE TABLE conclusion (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kind TEXT NOT NULL CHECK (kind IN ('hypothesis','implication','lesson')),
            statement TEXT NOT NULL,
            reasoning TEXT,
            applies_for TEXT NOT NULL,
            author TEXT,
            time TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','supported','refuted','resolved')),
            refuted_through INTEGER REFERENCES conclusion(id)
        , confidence REAL);
CREATE TABLE conclusion_evidence (
            conclusion_id INTEGER NOT NULL REFERENCES conclusion(id),
            evidence_kind TEXT NOT NULL CHECK (evidence_kind IN
                ('protocol','article','measurement','problem','edge','file')),
            evidence_id TEXT NOT NULL,
            PRIMARY KEY (conclusion_id, evidence_kind, evidence_id)
        );
CREATE VIRTUAL TABLE fts_index_article USING fts5(title, text, content='article_search_text', content_rowid='id');
CREATE VIRTUAL TABLE fts_index_file USING fts5(title, text, content='file', content_rowid='id');
CREATE TABLE find_location (
                file_id INTEGER NOT NULL,  -- FK on file.id (robuster Join)
                checksum TEXT NOT NULL,   -- as requested by the owner, for display/direct query
                host TEXT NOT NULL,
                path TEXT NOT NULL,
                bubble TEXT,                 -- NULL = Kern/unlimited
                changed TEXT,
                PRIMARY KEY (host, path)
            );
CREATE TABLE memory_yield(  id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL,  turn_id TEXT, role TEXT, lane TEXT, model TEXT,  taken INTEGER NOT NULL, discarded INTEGER NOT NULL, reasons TEXT);
CREATE TABLE tombstone (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        activity TEXT NOT NULL,
        goal_id TEXT NOT NULL,
        author TEXT,
        time TEXT NOT NULL,
        reason TEXT,
        content_hash TEXT NOT NULL
    );
CREATE TABLE graph_edges(edge_id TEXT PRIMARY KEY,src TEXT NOT NULL,dst TEXT NOT NULL,kind TEXT NOT NULL,provenance TEXT NOT NULL);
CREATE TABLE graph_edge(
            source_node_id TEXT NOT NULL,
            target_node_id TEXT NOT NULL,
            edge_type TEXT NOT NULL,
            weight REAL NOT NULL DEFAULT 1.0,
            confidence REAL,
            graph_epoch INTEGER NOT NULL,
            source_edge_kind TEXT NOT NULL,
            evidence TEXT,
            built_at TEXT NOT NULL, expire INTEGER, protected INTEGER,
            PRIMARY KEY(source_node_id, target_node_id, edge_type)
        ) WITHOUT ROWID;
CREATE TABLE graph_node(
            node_id TEXT PRIMARY KEY,
            node_type TEXT NOT NULL,
            external_id TEXT NOT NULL,
            title TEXT,
            source TEXT,
            source_content_hash TEXT,
            date TEXT,
            metadata TEXT,
            graph_epoch INTEGER NOT NULL,
            built_at TEXT NOT NULL
        , status TEXT, expire INTEGER, protected INTEGER);
CREATE TABLE graph_meta(
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
CREATE TABLE graph_nodes(node_id TEXT PRIMARY KEY,kind TEXT NOT NULL,label TEXT NOT NULL,source_table TEXT NOT NULL,source_id TEXT NOT NULL);
CREATE TABLE gw_intention(  id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL,  turn_id TEXT, session_id TEXT, question TEXT,  tools TEXT, external_effect TEXT, announced TEXT,  suspicion TEXT, reason TEXT);
CREATE TABLE gw_broadcast(  id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL,  turn_id TEXT, session_id TEXT, article_id TEXT, value REAL);
CREATE TABLE gw_origin(  memory_id TEXT PRIMARY KEY, turn_id TEXT, session_id TEXT, ts REAL NOT NULL,  foreign_text INTEGER NOT NULL DEFAULT 0, tools TEXT);
CREATE TABLE gw_learning(  feature TEXT NOT NULL, article_id TEXT NOT NULL,  boost REAL NOT NULL DEFAULT 0, n INTEGER NOT NULL DEFAULT 0,  rewarded INTEGER NOT NULL DEFAULT 0, ts REAL NOT NULL,  PRIMARY KEY(feature, article_id));
CREATE TABLE gw_competition(  id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL,  turn_id TEXT, session_id TEXT, article_id TEXT, rang INTEGER,  salience REAL, relevance REAL, novelty REAL, value REAL,  approved INTEGER, chosen INTEGER);
CREATE TABLE home_evidence(evidence_id TEXT PRIMARY KEY, ts REAL NOT NULL, effect_id TEXT, causal_id TEXT,user_id TEXT NOT NULL, host TEXT NOT NULL, action TEXT NOT NULL,payload_sha256 TEXT NOT NULL, judgment TEXT NOT NULL);
CREATE TABLE edge (
            src TEXT NOT NULL,
            dst TEXT NOT NULL,
            kind TEXT NOT NULL,    -- which source field produced this edge
            evidence TEXT, confidence REAL, generated_at TEXT, time_source TEXT, expire INTEGER DEFAULT 0, protected INTEGER DEFAULT 0,           -- provenance: source path of the asserting article
            PRIMARY KEY (src, dst, kind)
        );
CREATE TABLE kb_task (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            process           TEXT NOT NULL,
            payload          TEXT NOT NULL,
            state           TEXT NOT NULL DEFAULT 'open'
                              CHECK (state IN ('open','running','finished','unusable')),
            attempts          INTEGER NOT NULL DEFAULT 0,
            last_reason     TEXT,
            blocked_lanes  TEXT,
            created          TEXT NOT NULL,
            changed         TEXT NOT NULL,
            -- inoperable WITHOUT reason is forbidden: otherwise no one knows anymore,
            -- why something was left lying, and the order is effectively lost.
            CHECK (state <> 'unusable'
                   OR (last_reason IS NOT NULL AND TRIM(last_reason) <> ''))
        );
CREATE TABLE kb_booking (
            id                    INTEGER PRIMARY KEY AUTOINCREMENT,
            time                   TEXT NOT NULL,
            account                   TEXT NOT NULL REFERENCES kb_account(account),
            access                   TEXT NOT NULL REFERENCES kb_access(access),
            amount                    REAL NOT NULL CHECK (amount >= 0),
            unit                  TEXT,
            purpose                    TEXT,
            batch_id                 TEXT,
            activity_id             INTEGER,
            key_hint        TEXT,
            source                   TEXT NOT NULL DEFAULT 'book'
                                     CHECK (source IN ('book','synthetic')),
            raw_hash                 TEXT UNIQUE
        );
CREATE TABLE kb_account (
            account                 TEXT PRIMARY KEY,
            display                TEXT NOT NULL,
            priority                 INTEGER NOT NULL,
            hat_own_limit        INTEGER NOT NULL DEFAULT 0
                                     CHECK (hat_own_limit IN (0,1)),
            own_limit_value       REAL,
            own_limit_unit    TEXT,
            own_limit_window    TEXT,
            warning_to              TEXT NOT NULL,
            host                    TEXT,
            created                TEXT NOT NULL
        );
CREATE TABLE kb_wiring (
            process         TEXT PRIMARY KEY,
            lane_first       TEXT,
            lane_second      TEXT,
            lane_third      TEXT,
            highest_share   REAL NOT NULL
                            CHECK (highest_share > 0.0 AND highest_share <= 1.0),
            reasoning     TEXT NOT NULL CHECK (LENGTH(TRIM(reasoning)) > 0),
            max_per_run     INTEGER,
            schema_duty  INTEGER,
            created        TEXT NOT NULL
        );
CREATE TABLE kb_warning (
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            time                TEXT NOT NULL,
            account                TEXT,
            access                TEXT,
            kind                  TEXT NOT NULL CHECK (kind IN (
                                 'over_norm', 'reset_approaching',
                                 'consumption_without_progress',
                                 'ambiguous_key',
                                 'no_limit_no_pattern')),
            text                 TEXT NOT NULL,
            metrics_json       TEXT
        );
CREATE TABLE kb_access (
            access                    TEXT PRIMARY KEY,
            display                    TEXT NOT NULL,
            unit                    TEXT,
            window_duration_seconds      INTEGER,
            window_limit                REAL,
            week_limit                  REAL,
            tag_limit                    REAL,
            minute_limit                 REAL,
            day_switch_hour          INTEGER,
            peak_time_json             TEXT,
            shared_with                  TEXT,
            specialty                TEXT NOT NULL,
            ambiguous_key      INTEGER NOT NULL DEFAULT 0
                                         CHECK (ambiguous_key IN (0,1)),
            created                    TEXT NOT NULL
        , model TEXT, token_minute_limit REAL, token_tag_limit REAL, state TEXT NOT NULL DEFAULT 'untested', state_reason TEXT, state_measured TEXT, boundaries_source TEXT, unknown_fields TEXT, unknown_reason TEXT, can_embedding INTEGER, can_schema INTEGER, can_batch INTEGER, exhausted INTEGER NOT NULL DEFAULT 0, accounts_count INTEGER, accounts_separated INTEGER, key_names TEXT);
CREATE TABLE comment (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        article_id TEXT NOT NULL,
        text TEXT NOT NULL,
        author TEXT,
        time TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'open'
            CHECK (status IN ('open','answered','supported','refuted','undecidable')),
        answer_conclusion_id INTEGER REFERENCES conclusion(id)
    );
CREATE TABLE curation (
            article_id           TEXT PRIMARY KEY,
            source                TEXT,
            event              TEXT,
            class                TEXT NOT NULL,
            alt_hash              TEXT,
            new_hash              TEXT,
            alt_size           INTEGER,
            alt_lines            INTEGER,
            new_size           INTEGER,
            new_lines            INTEGER,
            recognized_at            TEXT NOT NULL,
            last_checked_at   TEXT NOT NULL,
            necessary                TEXT NOT NULL,
            status                TEXT NOT NULL DEFAULT 'open'
        );
CREATE TABLE leases(resource TEXT PRIMARY KEY,holder TEXT NOT NULL,generation INTEGER NOT NULL,expires_at REAL NOT NULL,nonce TEXT NOT NULL);
CREATE TABLE memory_table (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    article_id TEXT NOT NULL,
                    memory_text TEXT NOT NULL,
                    source TEXT,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    priority REAL DEFAULT 1.0,
                    tag TEXT
                , user_id TEXT);
CREATE TABLE measurement(
            id TEXT PRIMARY KEY,
            component TEXT NOT NULL,
            source TEXT NOT NULL,
            line_hash TEXT NOT NULL,
            metric TEXT NOT NULL,
            value REAL NOT NULL,
            unit TEXT NOT NULL,
            time TEXT NOT NULL,
            host TEXT,
            instance TEXT,
            raw TEXT NOT NULL
        );
CREATE TABLE measurement_meta(
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE mv_claude_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    turn_id TEXT,
    session_id TEXT,
    user_id TEXT,
    warm INTEGER NOT NULL DEFAULT 0,
    round_no INTEGER,
    num_turns INTEGER,
    input_tokens INTEGER,
    output_tokens INTEGER,
    cache_read_input_tokens INTEGER,
    cache_creation_input_tokens INTEGER,
    cost_usd REAL,
    duration_ms_claude_code REAL,
    duration_ms_api REAL,
    wall_ms REAL,
    created_at REAL NOT NULL
);
CREATE TABLE mv_eval_runs (
    run_id TEXT PRIMARY KEY,
    iteration INTEGER NOT NULL,
    prompt_version TEXT NOT NULL,
    eval_set_size INTEGER NOT NULL,
    pass_rate REAL NOT NULL,
    avg_faithfulness REAL NOT NULL,
    avg_readability REAL NOT NULL,
    fabrication_count INTEGER NOT NULL,
    notes TEXT,
    created_at REAL NOT NULL
);
CREATE TABLE mv_prestage_state (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT NOT NULL UNIQUE,
    value_json TEXT NOT NULL,
    updated_at REAL NOT NULL
);
CREATE TABLE mv_prestage_turns (
    prestage_id TEXT PRIMARY KEY,
    turn_id TEXT,
    session_id TEXT,
    user_id TEXT,
    raw_prompt TEXT NOT NULL,
    world_digest TEXT,
    connected_systems_json TEXT,
    caveman_prompt TEXT NOT NULL,
    tool_selection_json TEXT,
    memory_artefacts_json TEXT,
    outsourced_json TEXT,
    user_intent TEXT,
    watch_out TEXT,
    hypotheses_json TEXT,
    counter_hypotheses_json TEXT,
    prestage_model TEXT,
    prestage_receipt_json TEXT,
    created_at REAL NOT NULL
, epistemic_json TEXT, epistemic_known_n INTEGER, epistemic_unknown_n INTEGER, routing_key TEXT, self_adapted INTEGER, translation_raw_fallback INTEGER, self_reported_gap INTEGER, self_reported_gap_marker TEXT, outcome_ok INTEGER, corpus_hit_n INTEGER, effects_evidence_json TEXT);
CREATE TABLE mv_translation_log (
    translation_id TEXT PRIMARY KEY,
    turn_id TEXT,
    prestage_id TEXT,
    caveman_original TEXT NOT NULL,
    german_translation TEXT NOT NULL,
    translator_model TEXT,
    translator_receipt_json TEXT,
    faithfulness_score REAL,
    readability_score REAL,
    judge_model TEXT,
    judge_verdict_json TEXT,
    fabrication_flag INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL
);
CREATE TABLE mv_translation_failure(  id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL,  turn_id TEXT, session_id TEXT, error TEXT);
CREATE TABLE om_hypothesis_implication(
    id INTEGER PRIMARY KEY,
    article_id TEXT NOT NULL,
    hypothesis_id TEXT,
    hypothesis_text TEXT NOT NULL,
    text TEXT NOT NULL,
    confidence REAL NOT NULL,
    model TEXT NOT NULL,
    generated_at TEXT NOT NULL
);
CREATE TABLE om_run(
    id INTEGER PRIMARY KEY,
    time TEXT NOT NULL,
    step TEXT NOT NULL,
    ok INTEGER NOT NULL,
    count INTEGER NOT NULL DEFAULT 0,
    ms INTEGER NOT NULL DEFAULT 0,
    hint TEXT
);
CREATE TABLE om_project(
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    kind TEXT NOT NULL,              -- 'field' (from article.project) | 'cluster' (co-occurrence/graph)
    parents_id TEXT,                 -- NULL = no parent relationship proven
    confidence REAL NOT NULL,
    reasoning TEXT NOT NULL,
    count_article INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
);
CREATE TABLE om_project_edge(
    a_id TEXT NOT NULL,
    b_id TEXT NOT NULL,
    strength REAL NOT NULL,
    evidence TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY(a_id, b_id)
);
CREATE TABLE om_project_member(
    article_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    confidence REAL NOT NULL,
    PRIMARY KEY(article_id, project_id)
);
CREATE TABLE om_sketch(
    article_id TEXT PRIMARY KEY,
    mermaid TEXT NOT NULL,
    source TEXT NOT NULL,           -- 'mechanical:<field>' or 'model:<name>'
    generated_at TEXT NOT NULL
);
CREATE TABLE om_summary(
    article_id TEXT PRIMARY KEY,
    text TEXT NOT NULL,
    model TEXT NOT NULL,
    generated_at TEXT NOT NULL
);
CREATE TABLE problem (
            id TEXT PRIMARY KEY,
            component TEXT,
            source TEXT NOT NULL,
            line_hash TEXT NOT NULL,
            text TEXT NOT NULL,
            kind TEXT NOT NULL CHECK (kind IN ('problem','hurdle','risk','open_question')),
            recognized_at TEXT,
            status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','solved')),
            solved_at TEXT,
            solved_through TEXT
        );
CREATE TABLE pu_position (
        key TEXT PRIMARY KEY, value TEXT NOT NULL, time TEXT NOT NULL
    );
CREATE TABLE pu_beat (
        sequence INTEGER PRIMARY KEY,
        clay_id TEXT NOT NULL,
        time TEXT NOT NULL,
        monotonic REAL NOT NULL,
        boot_id TEXT NOT NULL,
        kind TEXT NOT NULL,
        delta INTEGER NOT NULL DEFAULT 0,
        costs_us REAL,
        model_calls INTEGER NOT NULL DEFAULT 0,
        tool_calls INTEGER NOT NULL DEFAULT 0,
        detail TEXT
    );
CREATE TABLE retrieval_entrypoint_policy(entry_key TEXT PRIMARY KEY,capital REAL NOT NULL DEFAULT 0.0,reward_ema REAL NOT NULL DEFAULT 0.0,pulls INTEGER NOT NULL DEFAULT 0,updated_at REAL NOT NULL);
CREATE TABLE retrieval_episodes(retrieval_id TEXT PRIMARY KEY,turn_id TEXT NOT NULL UNIQUE REFERENCES turns(turn_id),episode_id TEXT NOT NULL UNIQUE REFERENCES workspace_episodes(episode_id),causal_id TEXT NOT NULL UNIQUE,session_id TEXT NOT NULL REFERENCES sessions(session_id),user_id TEXT NOT NULL REFERENCES users(user_id),generation INTEGER NOT NULL,policy_version INTEGER NOT NULL,mode TEXT NOT NULL CHECK(mode IN ('SHADOW','ACTIVE')),query_hash TEXT NOT NULL,query_token_hashes TEXT NOT NULL,selected_memory_ids TEXT NOT NULL,shadow_memory_ids TEXT NOT NULL,entry_keys TEXT NOT NULL,budget_chars INTEGER NOT NULL,chars_selected INTEGER NOT NULL,status TEXT NOT NULL CHECK(status IN ('PRESENT','UNKNOWN')),ts REAL NOT NULL);
CREATE TABLE retrieval_feedback(receipt_id TEXT PRIMARY KEY,retrieval_id TEXT NOT NULL REFERENCES retrieval_episodes(retrieval_id) ON DELETE CASCADE,causal_id TEXT NOT NULL,generation INTEGER NOT NULL,credit REAL NOT NULL,signal_class TEXT NOT NULL,ts REAL NOT NULL);
CREATE TABLE retrieval_policy_state(singleton INTEGER PRIMARY KEY CHECK(singleton=1),mode TEXT NOT NULL CHECK(mode IN ('SHADOW','ACTIVE')),policy_version INTEGER NOT NULL,updated_at REAL NOT NULL);
CREATE TABLE key_position (
        key      TEXT PRIMARY KEY,
        last_checked TEXT,
        http            INTEGER,
        ms              REAL,
        classification      TEXT,      -- MECHANICAL, only here lies the truth
        since            TEXT,      -- when this state began
        error_text      TEXT,
        model_opinion  TEXT,      -- PROPOSAL of a model, not a fact
        checked_total INTEGER DEFAULT 0,
        healthy_total   INTEGER DEFAULT 0
    , probe TEXT, rest_quota TEXT);
CREATE TABLE key_run (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        time TEXT NOT NULL, key TEXT NOT NULL,
        http INTEGER, ms REAL, classification TEXT, error_text TEXT
    , probe TEXT, rest_quota TEXT);
CREATE TABLE sessions(session_id TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(user_id),created_at REAL NOT NULL,updated_at REAL NOT NULL,generation INTEGER NOT NULL DEFAULT 1,terminal_name TEXT NOT NULL UNIQUE);
CREATE TABLE view_workspace (
  entry_id    TEXT PRIMARY KEY,
  capture_id   TEXT NOT NULL,
  candidate_id   TEXT NOT NULL,
  object_id     TEXT,
  hypothesis_id  TEXT,
  turn_id       TEXT,
  session_id    TEXT,
  registered_at REAL NOT NULL,
  -- The ignition features from the architecture, section „G“: novelty,
  -- Prediction error, uncertainty, target reference, risk.
  ignition_reason TEXT NOT NULL DEFAULT '{}',
  ignition      INTEGER NOT NULL DEFAULT 0,
  broadcast_id  TEXT,
  rejected_reason TEXT,
  decided_at REAL
);
CREATE TABLE view_capture (
  capture_id   TEXT PRIMARY KEY,
  file_id      TEXT,
  source_id     TEXT NOT NULL,
  source_class TEXT NOT NULL,
  image_hash     TEXT,
  width        INTEGER,
  height         INTEGER,
  user_id       TEXT,
  turn_id       TEXT,
  causal_id     TEXT,
  session_id    TEXT,
  level         TEXT NOT NULL,
  level_version TEXT,
  -- ⭐ This is the reverse direction of retrieval: what the inventory knew BEFORE the
  -- analysis already knew and what therefore went into the measurement order. Without this
  -- column, it can no longer be said later whether a detection came from the
  -- image or from the expectation (NR-RET-014, prior dominance).
  recall_context TEXT,
  recall_hit INTEGER DEFAULT 0,
  duration_ms      REAL,
  result      TEXT,
  error_reason   TEXT,
  begun_at   REAL NOT NULL,
  finished_at    REAL
);
CREATE TABLE view_evidence (
  evidence_id        TEXT PRIMARY KEY,
  capture_id       TEXT NOT NULL,
  source_id         TEXT NOT NULL,
  source_epoch     INTEGER NOT NULL,
  capture_time     REAL,
  entrance_time      REAL NOT NULL,
  -- Not the pixels, only their fingerprint. The image stays in the
  -- file storage; a database is the wrong place for image data, and a
  -- hash suffices to later prove it was the same image.
  raw_reference_hash     TEXT,
  room_reference        TEXT,
  transformation    TEXT NOT NULL,
  transformation_version TEXT NOT NULL,
  observation_type   TEXT NOT NULL,
  value              TEXT NOT NULL,
  bottom_up_precision REAL,
  -- ⚠️ NR-RET-012: YOLO confidence, CLIP cosine and OCR quality are NOT
  -- comparable. This column tells against which calibration the number
  -- may be read. If 'UNCALIBRATED' is here, the number is only
  -- ordering within the same transformation, not across transformations.
  calibration_ref  TEXT NOT NULL DEFAULT 'UNCALIBRATED',
  -- Constant. A column that always says the same thing is intentional here: it
  -- appears in every line that someone reads.
  authority        TEXT NOT NULL DEFAULT 'ONLY_OBSERVATION',
  generated_at        REAL NOT NULL
);
CREATE TABLE view_hypothesis (
  hypothesis_id  TEXT PRIMARY KEY,
  capture_id   TEXT NOT NULL,
  anchor         TEXT NOT NULL,
  kind           TEXT NOT NULL,
  -- ⭐⭐ F57, mechanical: quantitative readings
  -- [{"reading":..., "p":..., "from":[evidence_id,...]}, ...].
  -- A cascade stage may shift weights, but not an interpretation
  -- remove — see narrow(). In a four-stage cascade there is a
  -- Early exclusion at four points no longer recoverable.
  readings      TEXT NOT NULL,
  readings_closed INTEGER NOT NULL DEFAULT 0,
  supporting_evidence    TEXT NOT NULL DEFAULT '[]',
  contradictory_evidence TEXT NOT NULL DEFAULT '[]',
  inventory_support       TEXT NOT NULL DEFAULT '[]',
  sensor_precision     REAL,
  prior_precision      REAL,
  context_reinforcement  REAL,
  -- portion of support that comes from the prior instead of from the image.
  -- NR-RET-014: a strong prior can dominate weak sensors and the
  -- Increase hit rate while allowing false assumptions to pass.
  -- Therefore tracked as a number and not as a feeling.
  prior_dominance        REAL,
  confidence    REAL,
  state       TEXT NOT NULL,
  revision      INTEGER NOT NULL DEFAULT 1,
  predecessor_id TEXT,
  resolved_from TEXT,
  generated_at    REAL NOT NULL
);
CREATE TABLE view_cascade_level (
  level         TEXT PRIMARY KEY,
  rang          INTEGER NOT NULL,
  purpose         TEXT NOT NULL,
  error_case    TEXT NOT NULL,
  active         INTEGER NOT NULL DEFAULT 0,
  measured_ms   REAL,
  measurement_basis TEXT NOT NULL,
  source        TEXT
);
CREATE TABLE view_feature (
  feature_id   TEXT PRIMARY KEY,
  capture_id  TEXT NOT NULL,
  anchor        TEXT NOT NULL,
  procedure    TEXT NOT NULL,
  dimension    INTEGER NOT NULL,
  vector       TEXT NOT NULL,
  frame_hash  TEXT,
  generated_at   REAL NOT NULL
);
CREATE TABLE view_usage (
  usage_id    TEXT PRIMARY KEY,
  entry_id    TEXT,
  object_id     TEXT,
  evidence_id    TEXT,
  turn_id       TEXT,
  causal_id     TEXT,
  usage_type   TEXT NOT NULL,
  evidence         TEXT,
  -- ⭐ Who determined this. “MECHANICAL” means: a rule has
  -- verified. A model that claims to have used something is not a
  -- Evidence — NR-RET-017 warns precisely against this.
  determined_from TEXT NOT NULL,
  generated_at    REAL NOT NULL
);
CREATE TABLE view_visibility (
  visibility  TEXT PRIMARY KEY,
  template_en    TEXT NOT NULL,
  measurable       INTEGER NOT NULL,
  evidenced_absence INTEGER NOT NULL,
  decay       TEXT NOT NULL,
  why         TEXT NOT NULL
);
CREATE TABLE view_world_object (
  object_id     TEXT PRIMARY KEY,
  source_id     TEXT NOT NULL,
  semantic_identity TEXT,
  first_capture_id TEXT NOT NULL,
  first_seen_at  REAL NOT NULL,
  predecessor_id TEXT,
  division_from   TEXT,
  merger_from TEXT,
  provenance    TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE view_world_object_stand (
  stand_id      TEXT PRIMARY KEY,
  object_id     TEXT NOT NULL,
  valid_from    REAL NOT NULL,
  valid_until   REAL,
  visibility  TEXT NOT NULL,
  -- Not cosmetic: the reason distinguishes “OCCLUDED, because a box
  -- stands in front of it” from “OCCLUDED, because we assume it”. Without reason there is a
  -- Visibility state is an assertion.
  visibility_reason TEXT,
  room_state  TEXT,
  features_with_evidence TEXT NOT NULL DEFAULT '[]',
  relations_with_evidence TEXT NOT NULL DEFAULT '[]',
  last_positive_evidence_epoch INTEGER,
  last_explicit_negative_epoch INTEGER,
  uncertainty  REAL,
  supporting_hypothesis_id TEXT,
  capture_id   TEXT,
  turn_id       TEXT,
  causal_id     TEXT,
  generated_at    REAL NOT NULL
);
CREATE TABLE view_assignment (
  assignment_id  TEXT PRIMARY KEY,
  capture_id   TEXT NOT NULL,
  anchor         TEXT NOT NULL,
  object_id     TEXT,
  decision  TEXT NOT NULL,
  reasoning   TEXT NOT NULL,
  similarity  REAL,
  distance_to_the_second REAL,
  procedure     TEXT NOT NULL,
  procedure_version TEXT,
  generated_at    REAL NOT NULL
);
CREATE TABLE memory_return_path(path TEXT PRIMARY KEY, captured REAL NOT NULL, why TEXT, models INTEGER, directory TEXT NOT NULL);
CREATE TABLE memory_watch_log(id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL, evidenced_percent REAL, free_gb REAL, level TEXT, handled INTEGER NOT NULL, freed_gb REAL, report TEXT, df_gb REAL, counted_gb REAL, gap_gb REAL, not_countable TEXT, balance_judgment TEXT);
CREATE TABLE activity (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    host TEXT,
    instance TEXT,
    session TEXT,
    time TEXT,
    tool TEXT,
    goal_path TEXT,
    action TEXT,
    result TEXT,
    source TEXT,
    line_nr INTEGER,
    raw_hash TEXT UNIQUE
);
CREATE TABLE activity_edge (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    activity_id INTEGER NOT NULL,
    article_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    evidence TEXT,
    UNIQUE(activity_id, article_id, kind)
);
CREATE TABLE turn_compressions(
    compression_id TEXT PRIMARY KEY,
    turn_id TEXT NOT NULL REFERENCES turns(turn_id),
    session_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    level INTEGER NOT NULL,
    level_name TEXT NOT NULL,
    content TEXT NOT NULL,
    source_sha256 TEXT NOT NULL,
    derived_from_turn_ids TEXT NOT NULL,
    extractor TEXT NOT NULL,
    prompt_version TEXT,
    created_at REAL NOT NULL,
    UNIQUE(turn_id, level)
);
CREATE TABLE turns(turn_id TEXT PRIMARY KEY,session_id TEXT NOT NULL REFERENCES sessions(session_id),user_id TEXT NOT NULL REFERENCES users(user_id),ordinal INTEGER NOT NULL,ts REAL NOT NULL,role TEXT NOT NULL CHECK(role IN ('user','assistant','system','tool')),content TEXT NOT NULL,fidelity TEXT NOT NULL DEFAULT 'full',compression_generation INTEGER NOT NULL DEFAULT 0,resource_refs TEXT NOT NULL DEFAULT '[]',causal_refs TEXT NOT NULL DEFAULT '[]',provenance TEXT NOT NULL DEFAULT '{}',UNIQUE(session_id, ordinal));
CREATE TABLE users(user_id TEXT PRIMARY KEY,display_name TEXT NOT NULL,rights TEXT NOT NULL DEFAULT 'equal',clerk_subject TEXT UNIQUE);
CREATE TABLE vd_capture (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        time          TEXT NOT NULL,
        stream         TEXT NOT NULL,
        new           INTEGER NOT NULL,
        changed     INTEGER NOT NULL,
        open_total  INTEGER NOT NULL,
        threshold      INTEGER NOT NULL,
        triggered    INTEGER NOT NULL
    );
CREATE TABLE vd_seen (
        stream            TEXT NOT NULL,
        quell_id         TEXT NOT NULL,
        time             TEXT NOT NULL,
        enrichment_id  INTEGER,
        PRIMARY KEY (stream, quell_id)
    );
CREATE TABLE vd_border (
        access            TEXT PRIMARY KEY,
        count_429        INTEGER NOT NULL DEFAULT 0,
        first_429         TEXT,
        last_429        TEXT,
        last_wait_time  REAL,
        call_without_429     INTEGER NOT NULL DEFAULT 0,
        remark         TEXT
    );
CREATE TABLE vd_run (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        time             TEXT NOT NULL,
        stream            TEXT NOT NULL,
        sources          INTEGER NOT NULL,
        lane             TEXT,
        model           TEXT,
        http             INTEGER,
        duration_ms         REAL,
        token_on        INTEGER,
        token_off        INTEGER,
        result         TEXT NOT NULL,
        reason            TEXT,
        detail           TEXT,
        enrichment_id  INTEGER,
        compression_id   TEXT
    );
CREATE TABLE vd_stream (
        stream            TEXT PRIMARY KEY,
        threshold         INTEGER NOT NULL,
        rate_per_hour   REAL,
        rate_evidence       TEXT,
        active            INTEGER NOT NULL DEFAULT 1,
        created         TEXT NOT NULL,
        last_verification  TEXT,
        last_run     TEXT
    , portion INTEGER);
CREATE TABLE vp_alias (
      alias_id INTEGER PRIMARY KEY AUTOINCREMENT,
      target_kind TEXT, target_id TEXT, alias_norm TEXT,
      alias_class TEXT, confidence REAL, source_epoch INTEGER
    );
CREATE TABLE vp_alias_df (
  word TEXT PRIMARY KEY,
  df INTEGER NOT NULL,          -- in how many aliases does the word appear
  built_at TEXT
);
CREATE VIRTUAL TABLE vp_alias_fts USING fts5(alias_norm, content='vp_alias', content_rowid='alias_id');
CREATE TABLE vp_alias_meta (key TEXT PRIMARY KEY, value TEXT);
CREATE VIRTUAL TABLE vp_file_fts USING fts5(title, file_id UNINDEXED);
CREATE VIRTUAL TABLE vp_dir_fts USING fts5(directory_name, file_id UNINDEXED);
CREATE TABLE vp_edge_learning (
      query_class TEXT, edge_kind TEXT,
      weight REAL DEFAULT 0, observations INTEGER DEFAULT 0,
      last_learned TEXT, seen INTEGER DEFAULT 0, used INTEGER DEFAULT 0,
      PRIMARY KEY(query_class, edge_kind)
    );
CREATE TABLE vp_edge_learning_backup_preflift(
  query_class TEXT,
  edge_kind TEXT,
  weight REAL,
  observations INT,
  last_learned TEXT
);
CREATE TABLE vp_event (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      time TEXT, kind TEXT, detail TEXT
    );
CREATE TABLE vp_success_marker (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts REAL NOT NULL, question TEXT, region TEXT, anchor TEXT,
  carried INTEGER,              -- 1 = the entry led to the answer
  source TEXT                    -- who set the marker
);
CREATE TABLE vp_seen (
      run TEXT, record_id TEXT, time TEXT
    );
CREATE TABLE vp_map_region (
  version INTEGER NOT NULL, region TEXT NOT NULL,
  project TEXT, kind TEXT, article_n INTEGER,
  landmarks TEXT,               -- JSON: the most highly connected articles
  PRIMARY KEY(version, region)
);
CREATE TABLE vp_map_version (
  version INTEGER PRIMARY KEY AUTOINCREMENT,
  built_at TEXT NOT NULL,
  occasion TEXT,
  regions INTEGER, landmarks INTEGER, signpost INTEGER,
  corpus_article INTEGER, corpus_edges INTEGER,
  ratio REAL,              -- Map lines / corpus lines. Must stay small.
  exploration_share REAL DEFAULT 0.0,   -- 0.0 = antidote against the echo NOT active
  duration_s REAL
);
CREATE TABLE vp_map_signpost (
  version INTEGER NOT NULL, word TEXT NOT NULL, region TEXT NOT NULL,
  strength REAL NOT NULL,         -- Lift: how strongly this word points to the region
  PRIMARY KEY(version, word, region)
);
CREATE TABLE vp_read_log (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      time TEXT, place_id TEXT, work_package_id TEXT, bytes INTEGER, allowed INTEGER, reason TEXT
    );
CREATE TABLE vp_work_package_log (
      work_package_id TEXT PRIMARY KEY, time TEXT, epoch_seconds INTEGER,
      question TEXT, places_json TEXT
    );
CREATE TABLE vp_plan_cache (
      sig_hash TEXT PRIMARY KEY,
      source_epoch INTEGER, graph_epoch INTEGER,
      anchor_ids TEXT, gap_terms TEXT,
      plan_json TEXT,
      generated_at TEXT, hit_count INTEGER DEFAULT 0, last_met TEXT
    );
CREATE TABLE vp_session (
      id TEXT PRIMARY KEY,
      computer TEXT NOT NULL,
      role TEXT NOT NULL,           -- z.B. 'clayverse' / 'gabriel' / 'user-b'
      started REAL NOT NULL,
      sign_of_life REAL NOT NULL
    );
CREATE TABLE vp_snapshot (
      snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
      generated_at TEXT, state_hash TEXT,
      normals_score TEXT, normals_passed INTEGER,
      observations_total INTEGER, edge_learning_snapshot TEXT
    , source_epoch INTEGER, graph_epoch INTEGER);
CREATE TABLE vp_path (
  src TEXT NOT NULL,
  dst TEXT NOT NULL,
  kind TEXT,                          -- Edge type from which the path originated
  usage INTEGER NOT NULL DEFAULT 0,
  carried INTEGER NOT NULL DEFAULT 0,
  quality REAL NOT NULL DEFAULT 0.0,   -- 0 = slow road, 1 = highway
  sessions TEXT,                    -- various sessions that carried it (JSON list)
  tunnel INTEGER NOT NULL DEFAULT 0,
  first_usage REAL NOT NULL,
  last_usage REAL NOT NULL,
  PRIMARY KEY(src, dst)
);
CREATE TABLE wa_event (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        time TEXT, kind TEXT, goal TEXT, detail TEXT, source TEXT
    );
CREATE TABLE wa_border (
        id INTEGER PRIMARY KEY AUTOINCREMENT, time TEXT, detail TEXT
    );
CREATE TABLE wa_snapshot (
        goal TEXT PRIMARY KEY,
        time TEXT, rchar INTEGER, wchar INTEGER, cpu_ticks INTEGER,
        active_enter TEXT, active_state TEXT
    );
CREATE TABLE wake_events(
    coalesce_key TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    subject_ref TEXT,
    ts REAL NOT NULL,
    first_ts REAL NOT NULL,
    count INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE path(
            id TEXT PRIMARY KEY,
            origin TEXT NOT NULL,
            goal_host TEXT NOT NULL,
            goal_service TEXT,
            goal_path TEXT,
            transport TEXT NOT NULL,
            proxyjump_via TEXT,
            account TEXT,
            command TEXT NOT NULL,
            tor TEXT NOT NULL,
            may TEXT NOT NULL,
            steps TEXT,
            reachable INTEGER NOT NULL,
            error TEXT,
            last_proven TEXT NOT NULL,
            evidence TEXT NOT NULL
        );
CREATE TABLE wk_task (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        kind           TEXT NOT NULL,
        article_id    TEXT NOT NULL,
        value          REAL NOT NULL DEFAULT 0,
        state       TEXT NOT NULL DEFAULT 'open'
                      CHECK (state IN ('open','running','finished','discarded','unusable')),
        attempts      INTEGER NOT NULL DEFAULT 0,
        last_reason TEXT,
        created      TEXT NOT NULL,
        changed     TEXT NOT NULL,
        UNIQUE (kind, article_id)
    );
CREATE TABLE wm_cast_rule (
        from_domain  TEXT NOT NULL,
        to_domain TEXT NOT NULL,
        allowed      INTEGER NOT NULL,
        condition    TEXT,
        evidence        TEXT NOT NULL,
        candidate     TEXT NOT NULL,
        open        INTEGER NOT NULL DEFAULT 1,
        generated_at   TEXT NOT NULL,
        PRIMARY KEY (from_domain, to_domain)
    );
CREATE TABLE wm_cast_log (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        time         TEXT NOT NULL,
        from_domain  TEXT NOT NULL,
        to_domain TEXT NOT NULL,
        result     TEXT NOT NULL,
        reason        TEXT NOT NULL,
        condition    TEXT,
        evidence        TEXT,
        item   TEXT,
        candidate     TEXT NOT NULL,
        open        INTEGER NOT NULL DEFAULT 1
    );
CREATE TABLE wm_reading (
        reading_id    TEXT PRIMARY KEY,
        article_id   TEXT NOT NULL,
        axis        TEXT NOT NULL,
        value         TEXT,
        context_json TEXT NOT NULL DEFAULT '{}',
        domain      TEXT NOT NULL DEFAULT 'FACT_EXACT',
        basis_json   TEXT NOT NULL,
        source       TEXT NOT NULL,
        confidence    REAL,
        generated_at   TEXT NOT NULL,
        valid_from  TEXT NOT NULL,
        valid_until  TEXT,
        candidate     TEXT NOT NULL,
        open        INTEGER NOT NULL DEFAULT 1,
        open_reason  TEXT
    );
CREATE TABLE wm_topology (
        src          TEXT NOT NULL,
        dst         TEXT NOT NULL,
        topology    TEXT NOT NULL,
        origin_kind TEXT NOT NULL DEFAULT '',
        weight      REAL NOT NULL DEFAULT 1.0,
        basis_json   TEXT NOT NULL,
        source       TEXT,
        generated_at   TEXT NOT NULL,
        valid_from  TEXT NOT NULL,
        valid_until  TEXT,
        candidate     TEXT NOT NULL,
        open        INTEGER NOT NULL DEFAULT 1,
        open_reason  TEXT,
        PRIMARY KEY (src, dst, topology, origin_kind)
    );
CREATE TABLE wm_topology_name (
        topology  TEXT PRIMARY KEY,
        h_number   TEXT NOT NULL,
        meaning  TEXT NOT NULL,
        candidate   TEXT NOT NULL,
        open      INTEGER NOT NULL DEFAULT 1
    );
CREATE TABLE workspace_episodes(episode_id TEXT PRIMARY KEY,session_id TEXT NOT NULL REFERENCES sessions(session_id),ts REAL NOT NULL,observation_turn_id TEXT REFERENCES turns(turn_id),salience REAL NOT NULL,alternatives TEXT NOT NULL,selected TEXT,state TEXT NOT NULL);
CREATE TABLE zero_room (
  session_id TEXT PRIMARY KEY,          -- one row per session, gets overwritten
  human     TEXT NOT NULL,             -- gabriel | user-b
  place      INTEGER NOT NULL,
  activity        TEXT NOT NULL,             -- Caveman: what I'm currently doing
  target      TEXT,                      -- the touched item: file, table, service
  state    TEXT NOT NULL,             -- working | waiting | free
  since       REAL NOT NULL,
  nickname  TEXT                       -- PHASE 37, star_cli.py self-healing also migrates this retroactively
);
CREATE TABLE zero_room_call (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts REAL NOT NULL,
  src TEXT NOT NULL,
  text TEXT NOT NULL
);
CREATE INDEX architect_engine_log_ts_idx ON architect_engine_log(ts);
CREATE INDEX eos_architect_receipts_hyp_idx ON eos_architect_receipts(hypothesis_id, ts);
CREATE INDEX eos_evaluations_session_idx ON eos_evaluations(session_id, ts);
CREATE INDEX eos_bug_hypotheses_status_idx ON eos_bug_hypotheses(status, ts);
CREATE INDEX eos_bug_hypotheses_user_idx ON eos_bug_hypotheses(user_id, ts);
CREATE INDEX gw_intention_ts ON gw_intention(ts);
CREATE INDEX gw_broadcast_ts ON gw_broadcast(ts);
CREATE INDEX gw_origin_ts ON gw_origin(ts);
CREATE INDEX idx_work_package_stand ON entityos_work_package(stand, created);
CREATE INDEX idx_article_kind ON article(kind);
CREATE INDEX idx_article_construction_note_lookup ON article(kind, from_source, date);
CREATE INDEX idx_article_epistemic_class ON article(epistemic_class);
CREATE INDEX idx_article_logical_id ON article(logical_id);
CREATE INDEX idx_article_project ON article(project);
CREATE INDEX idx_article_source ON article(source);
CREATE INDEX idx_article_sphere ON article(sphere);
CREATE INDEX idx_article_status ON article(status);
CREATE INDEX idx_article_compression_lookup ON article(kind, from_source, date);
CREATE INDEX idx_article_search_text_bubble ON article_search_text(bubble);
CREATE INDEX idx_lane_run_kind_time ON lane_run(kind, time);
CREATE INDEX idx_processing_article ON processing(article_id);
CREATE INDEX idx_success_marker_region ON vp_success_marker(region, ts);
CREATE INDEX idx_error_kind ON error(kind);
CREATE INDEX idx_error_severity ON error(severity);
CREATE INDEX idx_conclusion_evidence_fid ON conclusion_evidence(conclusion_id);
CREATE INDEX idx_conclusion_applies_for ON conclusion(applies_for);
CREATE INDEX idx_find_location_bubble ON find_location(bubble);
CREATE INDEX idx_find_location_file ON find_location(file_id);
CREATE INDEX idx_find_location_checksum ON find_location(checksum);
CREATE INDEX idx_tombstone_goal ON tombstone(activity, goal_id);
CREATE INDEX idx_graph_edge_source_epoch
            ON graph_edge(source_node_id, graph_epoch DESC, weight DESC);
CREATE INDEX idx_graph_edge_target_epoch
            ON graph_edge(target_node_id, graph_epoch DESC, weight DESC);
CREATE INDEX idx_graph_node_external
            ON graph_node(external_id);
CREATE INDEX idx_graph_node_type
            ON graph_node(node_type);
CREATE INDEX idx_edge_to ON edge(dst);
CREATE INDEX idx_edge_from ON edge(src);
CREATE INDEX idx_map_signpost_word ON vp_map_signpost(word);
CREATE INDEX idx_comment_article ON comment(article_id);
CREATE INDEX idx_comment_status ON comment(status);
CREATE INDEX idx_memory_article ON memory_table(article_id);
CREATE INDEX idx_memory_tag ON memory_table(tag);
CREATE INDEX idx_memory_user ON memory_table(user_id);
CREATE INDEX idx_measurement_component ON measurement(component);
CREATE INDEX idx_measurement_unit ON measurement(unit);
CREATE INDEX idx_measurement_line ON measurement(line_hash);
CREATE INDEX idx_om_implication_article ON om_hypothesis_implication(article_id);
CREATE INDEX idx_om_member_article ON om_project_member(article_id);
CREATE INDEX idx_om_member_project ON om_project_member(project_id);
CREATE INDEX idx_problem_component ON problem(component);
CREATE INDEX idx_problem_status ON problem(status);
CREATE INDEX idx_problem_line_hash ON problem(line_hash);
CREATE INDEX idx_retrieval_session_ts ON retrieval_episodes(session_id,ts DESC);
CREATE INDEX idx_activity_session ON activity(session);
CREATE INDEX idx_activity_goal_path ON activity(goal_path);
CREATE INDEX idx_turn_compressions_turn ON turn_compressions(turn_id, level);
CREATE INDEX idx_turns_session_ord ON turns(session_id, ordinal DESC);
CREATE INDEX idx_vd_capture_stream ON vd_capture(stream, time);
CREATE INDEX idx_vd_run_stream ON vd_run(stream, time);
CREATE INDEX idx_vp_alias_df_df ON vp_alias_df(df);
CREATE INDEX idx_vp_path_quality ON vp_path(quality DESC);
CREATE INDEX idx_wake_events_ts ON wake_events(ts);
CREATE INDEX idx_path_origin_goal ON path(origin, goal_host);
CREATE INDEX idx_path_goal ON path(goal_host);
CREATE INDEX idx_wk_task_kind ON wk_task(kind, state);
CREATE INDEX idx_wk_task_choice ON wk_task(state, value DESC);
CREATE INDEX ix_curation_status_necessary ON curation(status, necessary);
CREATE INDEX ix_key_run_time ON key_run(time);
CREATE INDEX ix_activity_time ON activity(time);
CREATE INDEX kb_task_state
            ON kb_task(state, process);
CREATE INDEX kb_booking_batch
            ON kb_booking(batch_id);
CREATE INDEX kb_booking_kz_time
            ON kb_booking(account, access, time);
CREATE INDEX kb_warning_time ON kb_warning(time);
CREATE INDEX mv_prestage_turns_routing_idx
    ON mv_prestage_turns(routing_key, epistemic_unknown_n);
CREATE INDEX mv_prestage_turns_session_idx
    ON mv_prestage_turns(session_id, created_at);
CREATE INDEX view_workspace_turn ON view_workspace(turn_id);
CREATE INDEX view_capture_source ON view_capture(source_id);
CREATE INDEX view_capture_turn ON view_capture(turn_id);
CREATE INDEX view_evidence_kind ON view_evidence(observation_type);
CREATE INDEX view_evidence_capture ON view_evidence(capture_id);
CREATE INDEX view_hypothesis_capture ON view_hypothesis(capture_id);
CREATE INDEX view_hypothesis_open
  ON view_hypothesis(resolved_from) WHERE resolved_from IS NULL;
CREATE INDEX view_feature_capture ON view_feature(capture_id);
CREATE INDEX view_feature_procedure ON view_feature(procedure);
CREATE INDEX view_usage_turn ON view_usage(turn_id);
CREATE INDEX view_stand_now
  ON view_world_object_stand(object_id) WHERE valid_until IS NULL;
CREATE INDEX view_stand_object ON view_world_object_stand(object_id);
CREATE INDEX view_world_object_source ON view_world_object(source_id);
CREATE INDEX view_assignment_capture ON view_assignment(capture_id);
CREATE INDEX wm_cast_log_ix1 ON wm_cast_log(result, time);
CREATE INDEX wm_reading_ix1 ON wm_reading(article_id, valid_until);
CREATE INDEX wm_reading_ix2 ON wm_reading(article_id, axis, valid_until);
CREATE INDEX wm_reading_ix3 ON wm_reading(axis, valid_until);
CREATE INDEX wm_topology_ix1 ON wm_topology(src, topology, valid_until);
CREATE INDEX wm_topology_ix2 ON wm_topology(topology);
CREATE INDEX wm_topology_ix3 ON wm_topology(dst, topology, valid_until);
CREATE TRIGGER view_evidence_none_change
BEFORE UPDATE ON view_evidence BEGIN
  SELECT RAISE(ABORT, 'view_evidence is immutable: a later interpretation replaces a hypothesis, it does not rewrite an observation');
END;
CREATE TRIGGER view_evidence_none_delete
BEFORE DELETE ON view_evidence BEGIN
  SELECT RAISE(ABORT, 'view_evidence is immutable: what has arrived stays');
END;
CREATE VIEW condensate AS
SELECT
    'measurement'        AS kind,
    json_extract(metadata, '$.component') AS component,
    NULL             AS applies_for,
    NULL             AS conclusion_id,
    id               AS ref_id,
    title            AS label,
    date            AS time
FROM article
WHERE kind = 'incident'

UNION ALL

SELECT
    'problem_open'  AS kind,
    component          AS component,
    NULL             AS applies_for,
    NULL             AS conclusion_id,
    id               AS ref_id,
    substr(text, 1, 120) AS label,
    recognized_at       AS time
FROM problem
WHERE status = 'open'

UNION ALL

SELECT
    'conclusion'      AS kind,
    NULL             AS component,
    applies_for        AS applies_for,
    id               AS conclusion_id,
    CAST(id AS TEXT) AS ref_id,
    substr(statement, 1, 120) || ' [' || status || ']' AS label,
    time             AS time
FROM conclusion

UNION ALL

SELECT
    'evidence'          AS kind,
    NULL             AS component,
    f.applies_for      AS applies_for,
    fb.conclusion_id  AS conclusion_id,
    fb.evidence_kind || ':' || fb.evidence_id AS ref_id,
    fb.evidence_kind     AS label,
    NULL             AS time
FROM conclusion_evidence fb
JOIN conclusion f ON f.id = fb.conclusion_id;
CREATE VIEW measurement_compact AS
        SELECT
            component AS component,
            metric     AS metric,
            value    AS value,
            unit AS unit,
            time    AS time,
            source  AS source
        FROM measurement
        ORDER BY time DESC, component;
CREATE VIEW mv_prestage_learning_image AS
SELECT
    routing_key,
    CASE WHEN epistemic_unknown_n > 0 THEN 1 ELSE 0 END AS had_gap,
    COUNT(*) AS n,
    SUM(COALESCE(self_adapted, 0)) AS n_self_adapted,
    SUM(COALESCE(translation_raw_fallback, 0)) AS n_translation_failed,
    SUM(COALESCE(self_reported_gap, 0)) AS n_self_reported_gap,
    SUM(CASE WHEN outcome_ok = 0 THEN 1 ELSE 0 END) AS n_not_ok
FROM mv_prestage_turns
WHERE routing_key IS NOT NULL AND routing_key != ''
GROUP BY routing_key, CASE WHEN epistemic_unknown_n > 0 THEN 1 ELSE 0 END;
CREATE TABLE star_recall_shown(session_id TEXT NOT NULL, item_id TEXT NOT NULL, ts REAL NOT NULL, PRIMARY KEY(session_id, item_id));
CREATE TABLE star_config(
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  type TEXT NOT NULL,
  source TEXT,
  changed REAL NOT NULL
);
CREATE TABLE star_digest(
  "commit" TEXT PRIMARY KEY,
  date TEXT,
  title TEXT,
  fetched_at REAL,
  run_id TEXT
);
CREATE TABLE star_digest_run(
  run_id TEXT PRIMARY KEY,
  generated_at TEXT,
  duration_ms INTEGER,
  source TEXT,
  lookback_days INTEGER,
  error TEXT,
  unchanged INTEGER
);
CREATE TABLE star_ability(tool_name TEXT PRIMARY KEY, approved INTEGER NOT NULL DEFAULT 1, reason TEXT, changed REAL NOT NULL);
CREATE TABLE udb_nvidia_embedding (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id TEXT NOT NULL,
    source_table TEXT NOT NULL DEFAULT 'article' CHECK (source_table IN ('article','durable_memory')),
    model TEXT NOT NULL,
    dim INTEGER NOT NULL,
    embedding_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(article_id, source_table)
);
CREATE TABLE retrieval_episodes_semantic (
    retrieval_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    generation INTEGER NOT NULL,
    model TEXT NOT NULL,
    query_hash TEXT NOT NULL,
    candidates_count INTEGER NOT NULL,
    selected_json TEXT NOT NULL,
    mechanical_selected_json TEXT,
    deviates_from INTEGER NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('PRESENT','UNKNOWN','ERROR')),
    ts REAL NOT NULL
);
CREATE INDEX idx_retrieval_sem_session_ts ON retrieval_episodes_semantic(session_id, ts DESC);
CREATE TABLE build_history (
  entry_id   TEXT PRIMARY KEY,
  phase        TEXT NOT NULL,
  description TEXT,
  completed_at TEXT NOT NULL,
  src          TEXT NOT NULL,
  measurement_result TEXT,
  evidence        TEXT,
  generated_at   TEXT NOT NULL
);
CREATE TABLE gw_champion(article_id TEXT PRIMARY KEY, series INTEGER NOT NULL DEFAULT 0, last_ts REAL NOT NULL, last_session TEXT);
CREATE TABLE star_sebukku(session_id TEXT PRIMARY KEY, ts REAL, reason TEXT, effect_id TEXT);
CREATE TABLE system_health(id TEXT PRIMARY KEY, ts REAL, cpu_percent REAL, ram_percent REAL, disk_percent REAL, load1 REAL, load5 REAL, load15 REAL, cores INTEGER, source TEXT, raw TEXT);
CREATE TABLE system_inventory(id TEXT PRIMARY KEY, run_id TEXT, ts REAL, category TEXT, name TEXT, version TEXT, source TEXT);
CREATE TABLE vault_overview(id TEXT PRIMARY KEY, url TEXT, account TEXT, status TEXT, last_usage REAL, failures_in_sequence INTEGER DEFAULT 0, last_latency_ms REAL, last_http_status INTEGER, generated_from TEXT, generated_at REAL, updated_at REAL, delete_requested INTEGER DEFAULT 0, delete_reason TEXT);
CREATE TABLE vault_event(id TEXT PRIMARY KEY, ts REAL, action TEXT, entry_id TEXT, url TEXT, reason TEXT);
