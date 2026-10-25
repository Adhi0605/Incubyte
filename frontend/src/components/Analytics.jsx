import { useEffect, useState } from "react";
import { api } from "../api";
import { compactMoney, money } from "../VehicleCard";
import { Field } from "./ui";

function Breakdown({ title, rows = [], monetary = false }) {
  const max = Math.max(
    1,
    ...rows.map((row) => Number(monetary ? row.sales : row.units)),
  );
  return (
    <section className="analytics-panel">
      <h2>{title}</h2>
      {rows.length ? (
        <ul className="breakdown-list">
          {rows.map((row) => (
            <li key={row.name}>
              <div className="breakdown-label">
                <span>{row.name}</span>
                <strong>
                  {monetary ? compactMoney(row.sales) : `${row.units} units`}
                </strong>
              </div>
              <div className="breakdown-track" aria-hidden="true">
                <span
                  style={{
                    width: `${(Number(monetary ? row.sales : row.units) / max) * 100}%`,
                  }}
                />
              </div>
              {monetary && (
                <small>
                  {row.units} units · {money(row.sales)}
                </small>
              )}
            </li>
          ))}
        </ul>
      ) : (
        <p className="muted">No recorded sales in this date range.</p>
      )}
    </section>
  );
}
function MonthlyChart({ rows = [] }) {
  const max = Math.max(1, ...rows.map((row) => Number(row.sales)));
  const width = Math.max(600, rows.length * 66),
    height = 220;
  return (
    <section className="analytics-panel monthly-chart">
      <h2>Monthly recorded sales</h2>
      {rows.length ? (
        <>
          <div className="chart-scroll">
            <svg
              viewBox={`0 0 ${width} ${height}`}
              role="img"
              aria-label="Monthly recorded sales in INR"
              style={{ minWidth: Math.min(width, 760) }}
            >
              <title>Monthly recorded sales in INR</title>
              <desc>
                Each bar shows recorded sales for a month. Exact amounts and
                units are listed in the table below.
              </desc>
              <line
                x1="15"
                y1="175"
                x2={width - 15}
                y2="175"
                stroke="#cdd7c0"
              />
              {rows.map((row, i) => {
                const step = (width - 30) / rows.length,
                  bar = (Math.max(0, Number(row.sales)) / max) * 130;
                return (
                  <g key={row.month}>
                    <title>
                      {row.month}: {money(row.sales)}, {row.units} units
                    </title>
                    <rect
                      x={15 + i * step + step * 0.2}
                      y={175 - bar}
                      width={step * 0.6}
                      height={bar}
                      rx="4"
                      fill="#527553"
                    />
                    <text
                      x={15 + (i + 0.5) * step}
                      y="197"
                      textAnchor="middle"
                      fontSize="11"
                      fill="#596e52"
                    >
                      {row.month}
                    </text>
                  </g>
                );
              })}
            </svg>
          </div>
          <details className="chart-data">
            <summary>View monthly sales data</summary>
            <div className="table-scroll">
              <table>
                <caption>Recorded sales by month (INR)</caption>
                <thead>
                  <tr>
                    <th scope="col">Month</th>
                    <th scope="col">Recorded sales</th>
                    <th scope="col">Units sold</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr key={row.month}>
                      <th scope="row">{row.month}</th>
                      <td>{money(row.sales)}</td>
                      <td>{row.units}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
        </>
      ) : (
        <p className="muted">No recorded sales in this date range.</p>
      )}
    </section>
  );
}
function StockInsight({ title, rows = [], aging = false, onDetails }) {
  const [expanded, setExpanded] = useState(false);
  const visibleRows = expanded ? rows : rows.slice(0, 6);
  return (
    <section className="analytics-panel">
      <h2>{title}</h2>
      <p className="form-help">
        {aging
          ? "Listings held longest in your current inventory."
          : "Current listings with limited availability, including sold out cars."}
      </p>
      {rows.length ? (
        <ul className="stock-insights">
          {visibleRows.map((v) => (
            <li key={v.id}>
              <div>
                <button className="text-link" onClick={() => onDetails(v)}>
                  {v.make} {v.model}
                </button>
                <small>
                  {[v.stock_number, v.condition, v.city]
                    .filter(Boolean)
                    .join(" · ")}
                </small>
              </div>
              <span>
                {aging
                  ? `${v.age_days ?? v.days_in_stock ?? 0} days`
                  : `${v.quantity} in stock`}
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="muted">No vehicles to show.</p>
      )}
      {rows.length > 6 && (
        <button
          className="insight-toggle"
          aria-expanded={expanded}
          onClick={() => setExpanded((value) => !value)}
        >
          {expanded
            ? "Show fewer vehicles"
            : `Show all ${rows.length} vehicles`}
        </button>
      )}
    </section>
  );
}
export default function Analytics({ token, onDetails, refreshKey }) {
  const [dates, setDates] = useState({ start_date: "", end_date: "" });
  const [applied, setApplied] = useState({});
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [dateError, setDateError] = useState("");
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");
    const query = new URLSearchParams(
      Object.entries(applied).filter(([, v]) => v),
    );
    api("/analytics" + (query.size ? `?${query}` : ""), {
      token,
      signal: controller.signal,
    })
      .then((value) => {
        if (!controller.signal.aborted) setData(value);
      })
      .catch((e) => {
        if (!controller.signal.aborted) setError(e.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [token, applied, retry, refreshKey]);
  return (
    <section>
      <div className="page-heading">
        <div>
          <p className="eyebrow">THE BIGGER PICTURE</p>
          <h1>
            Workspace analytics<span>.</span>
          </h1>
          <p className="muted">
            Understand recorded activity and the inventory you hold today.
          </p>
        </div>
      </div>
      <form
        className="analytics-dates filter-panel"
        onSubmit={(e) => {
          e.preventDefault();
          if (
            dates.start_date &&
            dates.end_date &&
            dates.start_date > dates.end_date
          ) {
            setDateError("From date must be on or before to date.");
            return;
          }
          setDateError("");
          setApplied({ ...dates });
        }}
      >
        <Field
          label="From date"
          type="date"
          value={dates.start_date}
          max={dates.end_date || undefined}
          onChange={(e) => setDates({ ...dates, start_date: e.target.value })}
        />
        <Field
          label="To date"
          type="date"
          value={dates.end_date}
          min={dates.start_date || undefined}
          onChange={(e) => setDates({ ...dates, end_date: e.target.value })}
        />
        <button className="primary">Apply dates</button>
        <button
          className="secondary"
          type="button"
          onClick={() => {
            setDates({ start_date: "", end_date: "" });
            setApplied({});
            setDateError("");
          }}
        >
          All dates
        </button>
        <p className="form-help">
          Inclusive sales dates. Inventory measures always reflect current
          active stock.
        </p>
        {dateError && (
          <p role="alert" className="error">
            {dateError}
          </p>
        )}
      </form>
      {loading ? (
        <p role="status" className="loading-message">
          Loading analytics…
        </p>
      ) : error ? (
        <p role="alert" className="error">
          {error}{" "}
          <button onClick={() => setRetry((n) => n + 1)}>Try again</button>
        </p>
      ) : (
        data && (
          <>
            <p className="data-notice">
              {data.demo_notice ||
                "Includes synthetic recorded activity. No payments are collected."}
            </p>
            <div
              className="stats-grid analytics-stats"
              aria-label="Analytics summary"
            >
              {[
                ["Recorded sales", data.summary.recorded_sales, true],
                ["Units sold", data.summary.units_sold],
                ["Average sale price", data.summary.average_sale_price, true],
                ["Inventory value", data.summary.inventory_value, true],
                ["Inventory units", data.summary.inventory_units],
                ["Active listings", data.summary.active_listings],
              ].map(([label, value, monetary]) => (
                <div className="stat" key={label}>
                  <div>
                    <p>{label}</p>
                    <strong
                      className={monetary ? "value-number" : ""}
                      title={monetary ? money(value) : undefined}
                    >
                      {monetary
                        ? compactMoney(value)
                        : Number(value).toLocaleString("en-IN")}
                    </strong>
                    {monetary && (
                      <small className="stat-exact">{money(value)}</small>
                    )}
                  </div>
                </div>
              ))}
            </div>
            <MonthlyChart rows={data.monthly_sales} />
            <div className="analytics-grid">
              <Breakdown title="Sales by brand" rows={data.by_brand} monetary />
              <Breakdown
                title="New and used sales"
                rows={data.by_condition}
                monetary
              />
              <Breakdown title="Current stock by fuel" rows={data.by_fuel} />
              <StockInsight
                title="Low stock"
                rows={data.low_stock}
                onDetails={onDetails}
              />
              <StockInsight
                title="Aging stock"
                rows={data.aging_stock}
                aging
                onDetails={onDetails}
              />
            </div>
          </>
        )
      )}
    </section>
  );
}
