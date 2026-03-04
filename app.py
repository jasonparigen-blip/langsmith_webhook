from flask import Flask, request, jsonify
from langsmith import Client
import requests
import os
import time

app = Flask(__name__)

SLACK_WEBHOOK_URL = os.environ["SLACK_WEBHOOK_URL"]
LANGSMITH_ORG_ID = os.environ["LANGSMITH_ORG_ID"]
LANGSMITH_PROJECT_ID = os.environ["LANGSMITH_PROJECT_ID"]

client = Client()

ATTRIBUTE_LABELS = {
    "error_count": "Error Count",
    "feedback_score": "Feedback Score",
    "latency": "Latency"
}

ATTRIBUTE_EMOJIS = {
    "error_count": ":red_circle:",
    "feedback_score": ":star:",
    "latency": ":hourglass_flowing_sand:"
}


def get_latest_trace_url(project_name):
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
                "https://smith.langchain.com/o/"
                + LANGSMITH_ORG_ID
                + "/projects/p/"
                + LANGSMITH_PROJECT_ID
                + "/r/"
                + str(run_id)
            )
    except Exception as e:
        print("Failed to fetch trace URL: " + str(e))
    return None


@app.route("/webhook", methods=["POST"])
def handle_webhook():
    payload = request.get_json(force=True, silent=True)
    if not payload:
        payload = request.form.to_dict() or {}
    if not payload:
        return jsonify({"error": "empty payload"}), 400

    project_name = payload.get("project_name", "Unknown Project")
    alert_rule_name = payload.get("alert_rule_name", "Unknown Rule")
    alert_rule_id = payload.get("alert_rule_id", "")
    attribute = payload.get("alert_rule_attribute", "")
    metric_value = payload.get("triggered_metric_value", "N/A")
    threshold = payload.get("triggered_threshold", "N/A")
    timestamp = payload.get("timestamp", "N/A")
    alert_type = payload.get("alert_rule_type", "threshold")

    attribute_label = ATTRIBUTE_LABELS.get(attribute, attribute)
    emoji = ATTRIBUTE_EMOJIS.get(attribute, ":warning:")

    trace_url = get_latest_trace_url(project_name)
    trace_text = "<" + trace_url + "|View Trace>" if trace_url else "Unavailable"

    project_url = (
        "https://smith.langchain.com/o/"
        + LANGSMITH_ORG_ID
        + "/projects/p/"
        + LANGSMITH_PROJECT_ID
    )

    button_url = trace_url if trace_url else project_url

    slack_payload = {
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": emoji + " LangSmith Alert - " + alert_rule_name,
                    "emoji": True
                }
            },
            {
                "type": "divider"
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": "*Project:*\n" + project_name},
                    {"type": "mrkdwn", "text": "*Alert Rule:*\n" + alert_rule_name},
                    {"type": "mrkdwn", "text": "*Attribute:*\n" + attribute_label},
                    {"type": "mrkdwn", "text": "*Alert Type:*\n" + alert_type},
                    {"type": "mrkdwn", "text": "*Triggered Value:*\n" + str(metric_value)},
                    {"type": "mrkdwn", "text": "*Threshold:*\n" + str(threshold)},
                    {"type": "mrkdwn", "text": "*Timestamp:*\n" + str(timestamp)},
                    {"type": "mrkdwn", "text": "*Trace:*\n" + trace_text}
                ]
            },
            {
                "type": "divider"
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "View Trace",
                            "emoji": True
                        },
                        "url": button_url
                    },
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "View Project",
                            "emoji": True
                        },
                        "url": project_url
                    }
                ]
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": "Alert Rule ID: `" + alert_rule_id + "`"
                    }
                ]
            }
        ]
    }

    resp = requests.post(SLACK_WEBHOOK_URL, json=slack_payload)
    if resp.status_code != 200:
        return jsonify({"error": "slack delivery failed", "detail": resp.text}), 502

    return jsonify({"ok": True}), 200


if __name__ == "__main__":
    app.run(port=5000, debug=True)
