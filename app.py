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


def format_latency(seconds):
    if seconds is None:
        return "N/A"
    if seconds >= 60:
        return str(round(seconds / 60, 1)) + " min"
    return str(round(seconds, 2)) + "s"


def get_slowest_trace(project_name):
    time.sleep(2)
    try:
        runs = list(client.list_runs(
            project_name=project_name,
            limit=5,
            order="desc"
        ))
        if not runs:
            return None

        slowest = max(runs, key=lambda r: (r.end_time - r.start_time).total_seconds() if r.end_time and r.start_time else 0)

        run_id = str(slowest.id)
        trace_url = (
            "https://smith.langchain.com/o/"
            + LANGSMITH_ORG_ID
            + "/projects/p/"
            + LANGSMITH_PROJECT_ID
            + "/r/"
            + run_id
        )

        latency = None
        if slowest.end_time and slowest.start_time:
            latency = (slowest.end_time - slowest.start_time).total_seconds()

        error = None
        if slowest.error:
            error = str(slowest.error)[:300]

        input_summary = None
        if slowest.inputs:
            raw = str(slowest.inputs)
            input_summary = raw[:200] + "..." if len(raw) > 200 else raw

        return {
            "trace_url": trace_url,
            "run_id": run_id,
            "latency": latency,
            "error": error,
            "input_summary": input_summary,
            "name": slowest.name or "Unknown"
        }

    except Exception as e:
        print("Failed to fetch trace: " + str(e))
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
    metric_value = payload.get("triggered_metric_value", "N/A")
    threshold = payload.get("triggered_threshold", "N/A")
    timestamp = payload.get("timestamp", "N/A")

    project_url = (
        "https://smith.langchain.com/o/"
        + LANGSMITH_ORG_ID
        + "/projects/p/"
        + LANGSMITH_PROJECT_ID
    )

    trace = get_slowest_trace(project_name)

    if trace:
        trace_url = trace["trace_url"]
        button_url = trace_url
        trace_line = "<" + trace_url + "|View Trace>"
        latency_line = format_latency(trace["latency"])
        run_name = trace["name"]
        error_line = trace["error"] if trace["error"] else "None detected"
        input_line = trace["input_summary"] if trace["input_summary"] else "N/A"
    else:
        button_url = project_url
        trace_line = "Unavailable"
        latency_line = str(metric_value) + "s"
        run_name = "N/A"
        error_line = "N/A"
        input_line = "N/A"

    slack_payload = {
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": ":hourglass_flowing_sand: Latency Alert - " + alert_rule_name,
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
                        {"type": "mrkdwn", "text": "*Project ID:*\n`" + LANGSMITH_PROJECT_ID + "`"},
                        {"type": "mrkdwn", "text": "*Run Name:*\n" + run_name},
                        {"type": "mrkdwn", "text": "*Triggered Latency:*\n" + str(metric_value) + "s"},
                        {"type": "mrkdwn", "text": "*Threshold:*\n" + str(threshold) + "s"},
                        {"type": "mrkdwn", "text": "*Slowest Recent Run:*\n" + latency_line},
                        {"type": "mrkdwn", "text": "*Date:*\n" + str(timestamp).split("T")[0]},
                        {"type": "mrkdwn", "text": "*Time (UTC):*\n" + str(timestamp).split("T")[1].replace("Z", "") if "T" in str(timestamp) else str(timestamp)}
                        ],
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*Error Message:*\n```" + error_line + "```"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*Input:*\n```" + input_line + "```"
                }
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
                            "text": ":mag: View Failing Trace",
                            "emoji": True
                        },
                        "style": "danger",
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
