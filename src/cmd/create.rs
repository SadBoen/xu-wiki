use std::fs;
use std::path::{Path, PathBuf};
use std::sync::LazyLock;
use crate::cmd::config::{global_config_path, load_registry, registry_find, save_registry, RegistryEntry};
use crate::db::Db;
use crate::paths::now_ts;
use crate::response;
use serde_json::Value;
use std::process::id as pid;

static NAME_REGEX: LazyLock<regex::Regex> = LazyLock::new(|| regex::Regex::new(r"^[A-Za-z0-9_-]{1,64}$").unwrap());

const WIKI_CONFIG_TEMPLATE: &str = r#"# xu-wiki per-wiki configuration
# ================================
# YAML 不支持内联注释，所有配置项及说明列在下方。
# 修改值即可，不要删除注释（注释是文档）。

# --- 基本信息 ---
version: "1.0.0"           # 格式版本，不要修改
name: "{name}"             # wiki 名称

# --- 模板定义（预留，暂无内置模板）---
templates: {{}}

# --- 检索切片参数（query CLI） ---
query:
  slice:
    soft_limit: 80         # 软上限：query 返回前先做切片，单次切片 token 数的软上限
    hard_limit: 150        # 硬上限：单次切片 token 数的绝对上限
    merge_radius: 80       # 相邻切片合并半径

  scoring:
    core_weight: 2000      # core 关键词权重
    expansion_weight: 500   # expansion 关键词权重
    density_bonus: 1.5     # 密度奖励系数

  fast_pass:
    enabled: true          # 是否启用 Fast Pass
    dynamic: true          # 是否动态调整 k
    k: 3.0                # Fast Pass 阈值系数
    low_hit: 3            # Fast Pass 低命中下限

  top_k: 10               # query 默认返回条数
  timeout_seconds: 10      # query 超时（秒）

# --- 关系管理 ---
relation:
  max_edges: 50            # 每节点最大关系边数
  policy: lru             # 淘汰策略

# --- 资产管理 ---
asset:
  compress_over: 2097152   # 触发压缩的文件大小阈值（字节）
  preserve_exif: true      # 是否保留 EXIF 元数据

# --- 摄取参数 ---
ingest:
  page_split_lines: 300    # PDF/DOCX 分页行数阈值

# --- 重建参数 ---
rebuild:
  granularity:             # rebuild CLI 的 --granularity 选项候选值
    - keep-l1
    - keep-l1-l2
    - full
"#;

fn write_config_yaml(xu_dir: &Path, name: &str) -> Result<(), String> {
    let content = WIKI_CONFIG_TEMPLATE.replace("{name}", name);
    atomic_write(xu_dir.join("config.yaml"), content)
}

