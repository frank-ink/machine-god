# German -> English rename map (plugins/frankenstein3, zero/unifieddb, docs/zero)

Machine-readable twin: `rename_map.json` (same directory). Migration for existing databases: `zero/unifieddb/migrate_to_english.py` (idempotent runner) and `zero/unifieddb/migrate_to_english.sql` (generated statement log).

## How to migrate an existing unified.db

```bash
python3 zero/unifieddb/migrate_to_english.py <db> --schema zero/unifieddb/schema.sql [--schema <plugin schema_empty.sql> ...]
```

- Backs up to `<db>.pre-english-<timestamp>` first (online-backup API); `--no-backup` skips it.
- One transaction: drops old-named views/triggers/indexes, renames columns, renames tables (FTS5 shadow tables follow), rebuilds tables whose CHECK/DEFAULT literals differ from the target schema while mapping enum values, recreates FTS5 tables with new column names and refills them, renames `star_config` keys, recreates indexes/views/triggers from the target schema, aborts if the foreign-key violation count grows.
- Idempotent: a second run on a migrated DB executes only PRAGMA/BEGIN/COMMIT (tested on the three schemas).
- `migrate_to_english.sql` is the statement sequence the runner produced for a database holding the full old schema; it is a reference/audit log. It is not guarded: apply it only to a complete old-schema DB, use the runner for anything else.
- Verified: migrating DBs built from the old schemas yields schemas identical to the new ones (tables, columns, types, literals, indexes, views, triggers) and 98 seeded enum values arrive mapped.

## Not migrated

- JSON payload keys stored inside text columns (e.g. durable memory payloads, evidence blobs): they stay as written; code reads the new keys only for new rows.
- Free-text values, ids, and enum values of columns without a CHECK constraint that are not listed in `value_map` (listed values are mapped everywhere they occur).
- Evidence strings already stored as `datei:<path>:<sha256>` stay; the verifier accepts `file:` (see "Evidence formats").

## Files (renamed with git mv)

| old | new |
|---|---|
| `plugins/frankenstein3/START_HIER.md` | `plugins/frankenstein3/START_HERE.md` |
| `plugins/frankenstein3/commands/architekt.md` | `plugins/frankenstein3/commands/architect.md` |
| `plugins/frankenstein3/commands/bild.md` | `plugins/frankenstein3/commands/image_studio.md` |
| `plugins/frankenstein3/daten/schema_leer.sql` | `plugins/frankenstein3/data/schema_empty.sql` |
| `plugins/frankenstein3/f3_pfade.py` | `plugins/frankenstein3/f3_paths.py` |
| `plugins/frankenstein3/scripts/_delegat.py` | `plugins/frankenstein3/scripts/_delegate.py` |
| `plugins/frankenstein3/scripts/bild` | `plugins/frankenstein3/scripts/image_studio` |
| `plugins/frankenstein3/scripts/raum_puls.py` | `plugins/frankenstein3/scripts/room_pulse.py` |
| `plugins/frankenstein3/scripts/raum_verlassen.py` | `plugins/frankenstein3/scripts/room_leave.py` |
| `plugins/frankenstein3/scripts/star/daten/architekt_governance.de.md` | `plugins/frankenstein3/scripts/star/data/architect_governance.de.md` |
| `plugins/frankenstein3/scripts/star/daten/architekt_governance.md` | `plugins/frankenstein3/scripts/star/data/architect_governance.md` |
| `plugins/frankenstein3/scripts/star/daten/architekt_tiefensitzung.de.md` | `plugins/frankenstein3/scripts/star/data/architect_deep_session.de.md` |
| `plugins/frankenstein3/scripts/star/daten/architekt_tiefensitzung.md` | `plugins/frankenstein3/scripts/star/data/architect_deep_session.md` |
| `plugins/frankenstein3/scripts/star/daten/begruessungen.json` | `plugins/frankenstein3/scripts/star/data/greetings.json` |
| `plugins/frankenstein3/scripts/star/daten/persona.de.md` | `plugins/frankenstein3/scripts/star/data/persona.de.md` |
| `plugins/frankenstein3/scripts/star/daten/persona.md` | `plugins/frankenstein3/scripts/star/data/persona.md` |
| `plugins/frankenstein3/scripts/star/daten/raum_namen.json` | `plugins/frankenstein3/scripts/star/data/room_names.json` |
| `plugins/frankenstein3/scripts/star/daten/schema_leer.sql` | `plugins/frankenstein3/scripts/star/data/schema_empty.sql` |
| `plugins/frankenstein3/scripts/star/daten/sebukku.de.txt` | `plugins/frankenstein3/scripts/star/data/sebukku.de.txt` |
| `plugins/frankenstein3/scripts/star/daten/sebukku.txt` | `plugins/frankenstein3/scripts/star/data/sebukku.txt` |
| `plugins/frankenstein3/scripts/star/f3_pfade.py` | `plugins/frankenstein3/scripts/star/f3_paths.py` |
| `plugins/frankenstein3/scripts/star/geheimnis_muster.py` | `plugins/frankenstein3/scripts/star/secret_pattern.py` |
| `plugins/frankenstein3/scripts/star/stern.py` | `plugins/frankenstein3/scripts/star/star_cli.py` |
| `plugins/frankenstein3/scripts/star/stern_core.py` | `plugins/frankenstein3/scripts/star/star_core.py` |
| `plugins/frankenstein3/scripts/star/stern_zyklus.py` | `plugins/frankenstein3/scripts/star/star_cycle.py` |
| `plugins/frankenstein3/skills/bild/SKILL.md` | `plugins/frankenstein3/skills/image_studio/SKILL.md` |
| `plugins/frankenstein3/tests/test_f3_pfade.py` | `plugins/frankenstein3/tests/test_f3_paths.py` |
| `plugins/frankenstein3/tests/test_f3_pfade_dry_run.py` | `plugins/frankenstein3/tests/test_f3_paths_dry_run.py` |
| `plugins/frankenstein3/tests/test_f3_pfade_dry_run_contract.py` | `plugins/frankenstein3/tests/test_f3_paths_dry_run_contract.py` |
| `plugins/frankenstein3/tests/test_f3_pfade_shim.py` | `plugins/frankenstein3/tests/test_f3_paths_shim.py` |
| `plugins/frankenstein3/tests/test_pfade.py` | `plugins/frankenstein3/tests/test_paths.py` |
| `zero/unifieddb/PRUEFUNG.json` | `zero/unifieddb/VERIFICATION.json` |

## Files deleted (tracked backup junk)

- `plugins/frankenstein3/.in_use/113382`
- `plugins/frankenstein3/.in_use/1142700`
- `plugins/frankenstein3/.in_use/1452753`
- `plugins/frankenstein3/.in_use/1466735`
- `plugins/frankenstein3/.in_use/1470169`
- `plugins/frankenstein3/.in_use/1501660`
- `plugins/frankenstein3/.in_use/1547252`
- `plugins/frankenstein3/.in_use/1624933`
- `plugins/frankenstein3/.in_use/1769013`
- `plugins/frankenstein3/.in_use/184186`
- `plugins/frankenstein3/.in_use/1949870`
- `plugins/frankenstein3/.in_use/1951954`
- `plugins/frankenstein3/.in_use/201433`
- `plugins/frankenstein3/.in_use/2038943`
- `plugins/frankenstein3/.in_use/206109`
- `plugins/frankenstein3/.in_use/207608`
- `plugins/frankenstein3/.in_use/2661024`
- `plugins/frankenstein3/.in_use/312532`
- `plugins/frankenstein3/.in_use/3186749`
- `plugins/frankenstein3/.in_use/3500583`
- `plugins/frankenstein3/.in_use/3611486`
- `plugins/frankenstein3/.in_use/372302`
- `plugins/frankenstein3/.in_use/3725061`
- `plugins/frankenstein3/.in_use/4160893`
- `plugins/frankenstein3/README.md ---`
- `plugins/frankenstein3/hooks/hooks.json.bak-vor-reentrydiaet-20261030`
- `plugins/frankenstein3/scripts/star/stern.py.backup-pre-turnlog-20261011`
- `plugins/frankenstein3/scripts/star/stern_core.py.backup-pre-turnlog-20261011`
- `plugins/frankenstein3/scripts/star/stern_core.py.bak-vor-abrufpatch-20261014`
- `plugins/frankenstein3/scripts/star/stern_core.py.vor-tatformat-20261030`

## Tables

