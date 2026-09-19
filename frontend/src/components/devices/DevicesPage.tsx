import type { DeviceStatus } from "../../types";
import { DataState } from "../common/DataState";
import { Icon } from "../common/Icon";
import { Panel } from "../common/Panel";
import { SectionHeading } from "../common/SectionHeading";
import { StatusBadge } from "../common/StatusBadge";

interface Props {
  devices: DeviceStatus[];
  loading?: boolean;
  error?: string | null;
  onRefresh?: () => void;
}

const labels: Record<string, string> = { thermal_camera: "Thermal camera", vibration_sensor: "Vibration sensor", microphone: "Microphone" };

function readable(value: string) {
  return value.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function DevicesPage({ devices, loading = false, error = null, onRefresh }: Props) {
  return (
    <div className="page">
      <SectionHeading eyebrow="Hardware probes" title="Devices" description="Connectivity is reported by the backend discovery service. Not connected is a real state, not a missing visual." action={<button type="button" className="button button-secondary" onClick={onRefresh} disabled={!onRefresh || loading}><Icon name="radio" size={14} /> Probe again</button>} />
      <Panel tone="paper" className="device-grid-panel">
        <div className="panel-title-row"><div><div className="panel-kicker panel-kicker--dark">Discovery state</div><h3>{devices.length} device record{devices.length === 1 ? "" : "s"}</h3></div><span className="panel-title-row__hint">Hardware probe runs on refresh</span></div>
        {loading ? <DataState tone="loading" title="Probing devices" description="The API is checking available camera and sensor interfaces." surface="light" /> : null}
        {!loading && error ? <DataState tone="error" title="Device discovery unavailable" description={error} surface="light" /> : null}
        {!loading && !error && devices.length === 0 ? <DataState tone="empty" title="No device records" description="The backend did not return a registered hardware probe." surface="light" /> : null}
        <div className="device-grid">
          {devices.map((device) => (
            <article className="device-card" key={device.device_id}>
              <div className="device-card__head"><span className="device-card__icon"><Icon name={device.device_type === "thermal_camera" ? "thermometer" : device.device_type === "microphone" ? "wave" : "activity"} size={18} /></span><StatusBadge status={device.status} /></div>
              <h3>{labels[device.device_type] ?? readable(device.device_type)}</h3>
              <p>{device.connection_type ? readable(device.connection_type) : "Connection type not reported"}{device.machine_id ? " · assigned" : " · unassigned"}</p>
              <div className="device-card__foot"><span>Last seen</span><strong>{device.last_seen ? new Date(device.last_seen).toLocaleString([], { dateStyle: "medium", timeStyle: "short" }) : "Not reported"}</strong></div>
              {device.configuration?.note ? <div className="device-card__note">{String(device.configuration.note)}</div> : null}
            </article>
          ))}
        </div>
      </Panel>
    </div>
  );
}