fn build_skeleton(target: &Path, name: &str) -> Result<(), String> {
    fs::create_dir_all(target.join("raws")).map_err(|e| e.to_string())?;
    let xu = target.join(".xu");
    fs::create_dir_all(&xu).map_err(|e| e.to_string())?;
    write_config_yaml(&xu, name)?;
    fs::write(xu.join("state.json"), format!(r#"{{"version":"1.0.0","created_at":{}}}"#, now_ts())).map_err(|e| e.to_string())?;
    Db::open(&xu.join("wiki.db")).map_err(|e| e.to_string())?.init_schema().map_err(|e| e.to_string())?;
    Ok(())
}

fn atomic_write(path: PathBuf, content: String) -> Result<(), String> {
    let tmp = path.with_extension(
        format!("tmp.{}.{}", pid(), uuid_v4())
    );
    fs::write(&tmp, content.as_bytes()).map_err(|e| e.to_string())?;
    fs::rename(&tmp, &path).map_err(|e| e.to_string())
}

fn uuid_v4() -> String {
    use std::time::SystemTime;
    let now = SystemTime::now()
        .duration_since(SystemTime::UNIX_EPOCH)
        .unwrap_or_default()
        .as_nanos();
    format!("{:x}", now)
}

fn resolve_target(path: &str) -> Result<PathBuf, String> {
    let raw = PathBuf::from(path);
    let expanded = if raw.starts_with("~") {
        if let Some(home) = dirs::home_dir() {
            raw.strip_prefix("~")
                .map(|p| home.join(p))
                .unwrap_or(raw)
        } else {
            raw.clone()
        }
    } else {
        raw
    };
    expanded.canonicalize().or_else(|_| Ok(expanded.clone())).map_err(|e| e.to_string())
}

fn is_wiki_root(path: &Path) -> bool {
    path.join(".xu").join("config.yaml").exists()
        && path.join(".xu").join("wiki.db").exists()
}

fn register_wiki(name: &str, path: &str, alias: Option<&str>) -> Result<Option<String>, String> {
    let mut reg = load_registry();
    let wikis = reg.wikis.entry(name.to_string()).or_insert_with(|| RegistryEntry {
        path: String::new(),
        alias: None,
        created_at: 0,
    });

    let existing_path = PathBuf::from(&wikis.path);
    let target_resolved = PathBuf::from(path).canonicalize().unwrap_or_else(|_| PathBuf::from(path));

    if !wikis.path.is_empty() && existing_path != target_resolved {
        return Err(format!("wiki name '{}' already registered at a different path: {}", name, wikis.path));
    }

    let mut alias_warning = None;
    if let Some(a) = alias {
        for (n, e) in reg.wikis.iter() {
            if n == a || e.alias.as_deref() == Some(a) {
                alias_warning = Some(format!("alias '{}' conflicts; wiki created without alias", a));
                break;
            }
        }
        if alias_warning.is_none() {
            wikis.alias = Some(a.to_string());
        }
    }

    wikis.path = path.to_string();
    wikis.created_at = now_ts();
    save_registry(&reg)?;

    Ok(alias_warning)
}

pub fn cmd_create(name: &str, path: &str, alias: Option<&str>) -> Value {
    if name.trim().is_empty() {
        return response::error("create requires --name", "MissingName", None, &["provide an explicit --name".into()]);
    }
    if !NAME_REGEX.is_match(name) {
        return response::error(&format!("invalid wiki name: {name:?}"), "InvalidName", None, &["name must be alnum/-/_ and <= 64 chars".into()]);
    }

    let target = PathBuf::from(path);

    if !target.is_absolute() {
        return response::error("--path must be absolute", "PathNotAbsolute", None, &["provide the full absolute path".into()]);
    }

    let target_resolved = match target.canonicalize() {
        Ok(p) => p,
        Err(_) => target.clone(),
    };

    if target_resolved.exists() {
        if is_wiki_root(&target_resolved) {
            match register_wiki(name, &target_resolved.to_string_lossy(), alias) {
                Ok(alias_warning) => {
                    let mut hints = vec!["use as-is, or rm -rf and re-create to start fresh".into()];
                    if let Some(w) = alias_warning {
                        return response::warning(
                            response::json!({"name": name, "path": target_resolved.to_string_lossy()}),
                            &w,
                            &["alias not bound; pick another".into()],
                        );
                    }
                    return response::success(
                        response::json!({"name": name, "path": target_resolved.to_string_lossy()}),
                        &format!("wiki already exists at {}; reusing", target_resolved.display()),
                    );
                }
                Err(e) => return response::error(&e, "NameConflict", None, &[]),
            }
        }
        if target_resolved.read_dir().map_or(false, |mut d| d.next().is_some()) {
            return response::error(&format!("target dir exists and is non-empty: {}", target_resolved.display()), "DirNotEmpty", None, &["choose an empty dir, or remove existing content yourself".into()]);
        }
    }

    let parent = target.parent();
    if let Err(e) = fs::create_dir_all(parent) {
        return response::error(&format!("cannot create parent dir: {e}"), "PathError", None, &[]);
    }

    let tmp_parent = parent;
    let tmp_name = format!(".xu-create-{}-{}", pid(), uuid_v4());
    let tmp = tmp_parent.join(tmp_name);

    if let Err(e) = fs::create_dir_all(&tmp) {
        return response::error(&format!("cannot create temp dir: {e}"), "TempDirError", None, &[]);
    }

    match build_skeleton(&tmp, name) {
        Ok(()) => {
            if let Err(e) = fs::rename(&tmp, &target) {
                let _ = fs::remove_dir_all(&tmp);
                return response::error(&format!("create failed, rolled back: {e}"), "CreateFailed", None, &[]);
            }

            let target_str = target.canonicalize()
                .map(|p| p.to_string_lossy().to_string())
                .unwrap_or_else(|_| path.to_string());

            let alias_warning = match register_wiki(name, &target_str, alias) {
                Ok(w) => w,
                Err(e) => {
                    return response::warning(
                        response::json!({"name": name, "path": target_str, "version": "1.0.0", "layout": ["raws/", ".xu/"], "tables": ["node_page", "node_derived", "patches", "relations"]}),
                        &format!("created wiki but registry failed: {e}"),
                        &["wiki created but not registered; run: xu register".into()],
                    );
                }
            };

            let mut hints = vec!["next: xu ingest-commit to add Node_Page (L1)".into()];
            if let Some(w) = alias_warning {
                return response::warning(
                    response::json!({"name": name, "path": target_str, "version": "1.0.0", "layout": ["raws/", ".xu/"], "tables": ["node_page", "node_derived", "patches", "relations"]}),
                    &w,
                    &["alias not bound; pick another".into()],
                );
            }
            response::success(
                response::json!({"name": name, "path": target_str, "version": "1.0.0", "layout": ["raws/", ".xu/"], "tables": ["node_page", "node_derived", "patches", "relations"]}),
                &format!("created wiki '{name}' at {target_str}"),
            )
        }
        Err(e) => {
            let _ = fs::remove_dir_all(&tmp);
            response::error(&format!("create failed: {e}"), "CreateFailed", None, &[])
        }
    }
}