| old | new |
|---|---|
| `ziele` | `goals` |
| `mg_drift_ereignis` | `mg_drift_event` |
| `mg_haltung` | `mg_stance` |
| `mg_haltung_widerspruch` | `mg_stance_contradiction` |
| `mg_drift_sperre` | `mg_drift_lock` |
| `hook_raum_puls` | `hook_room_pulse` |
| `hook_raum_verlassen` | `hook_room_leave` |
| `anreicherung` | `enrichment` |
| `architekt_engine_log` | `architect_engine_log` |
| `architekt_engine_zustand` | `architect_engine_state` |
| `artikel` | `article` |
| `artikel_sphaere` | `article_sphere` |
| `artikel_suchtext` | `article_search_text` |
| `bahn_lage` | `lane_position` |
| `bahn_lauf` | `lane_run` |
| `bahn_livestreak` | `lane_livestreak` |
| `bahn_nutzung` | `lane_usage` |
| `bearbeitung` | `processing` |
| `datei` | `file` |
| `entityos_arbeitspaket` | `entityos_work_package` |
| `entityos_artikel_zuordnung` | `entityos_article_assignment` |
| `entityos_erfolge` | `entityos_successes` |
| `entityos_profil` | `entityos_profile` |
| `entityos_projekte` | `entityos_projects` |
| `entityos_wirte` | `entityos_hosts` |
| `eos_architekt_quittungen` | `eos_architect_receipts` |
| `eos_bewertungen` | `eos_evaluations` |
| `eos_bug_hypothesen` | `eos_bug_hypotheses` |
| `fehler` | `error` |
| `folgerung` | `conclusion` |
| `folgerung_beleg` | `conclusion_evidence` |
| `fts_index_artikel` | `fts_index_article` |
| `fts_index_artikel_data` | `fts_index_article_data` |
| `fts_index_artikel_idx` | `fts_index_article_idx` |
| `fts_index_artikel_docsize` | `fts_index_article_docsize` |
| `fts_index_artikel_config` | `fts_index_article_config` |
| `fts_index_datei` | `fts_index_file` |
| `fts_index_datei_data` | `fts_index_file_data` |
| `fts_index_datei_idx` | `fts_index_file_idx` |
| `fts_index_datei_docsize` | `fts_index_file_docsize` |
| `fts_index_datei_config` | `fts_index_file_config` |
| `fundort` | `find_location` |
| `gedaechtnis_ausbeute` | `memory_yield` |
| `grabstein` | `tombstone` |
| `graph_kante` | `graph_edge` |
| `graph_knoten` | `graph_node` |
| `gw_absicht` | `gw_intention` |
| `gw_ausstrahlung` | `gw_broadcast` |
| `gw_herkunft` | `gw_origin` |
| `gw_lernen` | `gw_learning` |
| `gw_wettbewerb` | `gw_competition` |
| `heim_belege` | `home_evidence` |
| `kante` | `edge` |
| `kb_auftrag` | `kb_task` |
| `kb_buchung` | `kb_booking` |
| `kb_konto` | `kb_account` |
| `kb_verdrahtung` | `kb_wiring` |
| `kb_warnung` | `kb_warning` |
| `kb_zugang` | `kb_access` |
| `kommentar` | `comment` |
| `kuration` | `curation` |
| `memory_tabelle` | `memory_table` |
| `messung` | `measurement` |
| `messung_meta` | `measurement_meta` |
| `mv_uebersetzung_ausfall` | `mv_translation_failure` |
| `om_hypothese_implikation` | `om_hypothesis_implication` |
| `om_lauf` | `om_run` |
| `om_projekt` | `om_project` |
| `om_projekt_kante` | `om_project_edge` |
| `om_projekt_mitglied` | `om_project_member` |
| `om_skizze` | `om_sketch` |
| `om_zusammenfassung` | `om_summary` |
| `pu_lage` | `pu_position` |
| `pu_takt` | `pu_beat` |
| `schluessel_lage` | `key_position` |
| `schluessel_lauf` | `key_run` |
| `sicht_arbeitsraum` | `view_workspace` |
| `sicht_aufnahme` | `view_capture` |
| `sicht_evidenz` | `view_evidence` |
| `sicht_hypothese` | `view_hypothesis` |
| `sicht_kaskade_stufe` | `view_cascade_level` |
| `sicht_merkmal` | `view_feature` |
| `sicht_nutzung` | `view_usage` |
| `sicht_sichtbarkeit` | `view_visibility` |
| `sicht_weltobjekt` | `view_world_object` |
| `sicht_weltobjekt_stand` | `view_world_object_stand` |
| `sicht_zuordnung` | `view_assignment` |
| `speicher_rueckweg` | `memory_return_path` |
| `speicherwacht_log` | `memory_watch_log` |
| `taetigkeit` | `activity` |
| `taetigkeit_kante` | `activity_edge` |
| `vd_aufnahme` | `vd_capture` |
| `vd_gesehen` | `vd_seen` |
| `vd_grenze` | `vd_border` |
| `vd_lauf` | `vd_run` |
| `vd_strom` | `vd_stream` |
| `vp_datei_fts` | `vp_file_fts` |
| `vp_datei_fts_data` | `vp_file_fts_data` |
| `vp_datei_fts_idx` | `vp_file_fts_idx` |
| `vp_datei_fts_content` | `vp_file_fts_content` |
| `vp_datei_fts_docsize` | `vp_file_fts_docsize` |
| `vp_datei_fts_config` | `vp_file_fts_config` |
| `vp_edge_lern` | `vp_edge_learning` |
| `vp_edge_lern_backup_preflift` | `vp_edge_learning_backup_preflift` |
| `vp_ereignis` | `vp_event` |
| `vp_erfolgsmarke` | `vp_success_marker` |
| `vp_gesehen` | `vp_seen` |
| `vp_karte_region` | `vp_map_region` |
| `vp_karte_version` | `vp_map_version` |
| `vp_karte_wegweiser` | `vp_map_signpost` |
| `vp_lese_log` | `vp_read_log` |
| `vp_paket_log` | `vp_work_package_log` |
| `vp_sitzung` | `vp_session` |
| `vp_weg` | `vp_path` |
| `wa_ereignis` | `wa_event` |
| `wa_grenze` | `wa_border` |
| `weg` | `path` |
| `wk_aufgabe` | `wk_task` |
| `wm_cast_regel` | `wm_cast_rule` |
| `wm_guss_log` | `wm_cast_log` |
| `wm_lesart` | `wm_reading` |
| `wm_topologie` | `wm_topology` |
| `wm_topologie_name` | `wm_topology_name` |
| `zero_raum` | `zero_room` |
| `zero_raum_ruf` | `zero_room_call` |
| `star_abruf_gezeigt` | `star_recall_shown` |
| `star_konfig` | `star_config` |
| `star_digest_lauf` | `star_digest_run` |
| `star_faehigkeit` | `star_ability` |
| `retrieval_episodes_semantisch` | `retrieval_episodes_semantic` |
| `bau_historie` | `build_history` |
| `gw_dauersieger` | `gw_champion` |
| `system_gesundheit` | `system_health` |
| `system_bestand` | `system_inventory` |
| `vault_uebersicht` | `vault_overview` |
| `vault_ereignis` | `vault_event` |

## Columns (per OLD table name)

