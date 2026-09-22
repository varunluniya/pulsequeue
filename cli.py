"""
CLI entry point for PulseQueue.

Usage:
    python3 cli.py                     # run the built-in sample scenario
    python3 cli.py --time 60           # re-run the sample scenario at a different clock time
"""

import argparse
import sys

from triage_engine import static_queue, dynamic_queue, find_silent_risers
from simulate import PATIENTS, describe_patient


def main():
    parser = argparse.ArgumentParser(description="PulseQueue: dynamic ED triage re-scoring")
    parser.add_argument(
        "--time", type=float, default=90,
        help="simulation clock time in minutes (default: 90, the sample scenario's design point)",
    )
    parser.add_argument(
        "--watch-size", type=int, default=3,
        help="how many top slots to compare between static and dynamic queues (default: 3)",
    )
    args = parser.parse_args()

    # Real bug caught by actually running this CLI: a --time earlier than
    # some sample patients' arrival minute produced nonsensical negative
    # wait times in the static printout and then an unhandled crash in the
    # dynamic engine. The sample scenario's patients arrive at specific
    # minutes (see simulate.py); --time must be at or after the latest one.
    latest_arrival = max(p.arrival_minute for p in PATIENTS)
    if args.time < latest_arrival:
        print(
            f"Error: --time {args.time} is before the sample scenario's last "
            f"patient arrival (minute {latest_arrival}). Pick a --time >= "
            f"{latest_arrival} so every patient has actually checked in by "
            f"then, or edit PATIENTS in simulate.py for a different scenario.",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"PulseQueue -- ED waiting room at t = {args.time} minutes\n")

    print("Static (acuity-only) queue:")
    for rank, p in enumerate(static_queue(PATIENTS), start=1):
        print(f"  {rank}. {describe_patient(p, args.time)}")

    print("\nDynamic (PulseQueue) queue:")
    for rank, s in enumerate(dynamic_queue(PATIENTS, args.time), start=1):
        flag = "  <-- FLAGGED" if s.flagged else ""
        print(f"  {rank}. {s.patient.patient_id} (risk {s.dynamic_risk:.1f}){flag}")

    risers = find_silent_risers(PATIENTS, args.time, watch_size=args.watch_size)
    print(f"\nSilent risers (missed by the static queue): {len(risers)}")
    for s in risers:
        print(f"  {s.patient.patient_id} -- risk {s.dynamic_risk:.1f}, waited {s.elapsed_minutes:.0f} min")


if __name__ == "__main__":
    main()
