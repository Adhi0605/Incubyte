import {
  ArrowUpRight,
  Pencil,
  PackagePlus,
  Trash2,
  RotateCcw,
} from "lucide-react";
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
        <CarArt category={v.category} color={colors[v.id % colors.length]} />
      </div>
      <div className="card-body">
        <div className="make-label">{v.make}</div>
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