- `ziele` (now `goals`): `titel`→`title`, `beschreibung`→`description`, `messkriterium`→`measurement_criterion`, `ergebnis`→`result`, `prioritaet`→`priority`, `erstellt_at`→`created_at`, `aktualisiert_at`→`updated_at`
- `mg_drift_ereignis` (now `mg_drift_event`): `kanal`→`channel`, `typ`→`type`, `nachricht`→`message`, `gelöst`→`solved`
- `mg_haltung` (now `mg_stance`): `thema`→`topic`, `konfidenz`→`confidence`, `datum`→`date`, `gruende`→`reasons`, `quellen`→`sources`, `erstellt_at`→`created_at`
- `mg_haltung_widerspruch` (now `mg_stance_contradiction`): `haltung_id`→`stance_id`, `widerspruch`→`contradiction`, `quelle`→`source`, `offen`→`open`, `erstellt_at`→`created_at`
- `mg_drift_sperre` (now `mg_drift_lock`): `kanal`→`channel`, `grund`→`reason`, `gesperrt_bis`→`blocked_until`, `freigegeben_durch`→`released_through`, `freigegeben_am`→`released_at`
- `hook_digest`: `kanal`→`channel`, `inhalt`→`content`
- `hook_reentry`: `kanal`→`channel`, `grund`→`reason`, `ergebnis`→`result`
- `hook_raum_puls` (now `hook_room_pulse`): `kanal`→`channel`, `wert`→`value`, `quelle`→`source`
- `hook_raum_verlassen` (now `hook_room_leave`): `kanal`→`channel`, `grund`→`reason`
- `anreicherung` (now `enrichment`): `artikel_id`→`article_id`, `quelle_url`→`source_url`, `art`→`kind`, `auszug`→`excerpt`, `geholt_am`→`fetched_at`
- `architekt_engine_log` (now `architect_engine_log`): `prozess`→`process`, `bahn`→`lane`, `modell`→`model`, `glm_fehlgeschlagen_grund`→`glm_failed_reason`, `dauer_ms`→`duration_ms`
- `architekt_engine_zustand` (now `architect_engine_state`): `glm_bestaetigt`→`glm_confirmed`, `serie_fehler`→`series_error`, `zuletzt_aktualisiert`→`last_updated`
- `artikel` (now `article`): `art`→`kind`, `titel`→`title`, `quelle`→`source`, `quell_hash`→`source_hash`, `datum`→`date`, `metadaten`→`metadata`, `offene_fragen`→`open_questions`, `belegt`→`evidenced`, `erzeugt_am`→`generated_at`, `duenn`→`thin`, `zuletzt_bearbeitet`→`last_processed`, `zeitquelle`→`time_source`, `wirt`→`host`, `zuletzt_von`→`last_from`, `von_quelle`→`from_source`, `id_quelle`→`id_source`, `konfidenz`→`confidence`, `projekt`→`project`, `projekt_art`→`project_kind`, `sphaere`→`sphere`, `herkunft`→`origin`, `verfallen`→`expire`
- `artikel_sphaere` (now `article_sphere`): `artikel_id`→`article_id`, `sphaere`→`sphere`, `beleg`→`evidence`
- `artikel_suchtext` (now `article_search_text`): `artikel_id`→`article_id`, `titel`→`title`, `blase`→`bubble`, `indiziert`→`indexed`
- `bahn_lage` (now `lane_position`): `schluessel`→`key`, `wert`→`value`, `zeit`→`time`
- `bahn_lauf` (now `lane_run`): `zeit`→`time`, `art`→`kind`, `bahn`→`lane`, `modell`→`model`, `ziel_id`→`goal_id`, `dauer_ms`→`duration_ms`, `token_ein`→`token_on`, `token_aus`→`token_off`, `ergebnis`→`result`, `pruefung`→`verification`, `antwort`→`answer`
- `bahn_livestreak` (now `lane_livestreak`): `bahn`→`lane`, `serie`→`series`, `zuletzt_fehler`→`last_error`, `zuletzt_ergebnis`→`last_result`
- `bahn_nutzung` (now `lane_usage`): `bahn`→`lane`, `prozess`→`process`, `anfragen`→`inquiries`, `fehler`→`error`, `zuletzt`→`finally`
- `bearbeitung` (now `processing`): `artikel_id`→`article_id`, `feld`→`field`, `alt_wert`→`alt_value`, `neu_wert`→`new_value`, `autor`→`author`, `zeit`→`time`, `herkunft`→`origin`
- `datei` (now `file`): `pruefsumme`→`checksum`, `titel`→`title`, `art`→`kind`, `volltext_indiziert`→`full_text_indexed`, `groesse`→`size`, `indiziert`→`indexed`
- `entityos_arbeitspaket` (now `entityos_work_package`): `paket_id`→`work_package_id`, `besteller`→`orderer`, `auftrag`→`task`, `womit`→`target`, `warum`→`why`, `ergebnis`→`result`, `beleg`→`evidence`, `erstellt`→`created`, `geaendert`→`changed`
- `entityos_artikel_zuordnung` (now `entityos_article_assignment`): `artikel_id`→`article_id`, `gehoert`→`belongs`, `grund`→`reason`, `sicherheit`→`security`, `erfasst`→`captured`
- `entityos_erfolge` (now `entityos_successes`): `art`→`kind`, `titel`→`title`, `wirkung`→`effect`, `beleg`→`evidence`, `gehoert`→`belongs`, `seit_zero`→`since_zero`, `datum`→`date`, `erfasst`→`captured`
- `entityos_profil` (now `entityos_profile`): `feld`→`field`, `wert`→`value`, `herkunft`→`origin`, `beleg`→`evidence`, `erfasst`→`captured`
- `entityos_projekte` (now `entityos_projects`): `projekt`→`project`, `gehoert`→`belongs`, `gebaut_von`→`built_from`, `erfolg`→`success`, `seit_zero`→`since_zero`, `beschreibung`→`description`, `beleg`→`evidence`, `herkunft`→`origin`, `erfasst`→`captured`
- `entityos_wirte` (now `entityos_hosts`): `wirt`→`host`, `gehoert_zu`→`belongs_to`, `erste_sichtung`→`first_review`, `zuletzt_gesehen`→`last_seen`, `gesund`→`healthy`, `quelle`→`source`
- `eos_architekt_quittungen` (now `eos_architect_receipts`): `quittung_id`→`receipt_id`, `hypothese_id`→`hypothesis_id`, `hypothese_quelle`→`hypothesis_source`, `hypothese_text`→`hypothesis_text`, `zweig`→`branch`, `reproduziert`→`reproduced`, `befund`→`finding`, `sicherer_rahmen`→`safer_frame`, `rahmen_grund`→`frame_reason`, `testboden_vorher`→`test_bed_before`, `testboden_nachher`→`test_bed_afterwards`, `nicht_schlechter`→`not_worse`, `nicht_schlechter_grund`→`not_worse_reason`, `bericht_vorher_hash`→`report_before_hash`, `bericht_nachher_hash`→`report_afterwards_hash`, `kanarie_status`→`canary_status`, `urteil`→`judgment`, `live_geschaltet`→`live_switched`, `hinweis`→`hint`
- `eos_bewertungen` (now `eos_evaluations`): `bewertung_id`→`evaluation_id`, `wert`→`value`, `frage_turn_id`→`question_turn_id`, `frage_hash`→`question_hash`, `frage_laenge`→`question_length`, `antwort_hash`→`answer_hash`, `antwort_laenge`→`answer_length`, `modell`→`model`
- `eos_bug_hypothesen` (now `eos_bug_hypotheses`): `beschreibung`→`description`, `befund`→`finding`
- `fehler` (now `error`): `art`→`kind`, `ausloeser_muster`→`trigger_pattern`, `was_passiert`→`was_happened`, `wie_erkannt`→`how_recognized`, `wie_vermieden`→`how_avoided`, `schwere`→`severity`, `beleg`→`evidence`, `quelle`→`source`, `erkannt_am`→`recognized_at`, `bestaetigt_durch`→`confirmed_through`
- `folgerung` (now `conclusion`): `art`→`kind`, `aussage`→`statement`, `begruendung`→`reasoning`, `gilt_fuer`→`applies_for`, `autor`→`author`, `zeit`→`time`, `widerlegt_durch`→`refuted_through`, `konfidenz`→`confidence`
- `folgerung_beleg` (now `conclusion_evidence`): `folgerung_id`→`conclusion_id`, `beleg_art`→`evidence_kind`, `beleg_id`→`evidence_id`
- `fts_index_artikel` (now `fts_index_article`): `titel`→`title`
- `fts_index_datei` (now `fts_index_file`): `titel`→`title`
- `fundort` (now `find_location`): `datei_id`→`file_id`, `pruefsumme`→`checksum`, `wirt`→`host`, `pfad`→`path`, `blase`→`bubble`, `geaendert`→`changed`
- `gedaechtnis_ausbeute` (now `memory_yield`): `rolle`→`role`, `bahn`→`lane`, `modell`→`model`, `genommen`→`taken`, `verworfen`→`discarded`, `gruende`→`reasons`
- `grabstein` (now `tombstone`): `was`→`activity`, `ziel_id`→`goal_id`, `autor`→`author`, `zeit`→`time`, `grund`→`reason`, `inhalt_hash`→`content_hash`
- `graph_kante` (now `graph_edge`): `source_kante_art`→`source_edge_kind`, `beleg`→`evidence`, `verfallen`→`expire`
- `graph_knoten` (now `graph_node`): `titel`→`title`, `quelle`→`source`, `datum`→`date`, `metadaten`→`metadata`, `verfallen`→`expire`
- `gw_absicht` (now `gw_intention`): `frage`→`question`, `werkzeuge`→`tools`, `aussenwirkung`→`external_effect`, `angekuendigt`→`announced`, `verdacht`→`suspicion`, `grund`→`reason`
- `gw_ausstrahlung` (now `gw_broadcast`): `artikel_id`→`article_id`, `wert`→`value`
- `gw_herkunft` (now `gw_origin`): `fremdtext`→`foreign_text`, `werkzeuge`→`tools`
- `gw_lernen` (now `gw_learning`): `merkmal`→`feature`, `artikel_id`→`article_id`, `belohnt`→`rewarded`
- `gw_wettbewerb` (now `gw_competition`): `artikel_id`→`article_id`, `salienz`→`salience`, `relevanz`→`relevance`, `neuheit`→`novelty`, `wert`→`value`, `zugelassen`→`approved`, `gewaehlt`→`chosen`
- `heim_belege` (now `home_evidence`): `beleg_id`→`evidence_id`, `wirt`→`host`, `aktion`→`action`, `nutzlast_sha256`→`payload_sha256`, `urteil`→`judgment`
- `kante` (now `edge`): `von`→`src`, `nach`→`dst`, `art`→`kind`, `beleg`→`evidence`, `konfidenz`→`confidence`, `erzeugt_am`→`generated_at`, `zeitquelle`→`time_source`, `verfallen`→`expire`
- `kb_auftrag` (now `kb_task`): `prozess`→`process`, `nutzlast`→`payload`, `zustand`→`state`, `versuche`→`attempts`, `letzter_grund`→`last_reason`, `gesperrte_bahnen`→`blocked_lanes`, `angelegt`→`created`, `geaendert`→`changed`
- `kb_buchung` (now `kb_booking`): `zeit`→`time`, `konto`→`account`, `zugang`→`access`, `menge`→`amount`, `einheit`→`unit`, `zweck`→`purpose`, `taetigkeit_id`→`activity_id`, `schluessel_hinweis`→`key_hint`, `quelle`→`source`, `roh_hash`→`raw_hash`
- `kb_konto` (now `kb_account`): `konto`→`account`, `anzeige`→`display`, `vorrang`→`priority`, `hat_eigenes_limit`→`hat_own_limit`, `eigenes_limit_wert`→`own_limit_value`, `eigenes_limit_einheit`→`own_limit_unit`, `eigenes_limit_fenster`→`own_limit_window`, `warnung_an`→`warning_to`, `wirt`→`host`, `angelegt`→`created`
- `kb_verdrahtung` (now `kb_wiring`): `prozess`→`process`, `bahn_erst`→`lane_first`, `bahn_zweit`→`lane_second`, `bahn_dritt`→`lane_third`, `hoechstanteil`→`highest_share`, `begruendung`→`reasoning`, `max_je_lauf`→`max_per_run`, `schema_pflicht`→`schema_duty`, `angelegt`→`created`
- `kb_warnung` (now `kb_warning`): `zeit`→`time`, `konto`→`account`, `zugang`→`access`, `art`→`kind`, `kennzahlen_json`→`metrics_json`
- `kb_zugang` (now `kb_access`): `zugang`→`access`, `anzeige`→`display`, `einheit`→`unit`, `fenster_dauer_sekunden`→`window_duration_seconds`, `fenster_limit`→`window_limit`, `woche_limit`→`week_limit`, `tageswechsel_stunde`→`day_switch_hour`, `spitzenzeit_json`→`peak_time_json`, `geteilt_mit`→`shared_with`, `besonderheit`→`specialty`, `mehrdeutiger_schluessel`→`ambiguous_key`, `angelegt`→`created`, `modell`→`model`, `zustand`→`state`, `zustand_grund`→`state_reason`, `zustand_gemessen`→`state_measured`, `grenzen_quelle`→`boundaries_source`, `unbekannt_felder`→`unknown_fields`, `unbekannt_grund`→`unknown_reason`, `kann_embedding`→`can_embedding`, `kann_schema`→`can_schema`, `kann_batch`→`can_batch`, `ausgereizt`→`exhausted`, `konten_anzahl`→`accounts_count`, `konten_getrennt`→`accounts_separated`, `schluessel_namen`→`key_names`
- `kommentar` (now `comment`): `artikel_id`→`article_id`, `autor`→`author`, `zeit`→`time`, `antwort_folgerung_id`→`answer_conclusion_id`
- `kuration` (now `curation`): `artikel_id`→`article_id`, `quelle`→`source`, `ereignis`→`event`, `klasse`→`class`, `neu_hash`→`new_hash`, `alt_groesse`→`alt_size`, `alt_zeilen`→`alt_lines`, `neu_groesse`→`new_size`, `neu_zeilen`→`new_lines`, `erkannt_am`→`recognized_at`, `zuletzt_geprueft_am`→`last_checked_at`, `noetig`→`necessary`
- `memory_tabelle` (now `memory_table`): `artikel_id`→`article_id`, `quelle`→`source`, `erstellt_am`→`created_at`
- `messung` (now `measurement`): `bauteil`→`component`, `quelle`→`source`, `zeile_hash`→`line_hash`, `was`→`metric`, `wert`→`value`, `einheit`→`unit`, `zeit`→`time`, `wirt`→`host`, `instanz`→`instance`, `roh`→`raw`
- `mv_prestage_turns`: `epistemik_json`→`epistemic_json`, `epistemik_bekannt_n`→`epistemic_known_n`, `epistemik_unbekannt_n`→`epistemic_unknown_n`, `korpus_treffer_n`→`corpus_hit_n`
- `mv_uebersetzung_ausfall` (now `mv_translation_failure`): `fehler`→`error`
- `om_hypothese_implikation` (now `om_hypothesis_implication`): `artikel_id`→`article_id`, `hypothese_id`→`hypothesis_id`, `hypothese_text`→`hypothesis_text`, `konfidenz`→`confidence`, `modell`→`model`, `erzeugt_am`→`generated_at`
- `om_lauf` (now `om_run`): `zeit`→`time`, `schritt`→`step`, `anzahl`→`count`, `hinweis`→`hint`
- `om_projekt` (now `om_project`): `art`→`kind`, `eltern_id`→`parents_id`, `konfidenz`→`confidence`, `begruendung`→`reasoning`, `anzahl_artikel`→`count_article`, `aktualisiert_am`→`updated_at`
- `om_projekt_kante` (now `om_project_edge`): `staerke`→`strength`, `beleg`→`evidence`, `aktualisiert_am`→`updated_at`
- `om_projekt_mitglied` (now `om_project_member`): `artikel_id`→`article_id`, `projekt_id`→`project_id`, `konfidenz`→`confidence`
- `om_skizze` (now `om_sketch`): `artikel_id`→`article_id`, `quelle`→`source`, `erzeugt_am`→`generated_at`
- `om_zusammenfassung` (now `om_summary`): `artikel_id`→`article_id`, `modell`→`model`, `erzeugt_am`→`generated_at`
- `problem`: `bauteil`→`component`, `quelle`→`source`, `zeile_hash`→`line_hash`, `art`→`kind`, `erkannt_am`→`recognized_at`, `geloest_am`→`solved_at`, `geloest_durch`→`solved_through`
- `pu_lage` (now `pu_position`): `schluessel`→`key`, `wert`→`value`, `zeit`→`time`
- `pu_takt` (now `pu_beat`): `folge`→`sequence`, `zeit`→`time`, `monoton`→`monotonic`, `art`→`kind`, `kosten_us`→`costs_us`, `modellaufrufe`→`model_calls`, `werkzeugaufrufe`→`tool_calls`
- `schluessel_lage` (now `key_position`): `schluessel`→`key`, `zuletzt_geprueft`→`last_checked`, `einordnung`→`classification`, `seit`→`since`, `fehlertext`→`error_text`, `modell_meinung`→`model_opinion`, `geprueft_gesamt`→`checked_total`, `gesund_gesamt`→`healthy_total`, `sonde`→`probe`, `rest_kontingent`→`rest_quota`
- `schluessel_lauf` (now `key_run`): `zeit`→`time`, `schluessel`→`key`, `einordnung`→`classification`, `fehlertext`→`error_text`, `sonde`→`probe`, `rest_kontingent`→`rest_quota`
- `sicht_arbeitsraum` (now `view_workspace`): `eintrag_id`→`entry_id`, `aufnahme_id`→`capture_id`, `kandidat_id`→`candidate_id`, `objekt_id`→`object_id`, `hypothese_id`→`hypothesis_id`, `angemeldet_am`→`registered_at`, `zuendungsgrund`→`ignition_reason`, `zuendung`→`ignition`, `abgelehnt_grund`→`rejected_reason`, `entschieden_am`→`decided_at`
- `sicht_aufnahme` (now `view_capture`): `aufnahme_id`→`capture_id`, `datei_id`→`file_id`, `quelle_id`→`source_id`, `quelle_klasse`→`source_class`, `bild_hash`→`image_hash`, `breite`→`width`, `hoehe`→`height`, `stufe`→`level`, `stufe_version`→`level_version`, `abruf_kontext`→`recall_context`, `abruf_treffer`→`recall_hit`, `dauer_ms`→`duration_ms`, `ergebnis`→`result`, `fehlergrund`→`error_reason`, `begonnen_am`→`begun_at`, `beendet_am`→`finished_at`
- `sicht_evidenz` (now `view_evidence`): `evidenz_id`→`evidence_id`, `aufnahme_id`→`capture_id`, `quelle_id`→`source_id`, `quelle_epoche`→`source_epoch`, `aufnahme_zeit`→`capture_time`, `eingang_zeit`→`entrance_time`, `rohbezug_hash`→`raw_reference_hash`, `raum_bezug`→`room_reference`, `beobachtungsart`→`observation_type`, `wert`→`value`, `bottom_up_praezision`→`bottom_up_precision`, `kalibrierung_ref`→`calibration_ref`, `autoritaet`→`authority`, `erzeugt_am`→`generated_at`
- `sicht_hypothese` (now `view_hypothesis`): `hypothese_id`→`hypothesis_id`, `aufnahme_id`→`capture_id`, `anker`→`anchor`, `art`→`kind`, `lesarten`→`readings`, `lesarten_geschlossen`→`readings_closed`, `stuetzende_evidenz`→`supporting_evidence`, `widersprechende_evidenz`→`contradictory_evidence`, `bestand_stuetze`→`inventory_support`, `sensor_praezision`→`sensor_precision`, `prior_praezision`→`prior_precision`, `kontext_verstaerkung`→`context_reinforcement`, `prior_dominanz`→`prior_dominance`, `zuversicht`→`confidence`, `zustand`→`state`, `vorgaenger_id`→`predecessor_id`, `abgeloest_von`→`resolved_from`, `erzeugt_am`→`generated_at`
- `sicht_kaskade_stufe` (now `view_cascade_level`): `stufe`→`level`, `zweck`→`purpose`, `fehlerfall`→`error_case`, `aktiv`→`active`, `gemessen_ms`→`measured_ms`, `messgrundlage`→`measurement_basis`, `quelle`→`source`
- `sicht_merkmal` (now `view_feature`): `merkmal_id`→`feature_id`, `aufnahme_id`→`capture_id`, `anker`→`anchor`, `verfahren`→`procedure`, `vektor`→`vector`, `rahmen_hash`→`frame_hash`, `erzeugt_am`→`generated_at`
- `sicht_nutzung` (now `view_usage`): `nutzung_id`→`usage_id`, `eintrag_id`→`entry_id`, `objekt_id`→`object_id`, `evidenz_id`→`evidence_id`, `nutzungsart`→`usage_type`, `beleg`→`evidence`, `festgestellt_von`→`determined_from`, `erzeugt_am`→`generated_at`
- `sicht_sichtbarkeit` (now `view_visibility`): `sichtbarkeit`→`visibility`, `vorlage_en`→`template_en`, `messbar`→`measurable`, `belegt_abwesenheit`→`evidenced_absence`, `zerfall`→`decay`, `warum`→`why`
- `sicht_weltobjekt` (now `view_world_object`): `objekt_id`→`object_id`, `quelle_id`→`source_id`, `semantische_identitaet`→`semantic_identity`, `erst_aufnahme_id`→`first_capture_id`, `erst_gesehen_am`→`first_seen_at`, `vorgaenger_id`→`predecessor_id`, `teilung_von`→`division_from`, `verschmelzung_von`→`merger_from`, `provenienz`→`provenance`
- `sicht_weltobjekt_stand` (now `view_world_object_stand`): `objekt_id`→`object_id`, `gueltig_ab`→`valid_from`, `gueltig_bis`→`valid_until`, `sichtbarkeit`→`visibility`, `sichtbarkeit_grund`→`visibility_reason`, `raum_zustand`→`room_state`, `merkmale_mit_evidenz`→`features_with_evidence`, `beziehungen_mit_evidenz`→`relations_with_evidence`, `letzte_positive_evidenz_epoche`→`last_positive_evidence_epoch`, `letzte_explizit_negative_epoche`→`last_explicit_negative_epoch`, `ungewissheit`→`uncertainty`, `stuetzende_hypothese_id`→`supporting_hypothesis_id`, `aufnahme_id`→`capture_id`, `erzeugt_am`→`generated_at`
- `sicht_zuordnung` (now `view_assignment`): `zuordnung_id`→`assignment_id`, `aufnahme_id`→`capture_id`, `anker`→`anchor`, `objekt_id`→`object_id`, `entscheidung`→`decision`, `begruendung`→`reasoning`, `aehnlichkeit`→`similarity`, `abstand_zum_zweiten`→`distance_to_the_second`, `verfahren`→`procedure`, `verfahren_version`→`procedure_version`, `erzeugt_am`→`generated_at`
- `speicher_rueckweg` (now `memory_return_path`): `pfad`→`path`, `erfasst`→`captured`, `warum`→`why`, `modelle`→`models`, `verzeichnis`→`directory`
- `speicherwacht_log` (now `memory_watch_log`): `belegt_prozent`→`evidenced_percent`, `frei_gb`→`free_gb`, `stufe`→`level`, `gehandelt`→`handled`, `befreit_gb`→`freed_gb`, `bericht`→`report`, `gezaehlt_gb`→`counted_gb`, `luecke_gb`→`gap_gb`, `nicht_zaehlbar`→`not_countable`, `bilanz_urteil`→`balance_judgment`
- `taetigkeit` (now `activity`): `wirt`→`host`, `instanz`→`instance`, `sitzung`→`session`, `zeit`→`time`, `werkzeug`→`tool`, `ziel_pfad`→`goal_path`, `aktion`→`action`, `ergebnis`→`result`, `quelle`→`source`, `zeile_nr`→`line_nr`, `roh_hash`→`raw_hash`
- `taetigkeit_kante` (now `activity_edge`): `taetigkeit_id`→`activity_id`, `artikel_id`→`article_id`, `art`→`kind`, `beleg`→`evidence`
- `vd_aufnahme` (now `vd_capture`): `zeit`→`time`, `strom`→`stream`, `neu`→`new`, `geaendert`→`changed`, `offen_gesamt`→`open_total`, `schwelle`→`threshold`, `ausgeloest`→`triggered`
- `vd_gesehen` (now `vd_seen`): `strom`→`stream`, `zeit`→`time`, `anreicherung_id`→`enrichment_id`
- `vd_grenze` (now `vd_border`): `zugang`→`access`, `anzahl_429`→`count_429`, `erste_429`→`first_429`, `letzte_429`→`last_429`, `letzte_wartezeit`→`last_wait_time`, `rufe_ohne_429`→`call_without_429`, `bemerkung`→`remark`
- `vd_lauf` (now `vd_run`): `zeit`→`time`, `strom`→`stream`, `quellen`→`sources`, `bahn`→`lane`, `modell`→`model`, `dauer_ms`→`duration_ms`, `token_ein`→`token_on`, `token_aus`→`token_off`, `ergebnis`→`result`, `grund`→`reason`, `anreicherung_id`→`enrichment_id`, `verdichtung_id`→`compression_id`
- `vd_strom` (now `vd_stream`): `strom`→`stream`, `schwelle`→`threshold`, `rate_je_stunde`→`rate_per_hour`, `rate_beleg`→`rate_evidence`, `aktiv`→`active`, `angelegt`→`created`, `letzte_pruefung`→`last_verification`, `letzter_lauf`→`last_run`
- `vp_alias_df`: `wort`→`word`, `gebaut_am`→`built_at`
- `vp_datei_fts` (now `vp_file_fts`): `titel`→`title`, `datei_id`→`file_id`
- `vp_dir_fts`: `verzeichnisname`→`directory_name`, `datei_id`→`file_id`
- `vp_edge_lern` (now `vp_edge_learning`): `edge_art`→`edge_kind`, `gewicht`→`weight`, `beobachtungen`→`observations`, `zuletzt_gelernt`→`last_learned`, `gesehen`→`seen`, `genutzt`→`used`
- `vp_edge_lern_backup_preflift` (now `vp_edge_learning_backup_preflift`): `edge_art`→`edge_kind`, `gewicht`→`weight`, `beobachtungen`→`observations`, `zuletzt_gelernt`→`last_learned`
- `vp_ereignis` (now `vp_event`): `zeit`→`time`, `art`→`kind`
- `vp_erfolgsmarke` (now `vp_success_marker`): `frage`→`question`, `anker`→`anchor`, `getragen`→`carried`, `quelle`→`source`
- `vp_gesehen` (now `vp_seen`): `lauf`→`run`, `zeit`→`time`
- `vp_karte_region` (now `vp_map_region`): `projekt`→`project`, `art`→`kind`, `artikel_n`→`article_n`, `landmarken`→`landmarks`
- `vp_karte_version` (now `vp_map_version`): `gebaut_am`→`built_at`, `anlass`→`occasion`, `regionen`→`regions`, `landmarken`→`landmarks`, `wegweiser`→`signpost`, `korpus_artikel`→`corpus_article`, `korpus_kanten`→`corpus_edges`, `verhaeltnis`→`ratio`, `erkundungsanteil`→`exploration_share`, `dauer_s`→`duration_s`
- `vp_karte_wegweiser` (now `vp_map_signpost`): `wort`→`word`, `staerke`→`strength`
- `vp_lese_log` (now `vp_read_log`): `zeit`→`time`, `ort_id`→`place_id`, `paket_id`→`work_package_id`, `erlaubt`→`allowed`, `grund`→`reason`
- `vp_paket_log` (now `vp_work_package_log`): `paket_id`→`work_package_id`, `zeit`→`time`, `epoch_sekunden`→`epoch_seconds`, `frage`→`question`, `orte_json`→`places_json`
- `vp_plan_cache`: `erzeugt_am`→`generated_at`, `treffer_anzahl`→`hit_count`, `zuletzt_getroffen`→`last_met`
- `vp_sitzung` (now `vp_session`): `rechner`→`computer`, `rolle`→`role`, `gestartet`→`started`, `lebenszeichen`→`sign_of_life`
- `vp_snapshot`: `erzeugt_am`→`generated_at`, `normals_bestanden`→`normals_passed`, `beobachtungen_gesamt`→`observations_total`, `edge_lern_snapshot`→`edge_learning_snapshot`
- `vp_weg` (now `vp_path`): `von`→`src`, `nach`→`dst`, `art`→`kind`, `nutzung`→`usage`, `getragen`→`carried`, `guete`→`quality`, `sitzungen`→`sessions`, `erste_nutzung`→`first_usage`, `letzte_nutzung`→`last_usage`
- `wa_ereignis` (now `wa_event`): `zeit`→`time`, `art`→`kind`, `ziel`→`goal`, `quelle`→`source`
- `wa_grenze` (now `wa_border`): `zeit`→`time`
- `wa_snapshot`: `ziel`→`goal`, `zeit`→`time`
- `weg` (now `path`): `ursprung`→`origin`, `ziel_wirt`→`goal_host`, `ziel_dienst`→`goal_service`, `ziel_pfad`→`goal_path`, `konto`→`account`, `befehl`→`command`, `darf`→`may`, `schritte`→`steps`, `erreichbar`→`reachable`, `fehler`→`error`, `zuletzt_bewiesen`→`last_proven`, `beleg`→`evidence`
- `wk_aufgabe` (now `wk_task`): `art`→`kind`, `artikel_id`→`article_id`, `wert`→`value`, `zustand`→`state`, `versuche`→`attempts`, `letzter_grund`→`last_reason`, `angelegt`→`created`, `geaendert`→`changed`
- `wm_cast_regel` (now `wm_cast_rule`): `von_domaene`→`from_domain`, `nach_domaene`→`to_domain`, `erlaubt`→`allowed`, `bedingung`→`condition`, `beleg`→`evidence`, `kandidat`→`candidate`, `offen`→`open`, `erzeugt_am`→`generated_at`
- `wm_guss_log` (now `wm_cast_log`): `zeit`→`time`, `von_domaene`→`from_domain`, `nach_domaene`→`to_domain`, `ergebnis`→`result`, `grund`→`reason`, `bedingung`→`condition`, `beleg`→`evidence`, `gegenstand`→`item`, `kandidat`→`candidate`, `offen`→`open`
- `wm_lesart` (now `wm_reading`): `lesart_id`→`reading_id`, `artikel_id`→`article_id`, `achse`→`axis`, `wert`→`value`, `kontext_json`→`context_json`, `domaene`→`domain`, `quelle`→`source`, `konfidenz`→`confidence`, `erzeugt_am`→`generated_at`, `gueltig_von`→`valid_from`, `gueltig_bis`→`valid_until`, `kandidat`→`candidate`, `offen`→`open`, `offen_grund`→`open_reason`
- `wm_topologie` (now `wm_topology`): `von`→`src`, `nach`→`dst`, `topologie`→`topology`, `herkunft_art`→`origin_kind`, `gewicht`→`weight`, `quelle`→`source`, `erzeugt_am`→`generated_at`, `gueltig_von`→`valid_from`, `gueltig_bis`→`valid_until`, `kandidat`→`candidate`, `offen`→`open`, `offen_grund`→`open_reason`
- `wm_topologie_name` (now `wm_topology_name`): `topologie`→`topology`, `h_nummer`→`h_number`, `bedeutung`→`meaning`, `kandidat`→`candidate`, `offen`→`open`
- `zero_raum` (now `zero_room`): `mensch`→`human`, `platz`→`place`, `was`→`activity`, `womit`→`target`, `zustand`→`state`, `seit`→`since`, `spitzname`→`nickname`
- `zero_raum_ruf` (now `zero_room_call`): `von`→`src`
- `star_konfig` (now `star_config`): `schluessel`→`key`, `wert`→`value`, `typ`→`type`, `quelle`→`source`, `geaendert`→`changed`
- `star_digest`: `datum`→`date`, `titel`→`title`, `geholt_am`→`fetched_at`, `lauf_id`→`run_id`
- `star_digest_lauf` (now `star_digest_run`): `lauf_id`→`run_id`, `dauer_ms`→`duration_ms`, `quelle`→`source`, `lookback_tage`→`lookback_days`, `fehler`→`error`, `unveraendert`→`unchanged`
- `star_faehigkeit` (now `star_ability`): `zugelassen`→`approved`, `grund`→`reason`, `geaendert`→`changed`
- `udb_nvidia_embedding`: `artikel_id`→`article_id`, `quelle_tabelle`→`source_table`, `modell`→`model`, `erstellt_am`→`created_at`
- `retrieval_episodes_semantisch` (now `retrieval_episodes_semantic`): `modell`→`model`, `kandidaten_anzahl`→`candidates_count`, `ausgewaehlt_json`→`selected_json`, `mechanisch_selected_json`→`mechanical_selected_json`, `weicht_ab`→`deviates_from`
- `bau_historie` (now `build_history`): `eintrag_id`→`entry_id`, `beschreibung`→`description`, `abgeschlossen_am`→`completed_at`, `von`→`src`, `messergebnis`→`measurement_result`, `beleg`→`evidence`, `erzeugt_am`→`generated_at`
- `gw_dauersieger` (now `gw_champion`): `artikel_id`→`article_id`, `serie`→`series`, `zuletzt_ts`→`last_ts`, `zuletzt_session`→`last_session`
- `star_sebukku`: `grund`→`reason`
- `system_gesundheit` (now `system_health`): `cpu_prozent`→`cpu_percent`, `ram_prozent`→`ram_percent`, `disk_prozent`→`disk_percent`, `kerne`→`cores`, `quelle`→`source`, `roh`→`raw`
- `system_bestand` (now `system_inventory`): `lauf_id`→`run_id`, `kategorie`→`category`, `quelle`→`source`
- `vault_uebersicht` (now `vault_overview`): `konto`→`account`, `letzte_nutzung`→`last_usage`, `fehlschlaege_in_folge`→`failures_in_sequence`, `letzte_latenz_ms`→`last_latency_ms`, `letzter_http_status`→`last_http_status`, `erzeugt_von`→`generated_from`, `erzeugt_am`→`generated_at`, `aktualisiert_am`→`updated_at`, `loeschen_angefordert`→`delete_requested`, `loesch_grund`→`delete_reason`
- `vault_ereignis` (now `vault_event`): `aktion`→`action`, `eintrag_id`→`entry_id`, `grund`→`reason`

