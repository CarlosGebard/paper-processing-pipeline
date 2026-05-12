# Test Inventory

Purpose: map current tests before cleanup. This is audit input, not endorsement.

Status notes:

- `analytics` tests are stale because `analytics/` is leaving this repo.
- `tests/test_cli_smoke.py` is current smoke coverage for local CLI and bridge mount.
- Full suite currently not reliable until stale analytics references are removed or migrated.

## Files

| File | Area | Status |
|---|---|---|
| `tests/test_analytics_cli_smoke.py` | old analytics CLI | stale |
| `tests/test_cli_smoke.py` | local CLI smoke/routing | keep candidate |
| `tests/test_config_loader.py` | config and path resolution | keep candidate |
| `tests/test_docling_v2_adapter.py` | Docling conversion and document shaping | keep candidate |
| `tests/test_gap_discarded_audit_script.py` | gap discard audit script | review |
| `tests/test_metadata_csv_script.py` | old analytics metadata CSV export | stale candidate |
| `tests/test_metadata_from_doi_script.py` | one-DOI metadata script | keep candidate |
| `tests/test_metadata_gap_seed_dois_script.py` | undercovered-topic seed generation | review |
| `tests/test_metadata_seed_dois_script.py` | broad nutrition seed generation | keep candidate |
| `tests/test_metadata_selection.py` | Semantic Scholar exploration and LLM selection | keep candidate |
| `tests/test_pipeline_conversion_rates_script.py` | old analytics conversion report | stale candidate |
| `tests/test_pipeline_parallel_flow.py` | parallel pipeline runner | keep candidate |
| `tests/test_pre_ingestion_topics.py` | pre-ingestion topics and analytics support | review/stale candidate |
| `tests/test_scripts_contracts.py` | script contracts, PDFs, bibliography, claims | keep candidate, split later |
| `tests/test_single_paper_testing_flow.py` | single-paper test workflow | keep candidate |

## `tests/test_analytics_cli_smoke.py`

Stale analytics CLI coverage.

| Test | What it checks |
|---|---|
| `test_main_help_smoke_lists_analytics_taxonomy` | `analytics/cli.py --help` lists analytics groups. |
| `test_metadata_group_help_smoke` | analytics metadata group exposes `export-csv`. |
| `test_pre_ingestion_help_smoke_lists_subcommands` | analytics pre-ingestion group exposes expected subcommands. |
| `test_pre_ingestion_audit_help_smoke` | analytics pre-ingestion audit help exposes flags. |
| `test_report_conversion_rates_help_smoke` | analytics report command exposes conversion rates. |
| `test_main_routes_pre_ingestion_refresh_inputs` | analytics CLI routes refresh inputs to export scripts. |

## `tests/test_cli_smoke.py`

Current local CLI smoke and routing.

