import { useState } from "react";
import { api } from "../api";
import { Modal } from "./ui";
const example =
  "make,model,category,price,quantity,condition,year,mileage_km,fuel_type,transmission,city\nTata,Nexon,SUV,950000,2,new,2026,0,Petrol,Manual,Pune";
export default function CsvImport({ token, onClose, onImported }) {
  const [csv, setCsv] = useState("");
  const [busy, setBusy] = useState(false);
  const [reading, setReading] = useState(false);
  const [error, setError] = useState("");
  async function readFile(event) {
    const file = event.target.files?.[0];
    if (!file) return;
    if (file.size > 500000) {
      setError("Choose a CSV file no larger than 500 KB.");
      return;
    }
    setReading(true);
    setError("");
    try {
      setCsv(await file.text());
    } catch {
      setError("Unable to read this file. Paste its CSV contents below.");
    } finally {
      setReading(false);
    }
  }
  async function submit(event) {
    event.preventDefault();
    if (busy || reading) return;
    if (!csv.trim()) {
      setError("Choose a file or paste CSV contents.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const result = await api("/vehicles/import", {
        token,
        method: "POST",
        body: { csv },
      });
      onImported(result.imported);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal
      title="Import inventory from CSV"
      onClose={onClose}
      busy={busy || reading}
      wide
    >
      <form onSubmit={submit}>
        <p className="muted">
          All rows are validated together before any vehicles are added to your
          workspace. Prices are INR; used listings must have a quantity of 0 or
          1.
        </p>
        <p className="form-help">
          Required headers: make, model, category, price, quantity. Optional
          columns include condition, year, trim, mileage_km, fuel_type,
          transmission, color, city, description, stock_number, vin and
          info_url. Quote values containing commas.
        </p>
        <label className="field">
          <span>Choose CSV file</span>
          <input
            type="file"
            accept=".csv,text/csv"
            onChange={readFile}
            disabled={busy || reading}
          />
        </label>
        {reading && <p role="status">Reading CSV…</p>}
        <label className="field csv-contents">
          <span>CSV contents</span>
          <textarea
            value={csv}
            onChange={(e) => setCsv(e.target.value)}
            rows={10}
            maxLength={500000}
            spellCheck="false"
            placeholder={example}
            disabled={busy || reading}
          />
        </label>
        <details className="csv-example">
          <summary>Example CSV</summary>
          <pre>{example}</pre>
        </details>
        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}
        <div className="modal-buttons">
          <button
            type="button"
            className="secondary"
            onClick={onClose}
            disabled={busy || reading}
          >
            Cancel
          </button>
          <button className="primary" disabled={busy || reading}>
            {busy ? "Importing…" : "Import vehicles"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