## Indexes

| old | new |
|---|---|
| `idx_ziele_status` | `idx_goals_status` |
| `idx_mg_drift_kanal_ts` | `idx_mg_drift_channel_ts` |
| `idx_mg_haltung_status` | `idx_mg_stance_status` |
| `idx_mg_haltung_thema_version` | `idx_mg_stance_topic_version` |
| `idx_mg_widerspruch_haltung_offen` | `idx_mg_contradiction_stance_open` |
| `idx_mg_drift_sperre_kanal` | `idx_mg_drift_lock_channel` |
| `idx_hook_digest_kanal_ts` | `idx_hook_digest_channel_ts` |
| `idx_hook_reentry_kanal_ts` | `idx_hook_reentry_channel_ts` |
| `idx_hook_raum_puls_kanal_ts` | `idx_hook_room_pulse_channel_ts` |
| `idx_hook_raum_verlassen_kanal_ts` | `idx_hook_room_leave_channel_ts` |
| `architekt_engine_log_ts_idx` | `architect_engine_log_ts_idx` |
| `eos_architekt_quittungen_hyp_idx` | `eos_architect_receipts_hyp_idx` |
| `eos_bewertungen_session_idx` | `eos_evaluations_session_idx` |
| `eos_bug_hypothesen_status_idx` | `eos_bug_hypotheses_status_idx` |
| `eos_bug_hypothesen_user_idx` | `eos_bug_hypotheses_user_idx` |
| `gw_absicht_ts` | `gw_intention_ts` |
| `gw_ausstrahlung_ts` | `gw_broadcast_ts` |
| `gw_herkunft_ts` | `gw_origin_ts` |
| `idx_arbeitspaket_stand` | `idx_work_package_stand` |
| `idx_artikel_art` | `idx_article_kind` |
| `idx_artikel_baunotiz_lookup` | `idx_article_construction_note_lookup` |
| `idx_artikel_epistemic_class` | `idx_article_epistemic_class` |
| `idx_artikel_logical_id` | `idx_article_logical_id` |
| `idx_artikel_projekt` | `idx_article_project` |
| `idx_artikel_quelle` | `idx_article_source` |
| `idx_artikel_sphaere` | `idx_article_sphere` |
| `idx_artikel_status` | `idx_article_status` |
| `idx_artikel_verdichtung_lookup` | `idx_article_compression_lookup` |
| `idx_asuchtext_blase` | `idx_article_search_text_bubble` |
| `idx_bahn_lauf_art_zeit` | `idx_lane_run_kind_time` |
| `idx_bearbeitung_artikel` | `idx_processing_article` |
| `idx_erfolgsmarke_region` | `idx_success_marker_region` |
| `idx_fehler_art` | `idx_error_kind` |
| `idx_fehler_schwere` | `idx_error_severity` |
| `idx_folgerung_beleg_fid` | `idx_conclusion_evidence_fid` |
| `idx_folgerung_gilt_fuer` | `idx_conclusion_applies_for` |
| `idx_fundort_blase` | `idx_find_location_bubble` |
| `idx_fundort_datei` | `idx_find_location_file` |
| `idx_fundort_pruefsumme` | `idx_find_location_checksum` |
| `idx_grabstein_ziel` | `idx_tombstone_goal` |
| `idx_graph_kante_source_epoch` | `idx_graph_edge_source_epoch` |
| `idx_graph_kante_target_epoch` | `idx_graph_edge_target_epoch` |
| `idx_graph_knoten_external` | `idx_graph_node_external` |
| `idx_graph_knoten_type` | `idx_graph_node_type` |
| `idx_kante_nach` | `idx_edge_to` |
| `idx_kante_von` | `idx_edge_from` |
| `idx_karte_wegweiser_wort` | `idx_map_signpost_word` |
| `idx_kommentar_artikel` | `idx_comment_article` |
| `idx_kommentar_status` | `idx_comment_status` |
| `idx_memory_artikel` | `idx_memory_article` |
| `idx_messung_bauteil` | `idx_measurement_component` |
| `idx_messung_einheit` | `idx_measurement_unit` |
| `idx_messung_zeile` | `idx_measurement_line` |
| `idx_om_implikation_artikel` | `idx_om_implication_article` |
| `idx_om_mitglied_artikel` | `idx_om_member_article` |
| `idx_om_mitglied_projekt` | `idx_om_member_project` |
| `idx_problem_bauteil` | `idx_problem_component` |
| `idx_problem_zeile_hash` | `idx_problem_line_hash` |
| `idx_taetigkeit_sitzung` | `idx_activity_session` |
| `idx_taetigkeit_ziel_pfad` | `idx_activity_goal_path` |
| `idx_vd_aufnahme_strom` | `idx_vd_capture_stream` |
| `idx_vd_lauf_strom` | `idx_vd_run_stream` |
| `idx_vp_weg_guete` | `idx_vp_path_quality` |
| `idx_weg_ursprung_ziel` | `idx_path_origin_goal` |
| `idx_weg_ziel` | `idx_path_goal` |
| `idx_wk_aufgabe_art` | `idx_wk_task_kind` |
| `idx_wk_aufgabe_wahl` | `idx_wk_task_choice` |
| `ix_kuration_status_noetig` | `ix_curation_status_necessary` |
| `ix_schluessel_lauf_zeit` | `ix_key_run_time` |
| `ix_taetigkeit_zeit` | `ix_activity_time` |
| `kb_auftrag_zustand` | `kb_task_state` |
| `kb_buchung_batch` | `kb_booking_batch` |
| `kb_buchung_kz_zeit` | `kb_booking_kz_time` |
| `kb_warnung_zeit` | `kb_warning_time` |
| `sicht_arbeitsraum_turn` | `view_workspace_turn` |
| `sicht_aufnahme_quelle` | `view_capture_source` |
| `sicht_aufnahme_turn` | `view_capture_turn` |
| `sicht_evidenz_art` | `view_evidence_kind` |
| `sicht_evidenz_aufnahme` | `view_evidence_capture` |
| `sicht_hypothese_aufnahme` | `view_hypothesis_capture` |
| `sicht_hypothese_offen` | `view_hypothesis_open` |
| `sicht_merkmal_aufnahme` | `view_feature_capture` |
| `sicht_merkmal_verfahren` | `view_feature_procedure` |
| `sicht_nutzung_turn` | `view_usage_turn` |
| `sicht_stand_jetzt` | `view_stand_now` |
| `sicht_stand_objekt` | `view_stand_object` |
| `sicht_weltobjekt_quelle` | `view_world_object_source` |
| `sicht_zuordnung_aufnahme` | `view_assignment_capture` |
| `wm_guss_log_ix1` | `wm_cast_log_ix1` |
| `wm_lesart_ix1` | `wm_reading_ix1` |
| `wm_lesart_ix2` | `wm_reading_ix2` |
| `wm_lesart_ix3` | `wm_reading_ix3` |
| `wm_topologie_ix1` | `wm_topology_ix1` |
| `wm_topologie_ix2` | `wm_topology_ix2` |
| `wm_topologie_ix3` | `wm_topology_ix3` |

