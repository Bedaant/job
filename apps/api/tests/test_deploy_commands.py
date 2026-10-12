"""The deploy compose must start the worker and scheduler as MODULES.

Found in the user-zero end-to-end run (2026-10-10): `python workers/run_worker.py` puts
`workers/` itself on sys.path, so `from workers.jobs import ...` fails — verified inside the
built image, where the worker died with "No module named 'workers'" and the scheduler with
"No module named 'digest'". Only the API had been boot-tested, so a deploy would have come
up with nothing processing jobs. README already documents `python -m workers.run_worker`.
"""
from pathlib import Path

import yaml

COMPOSE = Path(__file__).resolve().parents[3] / "docker-compose.deploy.yml"


def _command(service: str) -> list[str]:
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))["services"][service]["command"]


def test_worker_runs_as_a_module():
    assert _command("worker")[:3] == ["python", "-m", "workers.run_worker"]
    assert _command("worker-background")[:3] == ["python", "-m", "workers.run_worker"]


def test_scheduler_runs_as_a_module():
    assert _command("scheduler")[:3] == ["python", "-m", "workers.run_scheduler"]


def test_irreversible_sends_have_their_own_worker():
    assert _command("worker-effects") == ["python", "-m", "workers.run_worker", "effects"]


def test_the_worker_that_plans_forms_builds_an_image_with_the_planner():
    # P0 #8: plan_form_task runs on `background`; its image used to lack node, so every plan failed.
    build = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))["services"]["worker-background"]["build"]
    stages = (COMPOSE.parent / "Dockerfile").read_text(encoding="utf-8").split("\nFROM ")
    planner = next(s for s in stages if s.split("\n")[0].endswith(f"AS {build['target']}"))
    assert "/usr/local/bin/node" in planner and "chromium" in planner and "plan.mjs" in planner
    assert stages[-1].startswith("base AS app")  # the default target stays the slim image