| Test | What it checks |
|---|---|
| `test_main_help_smoke_lists_cli_taxonomy` | root CLI lists pipeline groups and excludes analytics groups. |
| `test_metadata_group_help_smoke` | metadata group exposes `explore`, `from-doi`, `seed-dois`. |
| `test_metadata_explore_help_smoke` | metadata explore exposes modes. |
| `test_metadata_from_doi_help_smoke` | metadata from-doi exposes DOI and overwrite flags. |
| `test_metadata_seed_dois_help_smoke` | seed-dois exposes only mode flags, not old advanced flags. |
| `test_bib_generate_help_smoke_mentions_optional_csv_source` | bib generate documents optional CSV source. |
| `test_pdfs_normalize_help_smoke_mentions_relations_csv` | PDF normalization help mentions relation CSVs. |
| `test_pipeline_help_smoke_lists_subcommands` | pipeline group exposes `run` and `single-paper`. |
| `test_pipeline_single_paper_help_smoke` | single-paper help exposes DOI and testing path. |
| `test_pipeline_run_help_smoke_mentions_runners_flag` | pipeline run exposes `--runners`, hides `--pdf`. |
| `test_claims_extract_help_smoke` | claims extract exposes main flags. |
| `test_bridge_help_smoke_lists_subcommands` | bridge group exposes bridge commands. |
| `test_bridge_ingest_pdf_help_smoke` | bridge ingest help exposes path and DOI. |
| `test_bridge_status_help_smoke` | bridge status help exposes `paper_id`. |
| `test_data_layout_create_help_smoke` | data-layout create help exists. |
| `test_main_prints_help_when_no_command` | parser prints help when no command is provided. |
| `test_main_routes_metadata_explore` | metadata explore dispatches selected mode. |
| `test_main_routes_metadata_seed_dois` | undercovered seed mode dispatches gap seed script. |
| `test_main_routes_bib_generate` | bib generate passes resolved paths to flow. |
| `test_main_routes_claims_extract` | claims extract maps CLI args into claims flow kwargs. |
| `test_main_routes_bridge_status` | bridge status route can be mocked without services. |
| `test_main_routes_pipeline_run_with_runners` | pipeline run passes runner count and PDF path. |

## `tests/test_config_loader.py`

Config, env, and path behavior.

| Test | What it checks |
|---|---|
| `test_resolve_project_path_uses_root_for_relative_paths` | relative paths resolve from repo root. |
| `test_load_env_file_reads_simple_key_values` | `.env` parser reads simple values and quotes. |
| `test_get_env_or_config_prefers_environment` | env values override config values. |
| `test_get_env_or_config_falls_back_to_config` | config value used when env missing. |
| `test_get_pipeline_paths_defaults_claims_output_to_stage_04` | default claims output path is stage 04. |
| `test_get_testing_paths_defaults_to_archive_testing_workspace` | testing defaults live under archive workspace. |
| `test_pre_ingestion_defaults_live_under_corpus_info_workspace` | pre-ingestion defaults live under corpus info. |
| `test_get_data_layout_dirs_includes_runtime_archive_and_pre_ingestion_csv` | data-layout dirs include expected runtime/archive/pre-ingestion paths. |
| `test_get_exploration_seed_doi_file_defaults_to_metadata_rules_seed_file` | seed DOI file default path. |
| `test_get_exploration_completed_seed_doi_file_defaults_to_metadata_rules_completed_seed_file` | completed seed DOI file default path. |
| `test_get_claims_auto_approve_max_tokens_defaults_to_7000` | claims auto-approve threshold default. |
| `test_resolve_available_raw_pdf_dir_prefers_legacy_workspace_when_canonical_is_empty` | legacy raw PDF fallback behavior. |
| `test_create_data_layout_script_uses_canonical_layout` | data layout script creates canonical dirs. |
| `test_artifact_stage_status_detects_completed_pipeline` | artifact status detects completed stage outputs. |

## `tests/test_docling_v2_adapter.py`

Docling adapter and document JSON shape.

| Test | What it checks |
|---|---|
| `test_convert_pdf_for_pipeline_writes_canonical_outputs` | PDF conversion writes expected raw, filtered, final artifacts. |
| `test_export_conversion_outputs_moves_intermediate_files_into_pdf_subdir` | intermediate outputs move into per-PDF subdir. |
| `test_build_logical_document_keeps_table_content_in_section_text` | logical document preserves table content. |
| `test_build_logical_document_renders_docling_table_cells_grid` | Docling tables render as grid text. |
| `test_build_final_document_includes_citation_count_from_metadata` | final document carries citation count. |
| `test_build_final_document_requires_metadata_title` | final document requires metadata title. |
| `test_build_filtered_document_requires_metadata_title` | filtered document requires metadata title. |
| `test_build_final_document_prunes_empty_and_short_leaf_sections` | final document prunes weak leaf sections. |
| `test_build_final_document_keeps_short_parent_when_subsections_have_content` | final document preserves parent sections with useful children. |
| `test_build_filtered_document_prunes_empty_and_short_leaf_sections` | filtered document prunes weak leaf sections. |
| `test_build_filtered_document_keeps_short_parent_when_subsections_have_content` | filtered document preserves parent sections with useful children. |
| `test_build_filtered_document_keeps_short_leaf_section_with_table_content` | filtered document preserves short table sections. |
| `test_build_final_document_keeps_short_leaf_section_with_table_content` | final document preserves short table sections. |