## Views

| old | new |
|---|---|
| `mg_drift_sperre_unreleased` | `mg_drift_lock_unreleased` |
| `kondensat` | `condensate` |
| `messung_kompakt` | `measurement_compact` |
| `mv_prestage_lernbild` | `mv_prestage_learning_image` |

## Triggers

| old | new |
|---|---|
| `sicht_evidenz_kein_aendern` | `view_evidence_none_change` |
| `sicht_evidenz_kein_loeschen` | `view_evidence_none_delete` |

## Enum values (CHECK / status columns; per NEW table and column)

- `goals.status`: `offen`→`open`
- `mg_stance.status`: `aktiv`→`active`
- `article.generated_at`: `gemessen`→`measured`
- `article.origin`: `gemessen`→`measured`, `nutzer`→`user`
- `processing.origin`: `nutzer`→`user`
- `entityos_hosts.source`: `herzschlag`→`heartbeat`
- `eos_bug_hypotheses.bug_id`: `OFFEN`→`OPEN`
- `eos_bug_hypotheses.status`: `OFFEN`→`OPEN`, `REPRODUZIERT`→`REPRODUCED`, `WIDERLEGT`→`REFUTED`, `BEHOBEN`→`FIXED`
- `error.kind`: `daten`→`data`, `provenienz`→`provenance`, `methode`→`method`
- `error.severity`: `hoch`→`high`, `mittel`→`medium`, `niedrig`→`low`
- `conclusion.kind`: `hypothese`→`hypothesis`, `implikation`→`implication`, `lehre`→`lesson`
- `conclusion.status`: `offen`→`open`, `gestuetzt`→`supported`, `widerlegt`→`refuted`, `abgeloest`→`resolved`
- `conclusion_evidence.evidence_kind`: `protokoll`→`protocol`, `artikel`→`article`, `messung`→`measurement`, `kante`→`edge`, `datei`→`file`
- `kb_task.state`: `offen`→`open`, `laeuft`→`running`, `fertig`→`finished`, `unbedienbar`→`unusable`
- `kb_task.changed`: `unbedienbar`→`unusable`
- `kb_booking.source`: `buchen`→`book`
- `kb_warning.kind`: `ueber_norm`→`over_norm`, `reset_naehert_sich`→`reset_approaching`, `verbrauch_ohne_fortschritt`→`consumption_without_progress`, `mehrdeutiger_schluessel`→`ambiguous_key`, `kein_limit_kein_muster`→`no_limit_no_pattern`
- `kb_access.created`: `ungeprueft`→`untested`
- `comment.status`: `offen`→`open`, `beantwortet`→`answered`, `gestuetzt`→`supported`, `widerlegt`→`refuted`, `unentscheidbar`→`undecidable`
- `curation.status`: `offen`→`open`
- `problem.kind`: `huerde`→`hurdle`, `risiko`→`risk`, `offene_frage`→`open_question`
- `problem.status`: `offen`→`open`, `geloest`→`solved`
- `view_evidence.calibration_ref`: `UNKALIBRIERT`→`UNCALIBRATED`
- `view_evidence.authority`: `NUR_BEOBACHTUNG`→`ONLY_OBSERVATION`
- `wk_task.state`: `offen`→`open`, `laeuft`→`running`, `fertig`→`finished`, `verworfen`→`discarded`, `unbedienbar`→`unusable`
- `udb_nvidia_embedding.source_table`: `artikel`→`article`
- `retrieval_episodes_semantic.status`: `FEHLER`→`ERROR`

