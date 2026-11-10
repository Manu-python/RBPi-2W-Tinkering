"""Optional static plot generator; install matplotlib from requirements first."""
from __future__ import annotations
import argparse, json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from range_lab.storage import TrialRepository
from range_lab.dual_telemetry import load_dual_ndjson

def main() -> None:
    parser=argparse.ArgumentParser(); parser.add_argument("--trial-id",required=True); args=parser.parse_args()
    try: import matplotlib.pyplot as plt
    except ImportError as error: raise SystemExit("Install requirements.txt to enable plots.") from error
    repo=TrialRepository.from_project_root(); trial_directory=repo.attempt_directory(args.trial_id); events=load_dual_ndjson(trial_directory/"events.ndjson")
    pico=[e for e in events if e.get("collector_source")=="pico"]; tx=[e for e in pico if e.get("event")=="packet_tx" and e.get("status")=="sent"]
    replies=[e for e in pico if e.get("event")=="packet_rx" and e.get("status") in {"echo_on_time","echo_late"}]
    deadlines=[e for e in pico if e.get("event")=="packet_deadline"]
    fig,axes=plt.subplots(3,1,sharex=True,figsize=(11,8)); axes[0].plot([e["sequence"] for e in replies],[e["rtt_us"]/1000 for e in replies],".",label="echo RTT"); axes[0].set_ylabel("RTT (ms)"); axes[0].legend()
    axes[1].plot([e["sequence"] for e in tx],[e.get("rssi_dbm") for e in tx],"."); axes[1].set_ylabel("RSSI (dBm)")
    axes[2].plot([e["sequence"] for e in replies],[1]*len(replies),"g.",label="valid echo"); axes[2].plot([e["sequence"] for e in deadlines],[0]*len(deadlines),"rx",label="deadline"); axes[2].set_ylabel("event"); axes[2].set_xlabel("sequence"); axes[2].legend(); fig.tight_layout()
    output=trial_directory/"timeline.png"; fig.savefig(output,dpi=150); print(output)
if __name__ == "__main__": main()
