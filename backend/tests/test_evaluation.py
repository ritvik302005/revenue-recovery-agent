"""
The multi-seed evaluation is deterministic, agrees with the batch the
dashboard runs for the same seeds, labels itself as a simulation, and is
served by GET /api/evaluation.
"""
import json

import pytest


def test_evaluation_is_deterministic():
    from evaluate_batch import evaluate
    a, b = evaluate(range(1, 4), 20), evaluate(range(1, 4), 20)
    a.pop("generated_at"), b.pop("generated_at")
    assert a == b


def test_evaluation_matches_the_dashboard_batch_for_the_same_seeds(client):
    from evaluate_batch import evaluate
    seeds = range(1, 4)
    rates = []
    for seed in seeds:
        run = client.post("/api/batch/run", params={"n": 20, "seed": seed, "try_live_orders": False}).json()
        rates.append(100 * sum(r["outcome"] == "recovered" for r in run["results"]) / 20)
    result = evaluate(seeds, 20)
    assert result["recovery_rate_pct"]["mean"] == round(sum(rates) / len(rates), 1)
    assert result["payments_simulated"] == 60


def test_evaluation_labels_itself_and_reports_uncertainty():
    from evaluate_batch import evaluate
    result = evaluate(range(1, 6), 30)
    assert result["kind"] == "simulated_batch_evaluation"
    assert "simulation" in result["note"].lower()
    rate = result["recovery_rate_pct"]
    assert rate["mean_ci95"][0] <= rate["mean"] <= rate["mean_ci95"][1]
    assert rate["min"] <= rate["single_run_range95"][0] <= rate["single_run_range95"][1] <= rate["max"]
    assert abs(sum(result["outcome_share_pct"].values()) - 100) < 0.5


def test_endpoint_serves_the_evaluation_file(client, isolated_state_db, tmp_path, monkeypatch):
    path = tmp_path / "batch_eval.json"
    path.write_text(json.dumps({"kind": "simulated_batch_evaluation", "batch_size": 60}), encoding="utf-8")
    monkeypatch.setattr(isolated_state_db, "EVALUATION_PATH", str(path))
    assert client.get("/api/evaluation").json() == {"kind": "simulated_batch_evaluation", "batch_size": 60}


def test_endpoint_404s_without_an_evaluation(client, isolated_state_db, tmp_path, monkeypatch):
    monkeypatch.setattr(isolated_state_db, "EVALUATION_PATH", str(tmp_path / "missing.json"))
    assert client.get("/api/evaluation").status_code == 404