## star_config keys

| old | new |
|---|---|
| `abruf.generisch_schwelle` | `recall.generic_threshold` |
| `abruf.gesperrte_artikel_praefixe` | `recall.blocked_article_prefixes` |
| `abruf.gesperrte_paket_teilstrings` | `recall.blocked_work_package_substrings` |
| `wege.grundzuwachs` | `paths.base_growth` |
| `wege.verfall` | `paths.expiry` |
| `wege.schwelle_schnell` | `paths.threshold_fast` |
| `wege.schwelle_autobahn` | `paths.threshold_highway` |
| `wege.tunnel_min_sitzungen` | `paths.tunnel_min_sessions` |
| `wege.tunnel_min_guete` | `paths.tunnel_min_quality` |
| `wege.max_sitzungen_gemerkt` | `paths.max_sessions_remembered` |
| `raum_moeglichkeit.cap_seite` | `room_possibility.cap_page` |
| `raum_moeglichkeit.cap_zeichen_je_aussage` | `room_possibility.cap_character_per_statement` |
| `leases.ttl_sekunden` | `leases.ttl_seconds` |
| `geld_saetze` | `money_sentences` |
| `stopwoerter` | `stop_words` |
| `kurz_ausnahmen` | `short_exceptions` |
| `anker` | `anchor` |
| `architekt.aktiv` | `architect.active` |
| `architekt.seit` | `architect.since` |
| `kognition.aktiv` | `cognition.active` |
| `kognition.modell` | `cognition.model` |
| `kognition.ollama_url` | `cognition.ollama_url` |
| `kognition.timeout_sekunden` | `cognition.timeout_seconds` |
| `embedding.aktiv` | `embedding.active` |
| `embedding.modell` | `embedding.model` |
| `embedding.timeout_sekunden` | `embedding.timeout_seconds` |
| `benachrichtigung.ton_bei_warten` | `notification.sound_when_waiting` |
| `gw.dauersieger_schwelle` | `gw.champion_threshold` |
| `gw.dauersieger_malus` | `gw.champion_malus` |
| `gw.lernen_aktiv` | `gw.learning_active` |
| `gw.frage_kappung` | `gw.question_capping` |
| `sicht.wiedererkannt_schwelle` | `view.recognized_threshold` |
| `sicht.mehrdeutig_abstand` | `view.ambiguous_distance` |
| `persona.reinjektion_n` | `persona.re_injection_n` |
| `verdichtung.aktiv` | `compression.active` |
| `verdichtung.provider` | `compression.provider` |
| `verdichtung.fallback_kette` | `compression.fallback_chain` |
| `verdichtung.modell` | `compression.model` |
| `verdichtung.modell_fallback` | `compression.model_fallback` |
| `verdichtung.glm_thinking` | `compression.glm_thinking` |
| `verdichtung.max_tokens` | `compression.max_tokens` |
| `verdichtung.timeout_s` | `compression.timeout_s` |
| `verdichtung.retrieval` | `compression.retrieval` |
| `verdichtung.retrieval_anfragen` | `compression.retrieval_inquiries` |
| `betriebsart` | `operation_mode` |
| `architekt_governance.zug_intervall` | `architect_governance.move_interval` |
| `pool_quote.fenster_sekunden` | `pool_quote.window_seconds` |
| `pool_quote.mindest_output_tokens` | `pool_quote.minimum_output_tokens` |
| `pool_quote.schwelle_quote` | `pool_quote.threshold_quote` |
| `pool_quote.cooldown_sekunden` | `pool_quote.cooldown_seconds` |
| `chatgpt_idle.schwelle_minuten` | `chatgpt_idle.threshold_minutes` |
| `chatgpt_idle.cooldown_sekunden` | `chatgpt_idle.cooldown_seconds` |
| `telegram.aktiv` | `telegram.active` |
| `gespraech.aktiv` | `conversation.active` |
| `cortex.aktiv` | `cortex.active` |
| `cortex.min_eskalation_sekunden` | `cortex.min_escalation_seconds` |
| `gespraech.berechtigung` | `conversation.permission` |
| `gespraech.tts_modell` | `conversation.tts_model` |
| `gespraech.tts_stimme` | `conversation.tts_voice` |
| `gespraech.stt_modell` | `conversation.stt_model` |
| `gespraech.mic_geraet` | `conversation.mic_device` |
| `gespraech.verifikation_status` | `conversation.verification_status` |
| `gespraech.verifikation_detail` | `conversation.verification_detail` |
| `gespraech.konversation_timeout_sekunden` | `conversation.conversation_timeout_seconds` |
| `gespraech.realtime_modell` | `conversation.realtime_model` |
| `gespraech.realtime_stimme` | `conversation.realtime_voice` |
| `gespraech.realtime_reasoning_effort` | `conversation.realtime_reasoning_effort` |
| `gespraech.stille_timeout_sekunden` | `conversation.silence_timeout_seconds` |
| `voice_loop.gewichte` | `voice_loop.weights` |
| `voice_loop.wait_basiswert` | `voice_loop.wait_base_value` |
| `voice_loop.reopen_fenster_s` | `voice_loop.reopen_window_s` |
| `voice_loop.reopen_schwelle` | `voice_loop.reopen_threshold` |
| `voice_loop.qwen_modell` | `voice_loop.qwen_model` |
| `voice_loop.konversations_timeout_s` | `voice_loop.conversation_timeout_s` |
| `voice_loop.initiative_modus` | `voice_loop.initiative_mode` |

