import { useCallback, useEffect, useState } from "react";
import { Archive } from "lucide-react";
import { api } from "../api";
import { VehicleCard } from "../VehicleCard";
import { Modal } from "./ui";

export default function ArchivedVehicles({ token, onRestored }) {
  const [vehicles, setVehicles] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState(null);
  const [busy, setBusy] = useState(false);
  const [restoreError, setRestoreError] = useState("");
  const [notice, setNotice] = useState("");

  const load = useCallback(
    async (signal) => {
      setLoading(true);
      setError("");
      try {
        const data = await api("/vehicles/archived", { token, signal });
        if (!signal?.aborted) setVehicles(data);
      } catch (err) {
        if (!signal?.aborted) setError(err.message);
      } finally {
        if (!signal?.aborted) setLoading(false);
      }
    },
    [token],
  );
  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal);
    return () => controller.abort();
  }, [load]);

  async function restore(event) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setRestoreError("");
    try {
      await api(`/vehicles/${selected.id}/restore`, { token, method: "POST" });
      setVehicles((previous) => previous.filter((v) => v.id !== selected.id));
      setNotice(`${selected.make} ${selected.model} restored to inventory.`);
      setSelected(null);
      await onRestored();
    } catch (err) {
      setRestoreError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section>
      <div className="page-heading">
        <div>
          <p className="eyebrow">READY FOR ANOTHER CHAPTER</p>
          <h1>
            Archived vehicles<span>.</span>
          </h1>
          <p className="muted">
            Restore a vehicle with its original details and stock quantity.
          </p>
        </div>
      </div>
      {notice && (
        <p role="status" className="archive-notice">
          {notice}
        </p>
      )}
      {error && (
        <p role="alert" className="error">
          {error} <button onClick={() => load()}>Try again</button>
        </p>
      )}
      {loading ? (
        <p role="status" className="muted">
          Loading archived vehicles…
        </p>
      ) : vehicles.length ? (
        <div className="vehicle-grid">
          {vehicles.map((vehicle) => (
            <VehicleCard
              key={vehicle.id}
              vehicle={vehicle}
              admin
              busy={busy}
              onAction={(_, v) => {
                setRestoreError("");
                setSelected(v);
              }}
            />
          ))}
        </div>
      ) : (
        !error && (
          <div className="empty-state">
            <Archive size={38} />
            <h3>No archived vehicles.</h3>
            <p>
              Vehicles deleted from inventory will appear here for recovery.
            </p>
          </div>
        )
      )}
      {selected && (
        <Modal
          title="Restore vehicle?"
          busy={busy}
          onClose={() => setSelected(null)}
        >
          <form onSubmit={restore}>
            <p className="muted">
              Restore {selected.make} {selected.model} to inventory with{" "}
              {selected.quantity} units? It will be visible to members of your
              private workspace again.
            </p>
            {restoreError && (
              <p role="alert" className="error">
                {restoreError}
              </p>
            )}
            <div className="modal-buttons">
              <button
                type="button"
                className="secondary"
                disabled={busy}
                onClick={() => setSelected(null)}
              >
                Cancel
              </button>
              <button className="primary" disabled={busy}>
                {busy ? "Restoring…" : "Confirm restore"}
              </button>
            </div>
          </form>
        </Modal>
      )}
    </section>
  );
}
