from flask import Flask, request, jsonify
from langsmith import Client
import requests
import os
import time

app = Flask(__name__)

SLACK_WEBHOOK_URL    = os.environ["SLACK_WEBHOOK_URL"]
LANGSMITH_ORG_ID     = os.environ["LANGSMITH_ORG_ID"]
LANGSMITH_PROJECT_ID = os.environ["LANGSMITH_PROJECT_ID"]

client = Client()

ATTRIBUTE_LABELS = {
    "error_count":    "Error Count",
    "feedback_score": "Feedback Score",
    "latency":        "Latency"
}

ATTRIBUTE_EMOJIS = {
    "error_count":    ":red_circle:",
    "feedback_score": ":star:",
    "latency":        ":hourglass_flowing_sand:"
}


def get_latest_trace_url(project_name: str) -> str:
    time.sleep(2)
    try:
        runs = list(client.list_runs(
            project_name=project_name,
            limit=1,
            order="desc"
        ))
        if runs:
            run_id = runs[0].id
            return (
                f"https://smith.langchain.com/o/{LANGSMITH_ORG_ID}"
                f"/projects/p/{LANGSMITH_PROJECT_ID}/r/{run_id}"
            )
    except Exception as e:
        print(f"Failed to fetch trace URL: {e}")
    return None


@app.route("/webhook", methods=["POST"])
def handle_webhook():
    payload = request.get_json(force=True, silent=True)
    if not payload:
        payload = request.form.to_dict() or {}
    if not payload:
        return jsonify({"error": "empty payload"}), 400

    project_name    = payload.get("project_name", "Unknown Project")
    alert_rule_name = payload.get("alert_rule_name", "Unknown Rule")
    alert_rule_id   = payload.get("alert_rule_id", "")
    attribute       = payload.get("alert_rule_attribute", "")
    metric_value    = payload.get("triggered_metric_value", "N/A")
    threshold       = payload.get("triggered_threshold", "N/A")
    timestamp       = payload.get("timestamp", "N/A")
    alert_type      = payload.get("alert_rule_type", "threshold")

    attribute_label = ATTRIBUTE_LABELS.get(attribute, attribute)
    emoji           = ATTRIBUTE_EMOJIS.get(attribute, ":warning:")

    trace_url  = get_latest_trace_url(project_name)
    trace_text = f"<{trace_url}|View Trace>" if trace_url else "Unavailable"

    project_url = (
        f"https://smith.langchain.com/o/{LANGSMITH_ORG_ID}"
        f"/projects/p/{LANGSMITH_PROJECT_ID}"
    )

    slack_payload = {
