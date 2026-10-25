import {
  ArrowUpRight,
  Pencil,
  PackagePlus,
  Trash2,
  RotateCcw,
} from "lucide-react";
import VehicleImage from "./components/VehicleImage";
export const money = (value) =>
  new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 2,
  }).format(value);
export const compactMoney = (value) => {
  const amount = Number(value);
  if (Math.abs(amount) >= 10000000)
    return `₹${new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2 }).format(amount / 10000000)} crore`;
  if (Math.abs(amount) >= 100000)
    return `₹${new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2 }).format(amount / 100000)} lakh`;
  return money(value);
};
export function VehicleCard({ vehicle, admin, onAction, busy = false }) {
  const v = vehicle;
  const archived = Boolean(v.deleted_at);
  return (
    <article className="vehicle-card">
      <div className="vehicle-image">
        <span className="category-tag">{v.category}</span>
        <span
          className={"stock-dot " + (v.quantity ? "" : "empty")}
          title={
            archived ? "Archived" : v.quantity ? "In stock" : "Out of stock"
          }
        />
        <VehicleImage vehicle={v} />
      </div>
      <div className="card-body">
        <div className="card-meta">
          <div className="make-label">{v.make}</div>
          {v.condition && (
            <span className={`condition-badge ${v.condition}`}>
              {v.condition === "used" ? "Used" : "New"}
            </span>
          )}
        </div>
        <div className="flex items-start justify-between gap-3">
          <h3>{v.model}</h3>
          <span className={"stock-tag " + (v.quantity ? "" : "sold")}>
            {archived
              ? `${v.quantity} units saved`
              : v.quantity
                ? `${v.quantity} in stock`
                : "Sold out"}
          </span>
        </div>
        <p className="vehicle-spec-preview">
          {[v.year, v.fuel_type, v.transmission].filter(Boolean).join(" · ")}
        </p>
        <p className="vehicle-spec-preview">
          {[
            v.city,
            v.condition === "used" &&
              `${Number(v.mileage_km || 0).toLocaleString("en-IN")} km`,
          ]
            .filter(Boolean)
            .join(" · ")}
        </p>
        {!archived && (
          <button
            className="detail-button"
            disabled={busy}
            onClick={() => onAction("details", v)}
          >
            View details <ArrowUpRight size={14} />
          </button>
        )}
        <div className="card-footer">
          <div>
            <span className="price-caption">Asking price</span>
            <p className="price">{money(v.price)}</p>
          </div>
          {!archived && (
            <button
              className="purchase"
              disabled={!v.quantity || busy}
              onClick={() => onAction("purchase", v)}
            >
              {v.quantity ? "Purchase" : "Out of stock"}
              {v.quantity > 0 && <ArrowUpRight size={16} />}
            </button>
          )}
        </div>
        {archived && (
          <p className="muted small archive-date">
            Archived {new Date(v.deleted_at).toLocaleString()}
          </p>
        )}
        {admin && archived && (
          <div className="admin-actions">
            <button disabled={busy} onClick={() => onAction("restore", v)}>
              <RotateCcw size={14} />
              Restore
            </button>
          </div>
        )}
        {admin && !archived && (
          <div className="admin-actions">
            <button disabled={busy} onClick={() => onAction("edit", v)}>
              <Pencil size={14} />
              Edit
            </button>
            <button
              disabled={busy || (v.condition === "used" && v.quantity >= 1)}
              title={
                v.condition === "used" && v.quantity >= 1
                  ? "A used listing can hold only one car"
                  : undefined
              }
              onClick={() => onAction("restock", v)}
            >
              <PackagePlus size={14} />
              Restock
            </button>
            <button
              className="danger-text"
              disabled={busy}
              onClick={() => onAction("delete", v)}
            >
              <Trash2 size={14} />
              Delete
            </button>
          </div>
        )}
      </div>
    </article>
  );
}
