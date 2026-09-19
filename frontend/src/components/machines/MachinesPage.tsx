import { useState, type FormEvent } from "react";
import type { Machine, MachineCreate } from "../../types";
import { DataState } from "../common/DataState";
import { Icon } from "../common/Icon";
import { MetricValue } from "../common/MetricValue";
import { Panel } from "../common/Panel";
import { SectionHeading } from "../common/SectionHeading";
import { StatusBadge } from "../common/StatusBadge";

interface Props {
  machines: Machine[];
  selectedMachineId: string | null;
  onSelect: (machineId: string) => void;
  onCreate: (input: MachineCreate) => Promise<void>;
  loading?: boolean;
  error?: string | null;
}

const initialForm = {
  machine_name: "",
  machine_type: "",
  manufacturer: "",
  model: "",
  location: "",
  rpm: "",
  rated_power: "",
};

function optionalNumber(value: string) {
  if (!value.trim()) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export function MachinesPage({ machines, selectedMachineId, onSelect, onCreate, loading = false, error = null }: Props) {
  const [form, setForm] = useState(initialForm);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const selected = machines.find((machine) => machine.machine_id === selectedMachineId) ?? machines[0] ?? null;

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!form.machine_name.trim()) {
      setFormError("Machine name is required.");
      return;
    }
    if (form.rpm.trim() && optionalNumber(form.rpm) === null) {
      setFormError("RPM must be a number when provided.");
      return;
    }
    setFormError(null);
    setSubmitting(true);
    try {
      await onCreate({
        machine_name: form.machine_name.trim(),
        machine_type: form.machine_type.trim() || null,
        manufacturer: form.manufacturer.trim() || null,
        model: form.model.trim() || null,
        location: form.location.trim() || null,
        rpm: optionalNumber(form.rpm),
        rated_power: optionalNumber(form.rated_power),
      });
      setForm(initialForm);
    } catch (createError) {
      setFormError(createError instanceof Error ? createError.message : "Machine could not be registered.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="page">
      <SectionHeading
        eyebrow="Asset registry"
        title="Machines"
        description="Select the asset that anchors the command surface. Registry fields are shown exactly as returned by the backend."
        action={<span className="heading-meta">{machines.length} registered asset{machines.length === 1 ? "" : "s"}</span>}
      />

      <div className="registry-layout">
        <Panel tone="paper" className="registry-list-panel">
          <div className="panel-title-row">
            <div>
              <div className="panel-kicker panel-kicker--dark">Fleet registry</div>
              <h3>Available assets</h3>
            </div>
            <span className="panel-count">{machines.length.toString().padStart(2, "0")}</span>
          </div>
          {loading ? <DataState tone="loading" title="Loading machines" description="Reading the asset registry from the API." surface="light" /> : null}
          {!loading && error ? <DataState tone="error" title="Registry unavailable" description={error} surface="light" /> : null}
          {!loading && !error && machines.length === 0 ? (
            <DataState tone="empty" title="No machines registered" description="Use the registration form to add the first monitored asset." surface="light" />
          ) : null}
          <div className="machine-list" role="listbox" aria-label="Registered machines">
            {machines.map((machine) => (
              <button
                type="button"
                role="option"
                aria-selected={machine.machine_id === selected?.machine_id}
                className={"machine-list__row " + (machine.machine_id === selected?.machine_id ? "is-selected" : "")}
                key={machine.machine_id}
                onClick={() => onSelect(machine.machine_id)}
              >
                <span className="machine-list__signal" aria-hidden="true" />
                <span className="machine-list__copy">
                  <strong>{machine.machine_name}</strong>
                  <span>{machine.machine_type ?? "Type not set"} · {machine.location ?? "Location not set"}</span>
                </span>
                <Icon name="arrow" size={15} />
              </button>
            ))}
          </div>
        </Panel>

        <Panel tone="ink" className="machine-detail-panel">
          {selected ? (
            <>
              <div className="panel-kicker"><span>Selected asset</span><span>{selected.machine_id.slice(0, 8)}</span></div>
              <div className="machine-detail-panel__heading">
                <div>
                  <h2>{selected.machine_name}</h2>
                  <p>{selected.machine_type ?? "Machine type not set"}{selected.model ? " · " + selected.model : ""}</p>
                </div>
                <StatusBadge status={selected.baseline_status === "calibrated" ? "connected" : "insufficient"} label={selected.baseline_status === "calibrated" ? "Baseline calibrated" : "Baseline not calibrated"} />
              </div>
              <div className="metric-grid metric-grid--dark">
                <MetricValue label="Manufacturer" value={selected.manufacturer ?? "Not set"} tone="muted" />
                <MetricValue label="Location" value={selected.location ?? "Not set"} tone="muted" />
                <MetricValue label="Nominal speed" value={selected.rpm} unit="RPM" tone="muted" />
                <MetricValue label="Rated power" value={selected.rated_power} unit="kW" tone="muted" />
              </div>
              <div className="machine-detail-panel__foot">
                <span>Registry monitoring flag</span>
                <strong>{selected.monitoring_status || "Not reported"}</strong>
                <span className="machine-detail-panel__note">The live demo session and telemetry freshness are authoritative for active monitoring.</span>
              </div>
            </>
          ) : (
            <DataState tone="empty" title="Select an asset" description="Machine metadata will appear here when the registry has a selection." />
          )}
        </Panel>
      </div>

      <Panel tone="paper" className="registration-panel">
        <div className="panel-title-row">
          <div><div className="panel-kicker panel-kicker--dark">Register asset</div><h3>Add a machine</h3></div>
          <span className="panel-title-row__hint">Only machine name is required by the API.</span>
        </div>
        <form onSubmit={submit} className="machine-form">
          <label><span>Machine name *</span><input value={form.machine_name} onChange={(event) => setForm({ ...form, machine_name: event.target.value })} placeholder="e.g. Pump A" required /></label>
          <label><span>Machine type</span><input value={form.machine_type} onChange={(event) => setForm({ ...form, machine_type: event.target.value })} placeholder="e.g. centrifugal pump" /></label>
          <label><span>Manufacturer</span><input value={form.manufacturer} onChange={(event) => setForm({ ...form, manufacturer: event.target.value })} placeholder="Optional" /></label>
          <label><span>Model</span><input value={form.model} onChange={(event) => setForm({ ...form, model: event.target.value })} placeholder="Optional" /></label>
          <label><span>Location</span><input value={form.location} onChange={(event) => setForm({ ...form, location: event.target.value })} placeholder="Plant / line" /></label>
          <label><span>Nominal RPM</span><input inputMode="decimal" value={form.rpm} onChange={(event) => setForm({ ...form, rpm: event.target.value })} placeholder="Optional" /></label>
          <label><span>Rated power (kW)</span><input inputMode="decimal" value={form.rated_power} onChange={(event) => setForm({ ...form, rated_power: event.target.value })} placeholder="Optional" /></label>
          <div className="machine-form__actions">
            {formError ? <p className="form-error" role="alert">{formError}</p> : null}
            <button type="submit" className="button button-primary" disabled={submitting}>{submitting ? "Registering…" : "Register machine"}<Icon name="arrow" size={15} /></button>
          </div>
        </form>
      </Panel>
    </div>
  );
}
