"""create — initialize a new wiki instance (02-create.md).

Builds the three-piece layout (raws/nodes/.xu), DB schema with all three
layers + patches/IDF derived tables, wiki-internal config, and a registry entry.
Builds in a temp dir then atomically renames (CONST-CRT-2).
"""
from __future__ import annotations

import os
import re
import shutil
import tempfile
from pathlib import Path

from ..utils import db
from ..utils.config import (
    load_registry,
    registry_find,
    save_registry,
)
from ..utils.constants import WIKI_FORMAT_VERSION
from ..utils.paths import now_ts
from ..utils.response import error, success, warning
from ..utils.wiki import is_wiki_root

NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


_WIKI_CONFIG_COMMENTED_TEMPLATE = """\
# xu-wiki per-wiki configuration
# ================================
# YAML 不支持内联注释，所有配置项及说明列在下方。
# 修改值即可，不要删除注释（注释是文档）。

# --- 基本信息 ---
version: "1.0.0"           # 格式版本，不要修改
name: "{name}"             # wiki 名称（由 create --name 指定）

# --- 模板定义（预留，暂无内置模板）---
templates: {{}}

# --- 检索切片参数（query CLI） ---
query:
  slice:
    soft_limit: 80         # 软上限：query 返回前先做切片，单次切片 token 数的软上限（超限触发合并）
    hard_limit: 150        # 硬上限：单次切片 token 数的绝对上限（超限直接截断）
    merge_radius: 80       # 相邻切片合并半径（token 距离）

  scoring:
    core_weight: 2000      # core 关键词权重（分母上的常量）
    expansion_weight: 500   # expansion 关键词权重
    density_bonus: 1.5     # 密度奖励系数（>1，高密度切片权重上浮）

  fast_pass:
    enabled: true          # 是否启用 Fast Pass（提前退出优化）
    dynamic: true          # 是否动态调整 k
    k: 3.0                # Fast Pass 阈值系数：TF-IDF 得分第 k 名高于均值 × k 时提前退出
    low_hit: 3            # Fast Pass 低命中下限：低于此阈值时不触发快速退出

  top_k: 10               # query 默认返回条数（--top-k 覆盖）
  timeout_seconds: 10      # query 超时（秒），超时则返回已有结果

# --- 关系管理 ---
relation:
  max_edges: 50            # 每节点最大关系边数（LRU，超出后淘汰尾部）
  policy: lru             # 淘汰策略（目前仅支持 lru）

# --- 资产管理 ---
asset:
  compress_over: 2097152   # 触发压缩的文件大小阈值（字节），默认 2 MiB
  preserve_exif: true      # 是否保留 EXIF 元数据（true = 保留，压缩时也尽量保留）

# --- 摄取参数 ---
ingest:
  page_split_lines: 300    # PDF/DOCX 分页行数阈值（300 行切一刀，不足则余数独立成页）

# --- 重建参数 ---
rebuild:
  granularity:             # rebuild CLI 的 --granularity 选项候选值（不要修改）
    - keep-l1
    - keep-l1-l2
    - full
"""


def _write_wiki_config(path: Path, name: str) -> None:
    content = _WIKI_CONFIG_COMMENTED_TEMPLATE.format(name=name)
    path.write_text(content, encoding="utf-8")


def _build_skeleton(target: Path, name: str) -> None:
    """Create full structure inside `target` (a fresh dir)."""
    (target / "raws").mkdir(parents=True)
    (target / "nodes" / "page").mkdir(parents=True)
    (target / "nodes" / "list").mkdir(parents=True)
    (target / "nodes" / "report").mkdir(parents=True)
    (target / ".xu").mkdir(parents=True)

    # wiki marker (CONST-CRT-1)
    (target / "pyproject.toml").write_text(
        "[tool.xu-wiki]\nmarker = \"xu-wiki-project\"\n"
        f"name = \"{name}\"\n",
        encoding="utf-8",
    )

    # wiki-internal config (CONST-CRT-6) — written with inline comments
    _write_wiki_config(target / ".xu" / "config.yaml", name)

    # state.json
    (target / ".xu" / "state.json").write_text(
        '{"version": "%s", "created_at": %d}\n' % (WIKI_FORMAT_VERSION, now_ts()),
        encoding="utf-8",
    )

    # DB schema with all three layers + patches/IDF (CONST-CRT-6, PRIN-CRT-4/6)
    db.init_schema(target / ".xu" / "wiki.db")


