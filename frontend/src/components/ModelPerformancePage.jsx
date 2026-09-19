import { useEffect, useState } from 'react'
import { fetchModelPerformance } from '../api'

export default function ModelPerformancePage() {
  const [perf, setPerf] = useState(null)
  const [status, setStatus] = useState('loading')

  useEffect(() => {
    fetchModelPerformance()
      .then((data) => { setPerf(data); setStatus('ready') })
      .catch(() => setStatus('error'))
  }, [])

  if (status === 'loading') return <p className="empty">Loading model performance…</p>
  if (status === 'error') return <p className="empty">Could not reach the backend.</p>

  return (
    <div className="model-perf">
      <h2>Model Performance &amp; Validation</h2>

      <div className={`status-banner status-banner--${perf.status === 'METRICS_AVAILABLE' ? 'ok' : 'warn'}`}>
        {perf.message}
      </div>

      <div className={`status-banner status-banner--${perf.engine_status === 'XGBoost ACTIVE' ? 'ok' : 'warn'}`}>
        {perf.engine_status}
      </div>

      {perf.maturity_label && (
        <div className="status-banner status-banner--warn">⚠ {perf.maturity_label}</div>
      )}

      <div className="fingerprint-grid">
        <div><strong>{perf.model_deployed ? 'Deployed' : 'Not deployed'}</strong><span>ML model status</span></div>
        <div><strong>{perf.model_version || 'None — rule engine only'}</strong><span>model version</span></div>
        <div><strong>{perf.verified_labels_count}</strong><span>analyst-verified labels</span></div>
        <div><strong>{perf.real_observations_total}</strong><span>real observations total</span></div>
      </div>

      {perf.training_metadata_found && (
        <>
          <h3>Dataset</h3>
          <div className="fingerprint-grid">
            <div><strong>{perf.dataset_size}</strong><span>total rows</span></div>
            <div><strong>{perf.train_size}</strong><span>train rows</span></div>
            <div><strong>{perf.test_size}</strong><span>test rows</span></div>
            <div><strong>{perf.split_method}</strong><span>split method</span></div>
          </div>

          <h3>Feature schema (version {perf.feature_schema_version})</h3>
          <p className="detail__disclaimer">Signature: {perf.feature_schema_signature}</p>

          <h3>Class distribution</h3>
          <div className="detail__codes">
            {Object.entries(perf.class_distribution || {}).map(([k, v]) => (
              <span key={k} className="code-chip">{k}: {v}</span>
            ))}
          </div>

          {perf.balanced_accuracy !== undefined && perf.balanced_accuracy !== null && (
            <>
              <h3>Balanced accuracy</h3>
              <p className="detail__disclaimer">{(perf.balanced_accuracy * 100).toFixed(1)}% — this is a model score derived from a small held-out set, not a calibrated production accuracy figure.</p>
            </>
          )}

          {perf.metrics && (
            <>
              <h3>Full metrics (held-out, facility-aware split)</h3>
              <pre className="assessment-box">{JSON.stringify(perf.metrics, null, 2)}</pre>
            </>
          )}

          {perf.confusion_matrix && (
            <>
              <h3>Confusion matrix</h3>
              <pre className="assessment-box">{JSON.stringify(perf.confusion_matrix)}</pre>
            </>
          )}

          <p className="detail__disclaimer">Trained at: {perf.trained_at} · Dataset hash: {perf.dataset_hash} · Label source: {perf.label_source} · Data source: {perf.data_source}</p>
        </>
      )}

      {perf.human_verification_note && (
        <p className="detail__disclaimer">{perf.human_verification_note}</p>
      )}

      <h3>Rule-based baseline (always active fallback)</h3>
      <p className="detail__disclaimer">
        Every classification is available from the transparent rule engine in
        app/services/classifier.py regardless of ML model status — see
        docs/SCORING_METHODOLOGY.md for the exact logic. No SIH judge should
        be told a number here is a "probability" — it is explicitly a model
        score, not a calibrated probability, until validated against enough
        human-verified ground truth.
      </p>
    </div>
  )
}
