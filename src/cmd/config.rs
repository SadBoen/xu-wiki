use std::collections::HashMap;
use std::fs;
use std::path::PathBuf;
use std::sync::LazyLock;
use crate::paths::now_ts;
use crate::response;
use serde_json::Value;

static NAME_REGEX: LazyLock<regex::Regex> = LazyLock::new(|| regex::Regex::new(r"^[A-Za-z0-9_-]{1,64}$").unwrap());

pub struct RegistryEntry {
    pub path: String,
    pub alias: Option<String>,
    pub created_at: u64,
}

pub struct Registry {
    pub wikis: HashMap<String, RegistryEntry>,
    pub mineru_api_key: Option<String>,
}

fn global_dir() -> PathBuf {
    if let Ok(xh) = std::env::var("XU_HOME") {
        PathBuf::from(xh)
    } else if let Some(home) = dirs::home_dir() {
        home.join(".xu-wiki")
    } else {
        PathBuf::from("~/.xu-wiki")
    }
}

pub fn global_config_path() -> PathBuf {
    global_dir().join("config.yaml")
}

fn load_yaml_config(path: &PathBuf) -> Result<serde_yaml::Value, String> {
    let content = fs::read_to_string(path).map_err(|e| e.to_string())?;
    serde_yaml::from_str(&content).map_err(|e| e.to_string())
}

fn save_yaml_config(path: &PathBuf, cfg: &serde_yaml::Mapping) -> Result<(), String> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|e| e.to_string())?;
    }
    let content = serde_yaml::to_string(cfg).map_err(|e| e.to_string())?;
    fs::write(path, content).map_err(|e| e.to_string())
}

fn yaml_to_registry(value: &serde_yaml::Value) -> Registry {
    let mut reg = Registry {
        wikis: HashMap::new(),
        mineru_api_key: None,
    };
    if let Some(obj) = value.as_mapping() {
        if let Some(mineru) = obj.get(&serde_yaml::Value::String("mineru".into())) {
            if let Some(m) = mineru.as_mapping() {
                if let Some(key) = m.get(&serde_yaml::Value::String("api_key".into())) {
                    if let Some(s) = key.as_str() {
                        if !s.is_empty() {
                            reg.mineru_api_key = Some(s.to_string());
                        }
                    }
                }
            }
        }
        if let Some(wikis) = obj.get(&serde_yaml::Value::String("wikis".into())) {
            if let Some(w) = wikis.as_mapping() {
                for (k, v) in w {
                    let name = k.as_str().unwrap_or("").to_string();
                    if let Some(entry) = v.as_mapping() {
                        let path = entry.get(&serde_yaml::Value::String("path".into()))
                            .and_then(|p| p.as_str())
                            .map(|s| s.to_string())
                            .unwrap_or_default();
                        let alias = entry.get(&serde_yaml::Value::String("alias".into()))
                            .and_then(|a| a.as_str())
                            .map(|s| s.to_string());
                        let created_at = entry.get(&serde_yaml::Value::String("created_at".into()))
                            .and_then(|c| c.as_i64())
                            .map(|n| n as u64)
                            .unwrap_or(0);
                        reg.wikis.insert(name, RegistryEntry { path, alias, created_at });
                    }
                }
            }
        }
    }
    reg
}

fn registry_to_yaml(reg: &Registry) -> serde_yaml::Mapping {
    let mut root = serde_yaml::Mapping::new();
    let mut mineru = serde_yaml::Mapping::new();
    if let Some(ref key) = reg.mineru_api_key {
        mineru.insert(serde_yaml::Value::String("api_key".into()), serde_yaml::Value::String(key.clone()));
    }
    root.insert(serde_yaml::Value::String("mineru".into()), serde_yaml::Value::Mapping(mineru));
    let mut wikis = serde_yaml::Mapping::new();
    for (name, entry) in &reg.wikis {
        let mut e = serde_yaml::Mapping::new();
        e.insert(serde_yaml::Value::String("path".into()), serde_yaml::Value::String(entry.path.clone()));
        if let Some(ref a) = entry.alias {
            e.insert(serde_yaml::Value::String("alias".into()), serde_yaml::Value::String(a.clone()));
        }
        e.insert(serde_yaml::Value::String("created_at".into()), serde_yaml::Value::Number(entry.created_at.into()));
        wikis.insert(serde_yaml::Value::String(name.clone()), serde_yaml::Value::Mapping(e));
    }
    root.insert(serde_yaml::Value::String("wikis".into()), serde_yaml::Value::Mapping(wikis));
    root
}

pub fn load_registry() -> Registry {
    let path = global_config_path();
    if path.exists() {
        if let Ok(value) = load_yaml_config(&path) {
            return yaml_to_registry(&value);
        }
    }
    Registry { wikis: HashMap::new(), mineru_api_key: None }
}