## `tests/test_gap_discarded_audit_script.py`

Gap discard audit.

| Test | What it checks |
|---|---|
| `test_move_gap_rag_discards_for_date_moves_only_gap_rag_files` | moves only gap-rag discarded files for a date. |

## `tests/test_metadata_csv_script.py`

Metadata CSV export, likely analytics-owned.

| Test | What it checks |
|---|---|
| `test_read_metadata_rows_includes_doi_and_sorts_by_citations` | reads metadata rows, includes DOI, sorts by citations. |
| `test_write_csv_exports_metadata_rows_with_doi` | writes metadata CSV with DOI. |

## `tests/test_metadata_from_doi_script.py`

Single DOI metadata creation.

| Test | What it checks |
|---|---|
| `test_build_metadata_payload_matches_canonical_shape` | payload shape for DOI metadata. |
| `test_write_metadata_for_doi_writes_canonical_file` | writes canonical metadata file. |
| `test_write_metadata_for_doi_skips_existing_by_default` | avoids overwrite by default. |
| `test_write_metadata_for_doi_overwrites_when_requested` | overwrites when flag is set. |

## `tests/test_metadata_gap_seed_dois_script.py`

Undercovered-topic seed DOI generation.

| Test | What it checks |
|---|---|
| `test_load_gap_topics_normalizes_terms_and_falls_back_to_name` | gap topics normalize terms and use name fallback. |
| `test_collect_gap_seed_rows_prioritizes_unclassified_and_filters_explored` | seed rows prioritize unclassified topics and exclude explored DOIs. |
| `test_write_doi_output_writes_ranked_gap_seed_file` | writes ranked gap seed DOI file. |

## `tests/test_metadata_seed_dois_script.py`

Broad nutrition seed DOI generation.

| Test | What it checks |
|---|---|
| `test_load_keyword_dictionary_ignores_comments_and_normalizes` | keyword dictionary parsing. |
| `test_find_matching_keywords_supports_prefix_and_phrase_matching` | keyword matching supports prefixes and phrases. |
| `test_collect_candidate_rows_filters_by_keywords_explored_and_citations` | candidate filtering by keyword, explored set, citations. |
| `test_write_doi_output_writes_one_doi_per_line_with_limit` | DOI output respects line format and limit. |

## `tests/test_metadata_selection.py`

Metadata exploration, seed queues, paper save/discard, prompts.

