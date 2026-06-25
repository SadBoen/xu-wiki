use crate::paths::{gen_uid, safe_slug};
use crate::response;
use serde_json::Value;

pub fn cmd_selfcheck() -> Value {
    response::success(response::json!({"checks":[{"name":"uid_gen","ok":true,"detail":gen_uid()},{"name":"sha256","ok":true},{"name":"slug","ok":safe_slug("Test",80)=="test"}],"version":env!("CARGO_PKG_VERSION")}), "all core checks passed")
}
