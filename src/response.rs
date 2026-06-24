//! 4-key JSON response protocol (CONST-ARCH-1).

use serde_json::{json, Value};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Status {
    Success,
    Warning,
    Error,
}

impl Status {
    pub fn as_str(&self) -> &'static str {
        match self {
            Status::Success => "success",
            Status::Warning => "warning",
            Status::Error => "error",
        }
    }
}

pub fn make_response(
    status: Status,
    data: Value,
    message: &str,
    hints: &[String],
) -> Value {
    json!({
        "status": status.as_str(),
        "data": data,
        "message": message,
        "hints": hints,
    })
}

pub fn success(data: Value, message: &str) -> Value {
    make_response(Status::Success, data, message, &[])
}

pub fn success_with_hints(data: Value, message: &str, hints: &[String]) -> Value {
    make_response(Status::Success, data, message, hints)
}

pub fn warning(data: Value, message: &str) -> Value {
    make_response(Status::Warning, data, message, &[])
}

pub fn warning_with_hints(data: Value, message: &str, hints: &[String]) -> Value {
    make_response(Status::Warning, data, message, hints)
}

pub fn error(message: &str, error_class: &str, data: Option<Value>, hints: &[String]) -> Value {
    let mut payload = data.unwrap_or_else(|| json!({}));
    if let Value::Object(ref mut map) = payload {
        map.insert("error_class".to_string(), json!(error_class));
    }
    make_response(Status::Error, payload, message, hints)
}

/// Print response as JSON to stdout, return exit code.
pub fn emit(response: &Value) -> i32 {
    let status = response["status"].as_str().unwrap_or("error");
    println!("{}", serde_json::to_string_pretty(response).unwrap_or_default());
    match status {
        "success" | "warning" => 0,
        _ => 1,
    }
}

pub fn emit_string(response: &Value) -> String {
    serde_json::to_string_pretty(response).unwrap_or_default()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_success_has_4_keys() {
        let r = success(json!({"uid": "X1"}), "created");
        assert_eq!(r["status"], "success");
        assert_eq!(r["data"]["uid"], "X1");
        assert_eq!(r["message"], "created");
        assert!(r["hints"].as_array().is_some());
    }

    #[test]
    fn test_warning_status() {
        let r = warning(json!({"path": "/tmp"}), "already exists");
        assert_eq!(r["status"], "warning");
    }

    #[test]
    fn test_error_includes_class() {
        let r = error("not found", "WikiNotFound", None, &["check name".into()]);
        assert_eq!(r["status"], "error");
        assert_eq!(r["data"]["error_class"], "WikiNotFound");
        assert_eq!(r["hints"][0], "check name");
    }

    #[test]
    fn test_emit_exit_code() {
        let r = success(json!({}), "ok");
        assert_eq!(emit(&r), 0);
        let e = error("fail", "X", None, &[]);
        assert_eq!(emit(&e), 1);
    }

    #[test]
    fn test_emit_string_produces_json() {
        let r = success(json!({"k": 1}), "msg");
        let s = emit_string(&r);
        assert!(s.contains("\"status\""));
        assert!(s.contains("\"success\""));
    }

    #[test]
    fn test_success_with_hints_includes_hints() {
        let r = success_with_hints(json!({}), "done", &["next: query".into()]);
        assert_eq!(r["hints"][0], "next: query");
    }

    #[test]
    fn test_error_with_data_preserves_fields() {
        let mut extra = serde_json::Map::new();
        extra.insert("uid".into(), json!("N1"));
        let r = error("gone", "Gone", Some(Value::Object(extra)), &[]);
        assert_eq!(r["data"]["uid"], "N1");
        assert_eq!(r["data"]["error_class"], "Gone");
    }
}