| Test | What it checks |
|---|---|
| `test_build_selection_preview_limits_to_twenty_words` | preview truncates abstracts. |
| `test_citation_exploration_import_does_not_create_directories` | import has no filesystem side effects. |
| `test_paper_to_metadata_record_preserves_canonical_shape` | paper record maps to canonical metadata. |
| `test_load_seed_dois_reads_editable_file_and_ignores_comments` | seed DOI file parsing. |
| `test_load_seed_dois_returns_empty_when_file_exists_but_queue_is_empty` | empty seed file returns empty queue. |
| `test_append_completed_seed_doi_persists_unique_normalized_values` | completed seeds are unique and normalized. |
| `test_append_completed_seed_doi_removes_processed_seed_from_queue` | processed seed removed from queue. |
| `test_sync_seed_doi_queue_removes_all_completed_seeds_from_source_queue` | completed seeds removed in batch. |
| `test_save_paper_merges_seed_parent_and_seed_marker` | saved metadata merges parent and seed markers. |
| `test_save_paper_persists_parent_metadata_when_parent_payload_is_provided` | accepted paper persists parent metadata. |
| `test_save_discarded_persists_parent_metadata_when_parent_payload_is_provided` | discarded paper persists parent metadata. |
| `test_save_discarded_gap_rag_writes_to_dated_bucket_and_state_is_detected` | gap-rag discards use dated buckets and state detection. |
| `test_explore_with_nutrition_rag_skips_seed_not_found` | exploration handles missing seed. |
| `test_explore_with_nutrition_rag_skips_completed_seeds_and_processes_all_batches` | exploration skips completed seeds and processes batches. |
| `test_run_nutrition_rag_exploration_does_not_fail_when_first_pending_seed_is_missing` | first missing seed does not stop run. |
| `test_build_user_prompt_includes_title_and_preview` | prompt includes title and abstract preview. |
| `test_build_responses_payload_uses_gap_prompt_when_requested` | gap mode uses gap prompt. |
| `test_normalize_decisions_defaults_missing_candidates_to_uncertain` | missing LLM decisions become uncertain. |
| `test_run_metadata_exploration_flow_routes_modes` | exploration flow routes public modes. |

## `tests/test_pipeline_conversion_rates_script.py`

Conversion reporting, likely analytics-owned.

| Test | What it checks |
|---|---|
| `test_build_conversion_rows_computes_stage_rates` | computes stage conversion rates. |
| `test_write_csv_exports_conversion_rows` | writes conversion rate CSV. |

## `tests/test_pipeline_parallel_flow.py`

Parallel pipeline execution.

| Test | What it checks |
|---|---|
| `test_run_pipeline_pdf_subprocess_invokes_cli_with_single_pdf` | subprocess runner calls CLI for one PDF. |
| `test_run_pipeline_flow_queues_only_pending_pdfs` | only pending PDFs are queued. |
| `test_run_pipeline_flow_rejects_invalid_runners` | invalid runner counts fail. |

## `tests/test_pre_ingestion_topics.py`

Pre-ingestion topic tooling. Mixed ownership after analytics removal.

| Test | What it checks |
|---|---|
| `test_normalization_and_tokenization_are_deterministic` | title normalization/tokenization stable. |
| `test_topic_mapping_and_unmapped_terms` | topics map terms and track unmapped terms. |
| `test_filter_papers_by_year_excludes_missing_year_when_filtering` | year filter excludes missing years. |
| `test_script_exports_required_artifacts` | pre-ingestion script writes expected outputs. |
| `test_pre_ingestion_topic_audit_defaults_to_csv_workspace` | audit script default paths. |
| `test_bootstrap_candidate_terms_prioritizes_specific_repeated_terms` | candidate term ranking prefers specific repeated terms. |
| `test_bootstrap_topic_config_loads_from_yaml` | bootstrap rules load from YAML. |
| `test_draft_topics_script_writes_ranked_candidate_csv` | draft topics script writes ranked CSV. |
| `test_draft_topics_script_defaults_to_csv_workspace` | draft topics default paths. |
| `test_candidate_term_rows_to_csv_serializes_examples` | candidate term CSV serializes examples. |
| `test_build_draft_topics_yaml_payload_groups_terms_into_topics` | draft YAML groups terms into topics. |
| `test_build_draft_topics_yaml_payload_uses_custom_bootstrap_rules` | custom bootstrap rules affect draft YAML. |
| `test_read_metadata_rows_exports_canonical_pre_ingestion_fields` | metadata rows export pre-ingestion fields. |

## `tests/test_scripts_contracts.py`

Large mixed contract suite. Split candidate.

