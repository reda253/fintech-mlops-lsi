from mlflow.tracking import MlflowClient

from ml.tracking_smoke import log_smoke_run


def test_log_smoke_run_creates_a_run(tmp_path):
    uri = f"sqlite:///{tmp_path / 'mlflow.db'}"

    run_id = log_smoke_run(uri, experiment="smoke-test")

    client = MlflowClient(tracking_uri=uri)
    run = client.get_run(run_id)
    assert run.data.params["smoke"] == "true"
    assert run.data.params["source"] == "p3-tracking-script"
    assert run.data.metrics["example_metric"] > 0
    assert run.data.tags["git_commit"] != ""
