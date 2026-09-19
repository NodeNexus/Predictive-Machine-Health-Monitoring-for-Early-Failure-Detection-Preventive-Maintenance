import type { DatasetInfo } from "../../types";
import { DataState } from "../common/DataState";
import { Panel } from "../common/Panel";
import { SectionHeading } from "../common/SectionHeading";

interface Props {
  datasets: DatasetInfo[];
  loading?: boolean;
  error?: string | null;
  onRefresh?: () => void;
}

function formatNumber(value: number | null) {
  return value === null ? "—" : value.toLocaleString();
}

export function DatasetsPage({ datasets, loading = false, error = null, onRefresh }: Props) {
  return (
    <div className="page">
      <SectionHeading eyebrow="Source registry" title="Datasets" description="The backend registry is populated by the dataset scanner. Paths are provenance strings and may refer to an external asset volume." action={<button type="button" className="button button-secondary" onClick={onRefresh} disabled={!onRefresh || loading}>Refresh registry</button>} />
      <Panel tone="paper" className="dataset-panel">
        <div className="panel-title-row"><div><div className="panel-kicker panel-kicker--dark">Registered sources</div><h3>{datasets.length} dataset record{datasets.length === 1 ? "" : "s"}</h3></div><span className="panel-title-row__hint">No synthetic rows are added</span></div>
        {loading ? <DataState tone="loading" title="Loading registry" description="Reading dataset records from the API." surface="light" /> : null}
        {!loading && error ? <DataState tone="error" title="Dataset registry unavailable" description={error} surface="light" /> : null}
        {!loading && !error && datasets.length === 0 ? <DataState tone="empty" title="No datasets scanned" description="Run scripts/scan_datasets.py on the backend asset volume before expecting records here." surface="light" /> : null}
        <div className="dataset-table" role="table" aria-label="Registered datasets">
          {datasets.map((dataset) => (
            <div className="dataset-row" role="row" key={dataset.dataset_id}>
              <div className="dataset-row__name" role="cell"><strong>{dataset.dataset_name}</strong><span>{dataset.path}</span></div>
              <div className="dataset-row__cell" role="cell"><span>Modality</span><strong>{dataset.modality}</strong></div>
              <div className="dataset-row__cell" role="cell"><span>Samples</span><strong>{formatNumber(dataset.sample_count)}</strong></div>
              <div className="dataset-row__cell" role="cell"><span>Rate</span><strong>{dataset.sample_rate === null ? "—" : dataset.sample_rate + " Hz"}</strong></div>
              <div className="dataset-row__cell" role="cell"><span>Labels</span><strong>{dataset.normal_count === null && dataset.anomaly_count === null ? "—" : (dataset.normal_count ?? "—") + "N / " + (dataset.anomaly_count ?? "—") + "A"}</strong></div>
              {dataset.notes ? <p className="dataset-row__note">{dataset.notes}</p> : null}
            </div>
          ))}
        </div>
      </Panel>
    </div>
  );
}