| Test | What it checks |
|---|---|
| `test_generate_bib_creates_entry_from_metadata_wrapper` | BibTeX generated from metadata wrapper. |
| `test_generate_bib_from_missing_pdf_items_csv_creates_entries` | BibTeX generated from missing PDF CSV. |
| `test_resolve_output_bib_defaults_to_csv_sibling_when_input_csv_is_used` | bib output default follows input CSV. |
| `test_validate_claims_accepts_claims_v2_schema` | claims v2 schema accepted. |
| `test_validate_claims_rejects_old_claims_schema` | old claims schema rejected. |
| `test_sync_raw_pdfs_renames_pdf_from_metadata_match` | raw PDF sync renames matched PDFs. |
| `test_guess_base_name_handles_truncated_author_year_filename` | PDF name guessing handles truncated author-year names. |
| `test_audit_raw_pdf_dir_reports_resolution_buckets` | raw PDF audit reports resolution buckets. |
| `test_sync_raw_pdfs_uses_doi_pdf_relations_as_fallback` | DOI-PDF relations fallback mapping. |
| `test_sync_raw_pdfs_from_relations_uses_relations_as_primary_mapping` | relation mapping can be primary source. |
| `test_sync_raw_pdfs_from_relations_strips_legacy_from_raw_pdf_suffix` | legacy suffix stripping. |
| `test_sync_raw_pdfs_from_relations_copies_unmatched_pdfs_to_separate_dir` | unmatched PDFs copied aside. |
| `test_normalize_pdfs_flow_uses_legacy_raw_pdf_fallback` | normalize flow uses legacy fallback. |
| `test_guess_base_name_prefers_highest_citation_metadata_when_title_is_ambiguous` | ambiguous title picks highest citation metadata. |
| `test_parse_input_sections_reads_json_heuristics_output` | claims parser reads heuristics JSON. |
| `test_parse_input_sections_uses_top_level_final_sections` | claims parser reads top-level final sections. |
| `test_build_claims_preview_uses_top_level_paper_title` | claims preview uses top-level title. |
| `test_parse_input_sections_rejects_markdown_inputs` | markdown inputs rejected. |
| `test_derive_output_file_supports_json_inputs` | claims output file derived from JSON input. |
| `test_build_claims_preview_reports_title_sections_and_tokens` | claims preview reports title, section count, tokens. |
| `test_compute_dynamic_claim_limit_weights_text_more_than_citations` | dynamic claim limit weights text above citations. |
| `test_run_claim_extraction_flow_overwrites_existing_claims` | claims flow overwrites existing output. |
| `test_run_claim_extraction_flow_defers_review_callback_skip_until_final_pass` | review callback skip defers until final pass. |
| `test_run_claim_extraction_flow_processes_deferred_file_on_final_pass` | deferred files process on final pass. |
| `test_run_claim_extraction_flow_auto_approves_under_token_threshold` | auto mode processes files under token threshold. |
| `test_run_claim_extraction_flow_skip_existing_runs_before_preview` | skip-existing avoids preview work. |
| `test_run_claim_extraction_flow_skips_auto_mode_at_or_above_threshold` | auto mode skips files at/above threshold. |
| `test_run_claim_extraction_for_file_inserts_all_sections_into_prompt` | prompt includes all sections. |
| `test_run_claim_extraction_for_file_uses_dynamic_claim_limit` | single-file extraction uses dynamic limit. |
| `test_run_claim_extraction_for_file_respects_fixed_override` | fixed max-claims override wins. |
| `test_build_prompt_renders_full_prompt_from_final_json_sections` | final JSON renders full claims prompt. |
| `test_parse_document_from_pdf_name_supports_doi_first_and_legacy` | PDF document ID parsing supports DOI-first and legacy names. |

## `tests/test_single_paper_testing_flow.py`

Single-paper testing workflow.

| Test | What it checks |
|---|---|
| `test_resolve_pdf_for_doi_prefers_canonical_name` | DOI PDF lookup prefers canonical normalized name. |
| `test_run_single_paper_testing_flow_writes_to_testing_dirs` | single-paper flow writes outputs to testing dirs. |
