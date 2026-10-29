# Demonstration Guide

A 10-minute walkthrough that exercises every major feature. Start the app
(README Quick start; single-process mode at http://127.0.0.1:8000 is easiest).

## 1. Orientation (1 min)

- **Home** shows the product description, the two synthetic sample buildings,
  five sample scenarios, and recent runs.
- Point out the persistent disclaimer (sidebar + banner): educational tool,
  model-based outputs, not safety predictions.

## 2. Baseline evacuation (2 min)

- **Scenario Library → Sample: Baseline evacuation → Run now.**
- The run view polls live status, then shows: 120/120 evacuated, simulated
  time, T90, mean queue time.
- Press **Play** on the recorded frames; step a few frames; enable
  **Congestion heat** and point out where blocked attempts concentrate (the
  hall gaps and the two doors).
- Open **Exit utilization** — with nearest-exit routing the west room drains
  through EA and the east room through EB.

## 3. Perturbation: lose an exit (2 min)

- Run **Sample: West exit blocked**. Everyone must reroute east.
- Compare the metric cards with the baseline in **Compare**: evacuation time
  roughly doubles (≈62 s → ≈102 s on the recorded runs) — the model quantifies
  the cost of losing half the egress capacity.

## 4. Strategy comparison (2 min)

- Run **Sample: Balanced exit assignment**, then go to **Compare**, select all
  three runs, and show the verdict table.
- Talking point: on this symmetric office, balanced routing ≈ baseline — the
  zones already split naturally between the two exits. Strategies matter when
  demand is asymmetric or door capacities differ (next step).

## 5. Experiments: statistics, not anecdotes (2 min)

- **Experiments** → base scenario = baseline, preset = *Strategy comparison*,
  seeds 0,1,2 → Launch. Nine real runs execute in seconds.
- Show the results table: per-seed outcomes vary by ±1–3 s — that spread is
  model randomness, which is why single-run comparisons are not conclusions.
- Download the **CSV** and open it in Excel/LibreOffice for independent
  analysis.

## 6. Build your own (2 min)

- **Buildings & Editor** → paint a wall, place two exits, add a zone, save.
- **Scenario Editor** → pick the new building, set a population, choose a
  strategy, **Save & run**.
- Show the run reproducing: **Reproduce with recorded seed** gives identical
  numbers — that is the reproducibility contract.

## Anticipated questions

- *Is 1.0 persons/second realistic for a door?* It is a configurable,
  deliberately simple rate limit, not a calibrated value (SIMULATION_MODEL).
- *Why did balanced lose to nearest here?* Symmetric layout — see
  RESEARCH_METHODOLOGY §Analysis guidance.
- *Can it do smoke/stairs?* Not in this release; both are listed limitations.
- *What does congestion mean?* Blocked movement attempts per cell — an
  operational bottleneck indicator, not a density or safety threshold.