Prefixes: `persona.neu_injizieren.*`→`persona.new_inject.*`, `persona.zaehler.*`→`persona.counter.*`, `ausweich.*`→`fallback.*`


Suffixes: `*.angeboten`→`*.offered`, `*.vollzogen`→`*.executed`


## Environment variables

None renamed. The env-var names in the contract (`docs/zero/contract_env.json`) were already English.

## CLI (star_cli.py) subcommands, flags, slash commands

| old | new |
|---|---|
| `--auftrag` | `--task` |
| `--aussage` | `--statement` |
| `--befehl` | `--command` |
| `--beleg` | `--evidence` |
| `--datei` | `--file` |
| `--ergebnis` | `--result` |
| `--gilt-fuer` | `--applies-for` |
| `--grund` | `--reason` |
| `--nachricht` | `--message` |
| `--paket-id` | `--work-package-id` |
| `--projekt-wurzel` | `--project-root` |
| `--quelle` | `--source` |
| `--schwelle-je-kern` | `--threshold-per-core` |
| `--thema` | `--topic` |
| `--warum` | `--why` |
| `--was` | `--activity` |
| `--womit` | `--target` |
| `/architekt` | `/architect` |
| `/bild` | `/image_studio` |
| `architekt-aus` | `architect-off` |
| `architekt-dialog-ende` | `architect-dialog-end` |
| `architekt-dialog-start` | `architect-dialog-start` |
| `architekt-ein` | `architect-on` |
| `bug-einstufen` | `bug-classify` |
| `datei:` | `file:` |
| `geheimnis-schwaerzen` | `secret-redact` |
| `gespraech-raum-puls` | `conversation-room-pulse` |
| `paket-anlegen` | `work-package-create` |
| `passwort-ist` | `password-is` |
| `raum-puls-global` | `room-pulse-global` |
| `raum-verlassen-global` | `room-leave-global` |
| `sebukku-anbieten` | `sebukku-offer` |
| `sebukku-vollziehen` | `sebukku-execute` |
| `system-bestand` | `system-inventory` |
| `system-gesundheit` | `system-health` |
| `thema-status` | `topic-status` |