def cmd_create(args) -> dict:
    name = args.name
    if not name:
        return error(
            "create requires --name (BAN-CRT-3)",
            "MissingName",
            hints=["provide an explicit --name; the program never auto-picks a name"],
        )
    if not NAME_RE.match(name):
        return error(
            f"invalid wiki name: {name!r} (CONST-CRT-4)",
            "InvalidName",
            hints=["name must be alnum/-/_ and <= 64 chars"],
        )

    # path normalization + symlink escape guard (CONST-CRT-5: absolute paths only)
    raw_path = Path(args.path).expanduser()
    if not raw_path.is_absolute():
        return error(
            f"--path must be absolute (CONST-CRT-5); got: {args.path!r}",
            "PathNotAbsolute",
            hints=["provide the full absolute path; do not assume CWD"],
        )
    try:
        parent = raw_path.parent.resolve(strict=False)
        target = (parent / raw_path.name).resolve(strict=False)
    except (OSError, RuntimeError) as e:
        return error(f"path resolution failed: {e}", "PathError")

    # name uniqueness in registry (CONST-CRT-4)
    existing = registry_find(name)
    if existing and Path(existing[1]["path"]).resolve() != target:
        return error(
            f"wiki name {name!r} already registered at a different path (CONST-CRT-4)",
            "NameConflict",
            data={"existing_path": existing[1]["path"]},
        )

    # idempotency / already-a-wiki (BAN-CRT-1 exception, CONST-CRT-3)
    if target.exists():
        if is_wiki_root(target):
            _register(name, target, args.alias)
            return warning(
                {"path": str(target), "name": name},
                f"wiki already exists at {target}; reusing (CONST-CRT-3)",
                hints=["use as-is, or rm -rf and re-create to start fresh"],
            )
        if any(target.iterdir()):
            return error(
                f"target dir exists and is non-empty (BAN-CRT-1): {target}",
                "DirNotEmpty",
                hints=["choose an empty dir, or remove existing content yourself"],
            )

    # build in temp dir, then atomic rename (CONST-CRT-2).
    # The target dir is NOT created up-front. We build the entire skeleton
    # inside a sibling temp dir, then `os.replace` it into place as a single
    # atomic rename. On any failure we rmtree the temp dir and the target
    # is never touched (no half-built state).
    tmp_parent = target.parent
    tmp_parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix=".xu-create-", dir=str(tmp_parent)))
    try:
        _build_skeleton(tmp, name)
        os.replace(str(tmp), str(target))   # atomic on the same filesystem
    except Exception as e:  # rollback: leave no half-built artifact
        shutil.rmtree(tmp, ignore_errors=True)
        return error(f"create failed, rolled back: {e}", "CreateFailed")

    alias_warning = _register(name, target, args.alias)

    data = {
        "name": name,
        "path": str(target),
        "version": WIKI_FORMAT_VERSION,
        "layout": ["raws/", "nodes/page/", "nodes/list/", "nodes/report/", ".xu/"],
        "tables": ["nodes", "patches", "idf", "relations", "evidence", "list_members"],
    }
    if alias_warning:
        return warning(data, alias_warning, hints=["alias not bound; pick another"])
    return success(
        data,
        f"created empty wiki '{name}' at {target}",
        hints=["next: xu-wiki ingest-commit to add Node_Page (L1)"],
    )


def _register(name: str, target: Path, alias: str | None) -> str | None:
    """Add/update registry entry. Returns a warning string if alias conflicts."""
    reg = load_registry()
    reg.setdefault("wikis", {})
    alias_msg = None
    bound_alias = alias
    if alias:
        for ename, entry in reg["wikis"].items():
            if ename == alias or entry.get("alias") == alias:
                alias_msg = f"alias {alias!r} conflicts (CONST-CRT-4); wiki created without alias"
                bound_alias = None
                break
    reg["wikis"][name] = {
        "path": str(target),
        "alias": bound_alias,
        "created_at": now_ts(),
    }
    save_registry(reg)
    return alias_msg
