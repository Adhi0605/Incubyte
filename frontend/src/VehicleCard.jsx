import { ArrowUpRight, Pencil, PackagePlus, Trash2 } from "lucide-react";
import { CarArt } from "./CarArt";
export const money = (value) =>
  new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  }).format(value);
const colors = ["#a5b9aa", "#c8b99d", "#9caeba", "#b6b5b0"];
export function VehicleCard({ vehicle, admin, onAction, busy = false }) {
  const v = vehicle;
  return (
    <article className="vehicle-card">
      <div className="vehicle-image">
        <span className="category-tag">{v.category}</span>
        <span
          className={"stock-dot " + (v.quantity ? "" : "empty")}
          title={v.quantity ? "In stock" : "Out of stock"}
        />
        <CarArt category={v.category} color={colors[v.id % colors.length]} />
      </div>
      <div className="card-body">
        <div className="make-label">{v.make}</div>
        <div className="flex items-start justify-between gap-3">
          <h3>{v.model}</h3>
          <span className={"stock-tag " + (v.quantity ? "" : "sold")}>
            {v.quantity ? `${v.quantity} in stock` : "Sold out"}
          </span>
        </div>
        <div className="card-footer">
          <div>
            <span className="price-caption">Asking price</span>
            <p className="price">{money(v.price)}</p>
          </div>
          <button
            className="purchase"
            disabled={!v.quantity || busy}
            onClick={() => onAction("purchase", v)}
          >
            {v.quantity ? "Purchase" : "Out of stock"}
            {v.quantity > 0 && <ArrowUpRight size={16} />}
          </button>
        </div>
        {admin && (
          <div className="admin-actions">
            <button disabled={busy} onClick={() => onAction("edit", v)}>
              <Pencil size={14} />
              Edit
            </button>
            <button disabled={busy} onClick={() => onAction("restock", v)}>
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
