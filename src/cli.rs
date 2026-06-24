//! CLI entry point using clap.
//! Covers all commands from the original Python CLI.

use clap::{Parser, Subcommand};

use _core::response;

#[derive(Parser)]
#[command(
    name = "xu",
    about = "Relation-driven three-layer wiki engine for AI agents",
    version = env!("CARGO_PKG_VERSION")
)]
pub struct Cli {
    #[command(subcommand)]
    pub command: Commands,
}

#[derive(Subcommand)]
pub enum Commands {
    /// Skill bundle management
    Skills {
        #[command(subcommand)]
        action: SkillsAction,
    },

    /// Create a new empty wiki instance
    Create {
        #[arg(long)]
        name: Option<String>,
        #[arg(long)]
        path: String,
        #[arg(long)]
        alias: Option<String>,
    },

    /// List registered wikis
    Wikis,

    /// Phase 1: parse a file into pending
    IngestFile {
        #[arg(long)]
        wiki: String,
        #[arg(long)]
        file: String,
        #[arg(long, default_value = "")]
        node_path: String,
    },

    /// Phase 2: commit pending pages into L1
    IngestCommit {
        #[arg(long)]
        wiki: String,
        #[arg(long)]
        pending: Option<String>,
        #[arg(long)]
        title: Option<String>,
        #[arg(long, default_value = "article")]
        content_type: String,
        #[arg(long, default_value = "")]
        relations: String,
        #[arg(long, default_value = "")]
        native: String,
        #[arg(long, default_value = "")]
        source: String,
        #[arg(long, default_value = "")]
        #[arg(long, default_value = "agent")]
        author: String,
    },

    /// Album: N images -> 1 L1 Page
    IngestAlbum {
        #[arg(long)]
        wiki: String,
        #[arg(long)]
        title: String,
        #[arg(long)]
        files: String,
        #[arg(long, default_value = "")]
        #[arg(long, default_value = "table")]
        layout: String,
        #[arg(long, default_value = "false")]
        vision: bool,
        #[arg(long, default_value = "")]
        captions: String,
        #[arg(long, default_value = "agent")]
        author: String,
    },

    /// Verify a committed L1 node's integrity
    IngestVerify {
        #[arg(long)]
        wiki: String,
        #[arg(long)]
        uid: String,
    },

    /// Three-layer retrieval
    Query {
        #[arg(long)]
        wiki: String,
        #[arg(long, default_value = "")]
        core: String,
        #[arg(long, default_value = "")]
        expansion: String,
        #[arg(long)]
        top_k: Option<usize>,
        #[arg(long, default_value = "false")]
        neighbors: bool,
        #[arg(long, default_value = "false")]
        include_inactive: bool,
    },

    /// Read a single node full body
    Read {
        #[arg(long)]
        wiki: String,
        #[arg(long)]
        uid: String,
    },

    /// DB node metadata query
    Nodes {
        #[arg(long)]
        wiki: String,
        #[arg(long)]
        layer: Option<String>,
        #[arg(long, default_value = "false")]
        include_inactive: bool,
    },

    /// Manage relations
    QueryRelation {
        #[command(subcommand)]
        action: RelationAction,
    },

    /// L2 Node_List create/show
    List {
        #[command(subcommand)]
        action: ListAction,
    },

    /// L3 Node_Report create/show
    Report {
        #[command(subcommand)]
        action: ReportAction,
    },

    /// Health checks
    Doctor {
        #[arg(long)]
        wiki: String,
        #[arg(long, default_value = "false")]
        fix: bool,
    },

    /// Physically delete a node
    DeleteNode {
        #[arg(long)]
        wiki: String,
        #[arg(long)]
        uid: String,
        #[arg(long, default_value = "false")]
        force: bool,
    },

    /// Rebuild derived layers
    Rebuild {
        #[arg(long)]
        wiki: String,
        #[arg(long, default_value = "keep-l1")]
        granularity: String,
    },

    /// Manage wiki aliases
    Alias {
        #[command(subcommand)]
        action: AliasAction,
    },

    /// Register an existing directory as a wiki
    Register {
        #[arg(long)]
        name: String,
        #[arg(long)]
        path: String,
        #[arg(long)]
        alias: Option<String>,
    },

    /// Remove a wiki from the registry
    Unregister {
        #[arg(long)]
        name: String,
    },

    /// Manage global config
    Config {
        #[command(subcommand)]
        action: ConfigAction,
    },

    /// Uninstall xu-wiki
    Uninstall {
        #[arg(long, default_value = "false")]
        execute: bool,
        #[arg(long, default_value = "false")]
        dry_run: bool,
        #[arg(long, default_value = "false")]
        preserve_config: bool,
        #[arg(long, default_value = "false")]
        purge_wikis: bool,
        #[arg(long, default_value = "false")]
        keep_pip: bool,
        #[arg(long, default_value = "false")]
        keep_skill: bool,
        #[arg(long, action = clap::ArgAction::Append)]
        target: Vec<String>,
    },

