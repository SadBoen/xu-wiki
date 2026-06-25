//! Command implementations — Rust owns all business logic.
//! All functions return 4-key JSON via crate::response.

pub use crate::cmd::cmd_create;
pub use crate::cmd::cmd_selfcheck;
pub use crate::cmd::cmd_doctor;
pub use crate::cmd::cmd_uninstall_plan;
pub use crate::cmd::cmd_uninstall_execute;
pub use crate::cmd::cmd_ingest_commit;
pub use crate::cmd::cmd_ingest_context;
pub use crate::cmd::validate_body_format;
pub use crate::cmd::strip_frontmatter;
pub use crate::cmd::parse_pending_header;
pub use crate::cmd::cmd_query;
pub use crate::cmd::cmd_expand;
pub use crate::cmd::cmd_update;
pub use crate::cmd::cmd_deactivate;
pub use crate::cmd::cmd_verify;
pub use crate::cmd::cmd_list_create;
pub use crate::cmd::cmd_list_extend;
pub use crate::cmd::cmd_entity_create;
pub use crate::cmd::cmd_report_create;
pub use crate::cmd::cmd_nodes;
pub use crate::cmd::cmd_query_relation;
pub use crate::cmd::cmd_list_show;
pub use crate::cmd::cmd_report_show;
pub use crate::cmd::cmd_wikis;
pub use crate::cmd::cmd_delete_node;
pub use crate::cmd::cmd_alias_set;
pub use crate::cmd::cmd_alias_unset;
pub use crate::cmd::cmd_alias_show;
pub use crate::cmd::cmd_register;
pub use crate::cmd::cmd_unregister;
pub use crate::cmd::cmd_config_show;
pub use crate::cmd::cmd_config_path;
pub use crate::cmd::cmd_config_set_mineru_key;
