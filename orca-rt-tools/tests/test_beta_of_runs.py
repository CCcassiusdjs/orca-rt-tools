"""beta of the stored runs (rttools.paper.ablation.beta_of_runs, _earliest)."""
import os

from rttools.paper import ablation, ttflow

EXP = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "experiments")


def test_beta_per_source_task(tmp_path):
    a = ttflow.load_config(os.path.join(EXP, "tt", "config.json"))["apps"]["E"]
    jobs = tmp_path / "tt_jobs.csv"
    # source tasks of E with flows between PEs: A, C, F, H, I; B has no such flow
    jobs.write_text("pe,task,j,t_raw,q,bound,after_tick,slack\n"
                    "0-0,A,1,0,0,1000,587,0\n0-0,A,2,0,1,1000,590,0\n"
                    "0-1,C,1,0,0,2000,1999,0\n0-0,B,1,0,0,1000,1,0\n")
    b = ablation.beta_of_runs(a, {"-": str(jobs)}, "/")
    assert b["per_task"] == {"A": 0.587, "C": 0.999}       # rounded down, the smallest finish of each task
    assert b["beta"] == 0.587 and b["task"] == "A" and "B" not in b["per_task"]


def test_earliest_per_source():
    pk = [{"name": "f1:0", "flow": "f1", "source": "A", "min_start": 1000},
          {"name": "E/f2:0", "flow": "E/f2", "source": "C", "min_start": 5000 + 2000}]
    e = ablation._earliest(pk, 5000, {"A": 0.5, "E/C": 0.25})
    assert e == {"f1:0": 500.0, "E/f2:0": 5000 + 500.0}
    assert ablation._earliest(pk, 5000, 1.0) == {"f1:0": 1000.0, "E/f2:0": 7000.0}