    /// Post-install health check
    Selfcheck,

    /// Deploy artefacts
    Deploy {
        #[command(subcommand)]
        action: DeployAction,
    },
}

#[derive(Subcommand)]
pub enum SkillsAction {
    Path,
    List,
}

#[derive(Subcommand)]
pub enum RelationAction {
    Add {
        #[arg(long)]
        wiki: String,
        #[arg(long)]
        from_uid: String,
        #[arg(long)]
        to_uid: String,
        #[arg(long)]
        relation_name: String,
        #[arg(long, default_value = "")]
        comment: String,
    },
    List {
        #[arg(long)]
        wiki: String,
        #[arg(long)]
        from_uid: String,
    },
}

#[derive(Subcommand)]
pub enum ListAction {
    Create {
        #[arg(long)]
        wiki: String,
        #[arg(long)]
        title: String,
        #[arg(long)]
        members: String,
        #[arg(long, default_value = "")]
        dimension: String,
    },
    Show {
        #[arg(long)]
        wiki: String,
        #[arg(long)]
        uid: String,
    },
}

#[derive(Subcommand)]
pub enum ReportAction {
    Create {
        #[arg(long)]
        wiki: String,
        #[arg(long)]
        title: String,
        #[arg(long)]
        body: String,
        #[arg(long)]
        references: String,
    },
    Show {
        #[arg(long)]
        wiki: String,
        #[arg(long)]
        uid: String,
    },
}

#[derive(Subcommand)]
pub enum AliasAction {
    Set {
        #[arg(long)]
        wiki: String,
        #[arg(long)]
        alias: String,
    },
    Unset {
        #[arg(long)]
        wiki: String,
    },
    Show {
        #[arg(long)]
        wiki: String,
    },
}

#[derive(Subcommand)]
pub enum ConfigAction {
    SetMineruKey,
    Show,
    Path,
}

#[derive(Subcommand)]
pub enum DeployAction {
    Skill {
        #[arg(long, action = clap::ArgAction::Append)]
        target: Vec<String>,
        #[arg(long, default_value = "false")]
        copy: bool,
    },
}

pub fn dispatch(cli: Cli) -> i32 {
    match cli.command {
        Commands::Skills { action } => match action {
            SkillsAction::Path => {
                let r = response::success(
                    serde_json::json!({"path": "python/xu/skills"}),
                    "skill bundle source directory",
                );
                response::emit(&r)
            }
            SkillsAction::List => {
                let r = response::success(
                    serde_json::json!({"files": []}),
                    "skill bundle files",
                );
                response::emit(&r)
            }
        },
        Commands::Selfcheck => {
            let r = response::success(
                serde_json::json!({
                    "version": env!("CARGO_PKG_VERSION"),
                    "rust_core": true,
                }),
                "xu-wiki core (Rust) loaded - some commands not yet migrated",
            );
            response::emit(&r)
        },
        _ => {
            let cmd_name = format!("{:?}", std::mem::discriminant(&cli.command));
            let r = response::warning(
                serde_json::json!({"command": cmd_name}),
                "command not yet implemented in Rust; use Python xu CLI fallback",
            );
            response::emit(&r)
        }
    }
}

fn main() {
    let cli = Cli::parse();
    std::process::exit(dispatch(cli));
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_cli_parse_selfcheck() {
        let cli = Cli::try_parse_from(["xu", "selfcheck"]);
        assert!(cli.is_ok());
    }

    #[test]
    fn test_cli_parse_create() {
        let cli = Cli::try_parse_from(["xu", "create", "--name", "test", "--path", "/tmp/wiki"]);
        assert!(cli.is_ok());
    }

    #[test]
    fn test_cli_parse_ingest_album() {
        let cli = Cli::try_parse_from([
            "xu", "ingest-album",
            "--wiki", "mywiki",
            "--title", "photos",
            "--files", "/tmp/a.jpg,/tmp/b.jpg",
        ]);
        assert!(cli.is_ok());
    }

    #[test]
    fn test_cli_parse_query() {
        let cli = Cli::try_parse_from(["xu", "query", "--wiki", "mywiki", "--core", "ml,ai"]);
        assert!(cli.is_ok());
    }

    #[test]
    fn test_cli_parse_deploy_skill() {
        let cli = Cli::try_parse_from(["xu", "deploy", "skill", "--target", "hermes"]);
        assert!(cli.is_ok());
    }

    #[test]
    fn test_cli_version_exits() {
        let cli = Cli::try_parse_from(["xu", "--version"]);
        assert!(cli.is_err()); // version flag causes exit
    }

    #[test]
    fn test_dispatch_selfcheck_returns_0() {
        let cli = Cli::try_parse_from(["xu", "selfcheck"]).unwrap();
        let code = dispatch(cli);
        assert_eq!(code, 0);
    }

    #[test]
    fn test_dispatch_skills_path_returns_0() {
        let cli = Cli::try_parse_from(["xu", "skills", "path"]).unwrap();
        let code = dispatch(cli);
        assert_eq!(code, 0);
    }
}
