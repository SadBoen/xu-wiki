use crate::response;
use serde_json::Value;
use std::path::PathBuf;

pub fn cmd_uninstall_plan(preserve_config: bool, keep_pip: bool) -> Value {
    response::success(response::json!({"mode":"dry-run","pip_uninstall":!keep_pip,"purge_config":!preserve_config,"purge_wikis":false,"note":"wiki data NEVER deleted"}), "dry-run plan")
}

pub fn cmd_uninstall_execute(preserve_config: bool, keep_pip: bool) -> Value {
    let mut actions: Vec<Value> = vec![];
    let mut failed: Vec<String> = vec![];
    let mut hints: Vec<String> = vec![];
    let mut pip_uninstall_attempted = false;

    if !keep_pip {
        pip_uninstall_attempted = true;
        let pipx_ok = std::process::Command::new("pipx")
            .args(["uninstall", "xu-wiki"])
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .status()
            .map(|s| s.success())
            .unwrap_or(false);

        let pip_ok = if pipx_ok {
            true
        } else {
            std::process::Command::new("pip")
                .args(["uninstall", "xu-wiki", "-y"])
                .stdout(std::process::Stdio::null())
                .stderr(std::process::Stdio::null())
                .status()
                .map(|s| s.success())
                .unwrap_or(false)
        };

        let uninstalled = pipx_ok || pip_ok;
        let method = if pipx_ok { "pipx" } else if pip_ok { "pip" } else { "none" };
        actions.push(response::json!({"action":"pip_uninstall","ok":uninstalled,"method":method}));

        if !uninstalled {
            failed.push("pip_uninstall".into());
            hints.push("Auto-removal of xu-wiki package failed. Try manually: pipx uninstall xu-wiki  OR  pip uninstall xu-wiki -y".into());
        }
    }

    if !preserve_config {
        let config_dir = if let Ok(xh) = std::env::var("XU_HOME") {
            PathBuf::from(xh)
        } else if let Ok(home) = std::env::var("HOME") {
            PathBuf::from(home).join(".xu-wiki")
        } else {
            PathBuf::new()
        };

        if !config_dir.as_os_str().is_empty() && config_dir.exists() {
            let removed = std::fs::remove_dir_all(&config_dir).is_ok();
            actions.push(response::json!({"action":"remove_config","ok":removed,"path":config_dir.to_string_lossy()}));
            if !removed {
                failed.push("remove_config".into());
                hints.push(format!("Could not remove config directory: {}. You may remove it manually.", config_dir.display()));
            }
        }
    }

    actions.push(response::json!({"action":"wikis","note":"ALL wiki data preserved","ok":true}));

    let failed_count = failed.len();
    if failed_count == 0 {
        response::success(response::json!({"mode":"execute","actions":actions,"wikis_preserved":true}), "uninstall complete")
    } else if pip_uninstall_attempted && failed.contains(&"pip_uninstall".into()) {
        response::error_with_hints(
            response::json!({"mode":"execute","actions":actions,"failed_components":failed,"wikis_preserved":true}),
            &format!("uninstall failed: xu-wiki package still installed"),
            &hints,
        )
    } else {
        response::warning_with_hints(
            response::json!({"mode":"execute","actions":actions,"failed_components":failed,"wikis_preserved":true}),
            &format!("uninstall completed with {failed_count} issue(s)"),
            &hints,
        )
    }
}
