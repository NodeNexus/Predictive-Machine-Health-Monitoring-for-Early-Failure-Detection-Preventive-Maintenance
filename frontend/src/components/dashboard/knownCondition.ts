import type { DemoScenario, MachineVideoEntry } from "../../types";

/**
 * The backend does not expose a structured "known condition" field for a recorded
 * run. The only place a label exists is the human-readable run name, so it is read
 * from there with strict patterns. Anything that does not match returns null and
 * the page shows "No label provided" - a label is never guessed.
 *
 * Backend dependency: expose `known_condition` on DemoScenario / MachineVideoEntry.
 */
export function scenarioKnownCondition(scenario: DemoScenario | undefined): string | null {
  if (!scenario) return null;
  const vibration = /—\s*(Healthy|Degraded)\s*$/i.exec(scenario.label);
  if (scenario.modality === "vibration" && vibration) {
    // The "Degraded" run is the whole run to failure and begins in the healthy state.
    return /degraded/i.test(vibration[1]) ? "Degraded (full run; starts healthy)" : vibration[1];
  }
  const acoustic = /\((Normal|Anomaly)\)\s*$/i.exec(scenario.label);
  if (scenario.modality === "acoustic" && acoustic) return acoustic[1];
  return null;
}

export function videoKnownCondition(video: MachineVideoEntry | undefined): string | null {
  if (!video) return null;
  const oil = /—\s*(With|Without) Oil\s*$/i.exec(video.name);
  return oil ? `${oil[1]} oil` : null;
}

/** Vibration "Healthy"/"Degraded" ranges are derived by a project rule, not original dataset labels. */
export function isDerivedLabel(scenario: DemoScenario | undefined): boolean {
  return scenario?.modality === "vibration" && scenarioKnownCondition(scenario) !== null;
}