pub fn save_registry(reg: &Registry) -> Result<(), String> {
    let path = global_config_path();
    let yaml = registry_to_yaml(reg);
    save_yaml_config(&path, &yaml)
}

pub fn load_global_config() -> HashMap<String, serde_yaml::Value> {
    let path = global_config_path();
    if path.exists() {
        if let Ok(value) = load_yaml_config(&path) {
            if let Some(obj) = value.as_mapping() {
                let mut map = HashMap::new();
                for (k, v) in obj {
                    if let Some(key) = k.as_str() {
                        map.insert(key.to_string(), v.clone());
                    }
                }
                return map;
            }
        }
    }
    HashMap::new()
}

pub fn save_global_config(cfg: &HashMap<String, serde_yaml::Value>) -> Result<(), String> {
    let path = global_config_path();
    let mut yaml_map = serde_yaml::Mapping::new();
    for (k, v) in cfg {
        yaml_map.insert(serde_yaml::Value::String(k.clone()), v.clone());
    }
    save_yaml_config(&path, &yaml_map)
}

pub fn registry_find(name_or_alias: &str) -> Option<(String, RegistryEntry)> {
    let reg = load_registry();
    if let Some(entry) = reg.wikis.get(name_or_alias) {
        return Some((name_or_alias.to_string(), entry.clone()));
    }
    for (name, entry) in &reg.wikis {
        if entry.alias.as_deref() == Some(name_or_alias) {
            return Some((name.clone(), entry.clone()));
        }
    }
    None
}

fn mask_key(k: &str) -> String {
    if k.is_empty() { return String::new(); }
    if k.len() <= 4 { return "***".to_string(); }
    format!("{}...{}", &k[..2], &k[k.len()-2..])
}

// ======== ALIAS ========

pub fn cmd_alias_set(wiki_ref: &str, new_alias: &str) -> Value {
    if new_alias.is_empty() || !NAME_REGEX.is_match(new_alias) {
        return response::error(&format!("invalid alias: {new_alias:?}"), "InvalidName", None, &["name must be alnum/-/_ and <= 64 chars".into()]);
    }

    let (name, entry) = match registry_find(wiki_ref) {
        Some(f) => f,
        None => return response::error(&format!("wiki not found: {wiki_ref}"), "NameNotFound", None, &[]),
    };

    let mut reg = load_registry();

    for (n, e) in &reg.wikis {
        if n == new_alias || e.alias.as_deref() == Some(new_alias) {
            return response::error(
                &format!("alias {new_alias:?} already used by wiki {n}"),
                "AliasConflict",
                Some(response::json!({"attempted_alias": new_alias, "current_wiki": name, "conflicting_wiki": n})),
                &[],
            );
        }
    }

    let previous = entry.alias.clone();
    if let Some(e) = reg.wikis.get_mut(&name) {
        e.alias = Some(new_alias.to_string());
    }
    let _ = save_registry(&reg);

    response::success(
        response::json!({"name": name, "alias": new_alias, "previous_alias": previous}),
        &format!("set alias of {name:?} to {new_alias:?}"),
        &[format!("now reachable as `xu --wiki {new_alias} ...`")],
    )
}

pub fn cmd_alias_unset(wiki_ref: &str) -> Value {
    let (name, entry) = match registry_find(wiki_ref) {
        Some(f) => f,
        None => return response::error(&format!("wiki not found: {wiki_ref}"), "NameNotFound", None, &[]),
    };

    let previous = entry.alias.clone();
    if previous.is_none() {
        return response::warning(response::json!({"name": name}), &format!("wiki {name:?} has no alias to unset"));
    }

    let mut reg = load_registry();
    if let Some(e) = reg.wikis.get_mut(&name) {
        e.alias = None;
    }
    let _ = save_registry(&reg);

    response::success(
        response::json!({"name": name, "previous_alias": previous}),
        &format!("unset alias of {name:?}"),
    )
}

pub fn cmd_alias_show(wiki_ref: &str) -> Value {
    let (name, entry) = match registry_find(wiki_ref) {
        Some(f) => f,
        None => return response::error(&format!("wiki not found: {wiki_ref}"), "NameNotFound", None, &[]),
    };

    response::success(
        response::json!({
            "name": name,
            "alias": entry.alias,
            "path": entry.path,
            "created_at": entry.created_at,
        }),
        &format!("alias of {name:?}: {:?}", entry.alias),
    )
}

// ======== REGISTER / UNREGISTER ========