## Evidence formats

- `datei:<path>:<sha256>` → `file:<path>:<sha256>`
- `effect:<id>` → `effect:<id>`
- `test:<exit>:<text>` → `test:<exit>:<text>`

Stored `datei:` evidence is still read; `file:` is the form written from now on. The verification manifest key `PRUEFUNG.json` is written by `zero/code/export/agentzero_export.py` (outside this change); the in-tree manifest is `VERIFICATION.json`.

## Identifier tokens (Python names, constants, JSON keys)

1545 word-level mappings applied inside identifiers (full list in `rename_map.json` -> `identifier_tokens`). Examples: `ABBRUCH`→`ABORT`, `ABGELEHNT`→`REJECTED`, `ABRUF_FREMDBLOECKE`→`RECALL_FOREIGN_BLOCKS`, `ANKER-Karte`→`ANCHOR-Map`, `ANKER_DEFAULT`→`ANCHOR_DEFAULT`, `ARCHITEKT_GOVERNANCE_TEXT_CACHE`→`ARCHITECT_GOVERNANCE_TEXT_CACHE`, `ARCHITEKT_PERSONA_FALLBACK`→`ARCHITECT_PERSONA_FALLBACK`, `AUSFALL`→`FAILURE`, `Abklingzeit-Schluessel`→`Abklingzeit-Key`, `Aktivierungs-Runde`→`Aktivierungs-Round`, `Anti-Dauersieger-Schwelle`→`Anti-Champion-Threshold`, `Architektur`→`Architecture`.

## German on purpose

| what | why |
|---|---|
| scripts/star/data/*.de.md, sebukku.de.txt (4 files) | localized German variants of persona/governance text; content stays German, names are English |
| `lang-data:de` blocks in star_core.py, star_cycle.py, secret_pattern.py | language data: German stop words, accepted words, tool-error prefix ('fehler'), password keywords for secret detection; changing them breaks detection for German input |
| star_core.py comments naming external code: visueller_cycle(), menschliche_rueckmeldung(), produkt/microclay_retrieval.py, forschung-digest.json | names of code and files outside this tree (not renamable here) |
| star_cycle.py comments: schranke/wache-koenig.py, _sprachkuerzel() | external guardian script and external helper names |
| scripts/image_studio, skills/image_studio/SKILL.md, commands/image_studio.md, docs/zero/status.md: bild.py, omega-bildstudio, `bild` CLI | external service/CLI names (omega-browser/studio); only the plugin side was renamed to image_studio |
| star_core.py:184 quoted keyword "sprechen" | quotes user data (a retrieval query) |
| zero/unifieddb/migrate_to_english.py, .sql, docs/zero/rename_map.json, RENAME_MAP.md | contain the old German names by definition (old -> new) |
| JSON key `"zeile"` in `star_core.py` (tat entries) | written by the external merke.py; the reader must keep the German key. Same for the GRID payload key `zeile` and retina-frage `--zeile` (kept by the core branch) |

## Out of scope / follow-ups

- `zero/code/**` (221 tracked files, German directory and file names such as `unterbau/`, `udb/abruf/`, `produkt/`) and the top-level `zero/` files (`ZIELE.md`, `EntityOS-Architektur-Skizze-2026-08-22.md`) were not named in the task scope and were not renamed.
  **Consistency risk:** 115 files under `zero/code/` (about 2,600 references, e.g. `udb/abruf/paket.py`, `unterbau/vorprozessor.py`, `unterbau/suche.py`) still use the old German table and column names. They no longer match `zero/unifieddb/schema.sql`. Running them against a migrated or freshly created DB needs the same rename applied (`rename_map.json` has everything required: tables, columns, enum values, config keys). A mechanical pass is possible; it was not done here because it changes ~4.5 MB of code outside the stated scope.
- Rust side: `src/zero/entity.rs` comments (lines 16, 448, 466) and `src/zero/entity_test.rs:48` still say `f3_pfade` (now `f3_paths`); `src/` belongs to the parallel rename branch.

## Assumptions (decided without asking, safe defaults)

- `zero/code/**` and the top-level `zero/` files stay unrenamed: the task scope names only `plugins/`, `zero/unifieddb/` and `docs/zero/`, and a 4.5 MB code rename belongs in its own reviewed change. `rename_map.json` is the input for that pass.
- Enum values listed in `value_map` are rewritten in every table that holds them, also in tables without a CHECK constraint.
- Stored `datei:` evidence strings are kept as written; `file:` applies to new evidence only.
- The `.sql` migration log is a reference artifact; the Python runner is the supported way to migrate.