pub fn cmd_register(name: &str, path: &str, alias: Option<&str>) -> Value {
    if name.is_empty() || !NAME_REGEX.is_match(name) {
        return response::error(&format!("invalid wiki name: {name:?}"), "InvalidName", None, &["name must be alnum/-/_ and <= 64 chars".into()]);
    }

    let target = PathBuf::from(path);
    if !target.exists() || !target.is_dir() {
        return response::error(&format!("path does not exist or is not a dir: {path}"), "PathNotFound", Some(response::json!({"path": path})), &[]);
    }

    let mut reg = load_registry();

    if let Some(existing) = reg.wikis.get(name) {
        let existing_path = PathBuf::from(&existing.path);
        if existing_path == target {
            return response::warning(
                response::json!({"name": name, "path": path}),
                &format!("wiki {name:?} already registered at {path}; reusing (register is idempotent)"),
            );
        }
        return response::error(
            &format!("name {name:?} already registered at {}", existing.path),
            "NameConflict",
            Some(response::json!({"existing_path": existing.path})),
            &[],
        );
    }

    let mut alias_msg = None;
    let bound_alias = if let Some(a) = alias {
        if !NAME_REGEX.is_match(a) {
            return response::error(&format!("invalid alias: {a:?}"), "InvalidName", None, &[]);
        }
        for (n, e) in &reg.wikis {
            if n == a || e.alias.as_deref() == Some(a) {
                alias_msg = Some(format!("alias {a:?} conflicts; registered without alias"));
                None
            } else {
                Some(a.to_string())
            }
        }
    } else {
        None
    };

    let entry = RegistryEntry {
        path: path.to_string(),
        alias: bound_alias,
        created_at: now_ts(),
    };
    reg.wikis.insert(name.to_string(), entry);

    if let Err(e) = save_registry(&reg) {
        return response::error(&format!("failed to save registry: {e}"), "RegistryError", None, &[]);
    }

    let data = response::json!({
        "name": name,
        "path": path,
        "alias": bound_alias,
        "created_at": reg.wikis.get(name).map(|e| e.created_at).unwrap_or(0),
    });

    if let Some(msg) = alias_msg {
        response::warning(data, &format!("registered {name:?} at {path}; {msg}"), &["resolve the conflict and re-run to bind the alias".into()])
    } else {
        response::success(data, &format!("registered {name:?} at {path} (no files written)"), &["wiki files were not touched; only the global registry was updated".into()])
    }
}

pub fn cmd_unregister(name_or_alias: &str) -> Value {
    let reg = load_registry();
    let (name, entry) = match registry_find(name_or_alias) {
        Some(f) => f,
        None => return response::error(&format!("wiki not found: {name_or_alias}"), "NameNotFound", None, &[]),
    };
    drop(reg);

    let mut reg = load_registry();
    let removed_path = reg.wikis.remove(&name).map(|e| e.path).unwrap_or_default();
    let _ = save_registry(&reg);

    response::success(
        response::json!({"name": name, "removed_path": removed_path}),
        &format!("unregistered {name:?}; wiki files at {removed_path:?} were NOT touched"),
        &[
            "to delete wiki data: rm -rf <path>".into(),
            "register again later with `xu register --name ... --path <path>`".into(),
        ],
    )
}

// ======== CONFIG SHOW / PATH ========

pub fn cmd_config_show() -> Value {
    let reg = load_registry();
    let cfg = load_global_config();

    let mineru_key = cfg.get("mineru")
        .and_then(|m| m.as_mapping())
        .and_then(|m| m.get(&serde_yaml::Value::String("api_key".into())))
        .and_then(|k| k.as_str())
        .map(|s| s.to_string());

    response::success(
        response::json!({
            "wikis_count": reg.wikis.len(),
            "mineru": {
                "api_key_set": mineru_key.as_ref().map(|k| !k.is_empty()).unwrap_or(false),
                "api_key_masked": mask_key(mineru_key.as_deref().unwrap_or("")),
            },
            "paths": {
                "global_dir": global_dir().to_string_lossy(),
                "registry": global_config_path().to_string_lossy(),
                "global_config": global_config_path().to_string_lossy(),
            },
        }),
        "global config (secrets masked)",
    )
}

pub fn cmd_config_path() -> Value {
    response::success(
        response::json!({
            "global_dir": global_dir().to_string_lossy(),
            "registry": global_config_path().to_string_lossy(),
            "global_config": global_config_path().to_string_lossy(),
        }),
        "global config locations",
    )
}

pub fn cmd_config_set_mineru_key() -> Value {
    let key = std::env::var("MINERU_API_KEY")
        .map_err(|_| ())
        .ok()
        .filter(|k| !k.is_empty());

    let key = match key {
        Some(k) => k,
        None => return response::error(
            "MINERU_API_KEY env var is empty; set it before running this command",
            "MissingKey",
            Some(response::json!({"hint": "export MINERU_API_KEY=...; xu config set-mineru-key"})),
            &[],
        ),
    };

    let mut reg = load_registry();
    reg.mineru_api_key = Some(key.clone());
    if let Err(e) = save_registry(&reg) {
        return response::error(&format!("failed to save: {e}"), "SaveError", None, &[]);
    }

    response::success(
        response::json!({"masked": mask_key(&key), "scope": "global"}),
        "MinerU API key saved to global config",
        &["test with: xu config show".into(), "rotation: re-run with new MINERU_API_KEY env value".into()],
    )
}
