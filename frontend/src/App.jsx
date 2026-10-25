import { useCallback, useEffect, useRef, useState } from "react";
import {
  ArrowUpRight,
  Archive,
  CarFront,
  Check,
  BarChart3,
  Upload,
  CircleHelp,
  LayoutGrid,
  LogOut,
  Package,
  Plus,
  ShieldCheck,
  Users,
  X,
} from "lucide-react";
import { api, setUnauthorizedHandler } from "./api";
import { VehicleCard, money, compactMoney } from "./VehicleCard";
import { CarArt } from "./CarArt";
import Auth from "./components/Auth";
import ArchivedVehicles from "./components/ArchivedVehicles";
import { Brand, Field, Modal, Select } from "./components/ui";
import InventoryFilters, { blankFilters } from "./components/InventoryFilters";
import VehicleDetails from "./components/VehicleDetails";
import VehicleForm, { vehicleBody } from "./components/VehicleForm";
import Analytics from "./components/Analytics";
import CsvImport from "./components/CsvImport";

const emptyResult = {
  total: 0,
  page_size: 12,
  summary: { listings: 0, units: 0, value: "0" },
};

export default function App() {
  const [session, setSession] = useState(() => {
    try {
      return JSON.parse(sessionStorage.getItem("forecourt-session"));
    } catch {
      return null;
    }
  });
  const [checking, setChecking] = useState(!!session);
  const [vehicles, setVehicles] = useState([]);
  const [users, setUsers] = useState([]);
  const [page, setPage] = useState(1);
  const [sort, setSort] = useState("newest");
  const [result, setResult] = useState(emptyResult);
  const [analyticsVersion, setAnalyticsVersion] = useState(0);
  const [teamLoading, setTeamLoading] = useState(false);
  const [teamError, setTeamError] = useState("");
  const [detailsId, setDetailsId] = useState(null);
  const [importing, setImporting] = useState(false);
  const [view, setView] = useState("inventory");
  const [filters, setFilters] = useState(blankFilters);
  const [applied, setApplied] = useState(blankFilters);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [modal, setModal] = useState(null);
  const [modalError, setModalError] = useState("");
  const requestId = useRef(0);
  const teamRequestId = useRef(0);
  const currentToken = useRef(null);
  const token = session?.access_token;
  const admin = session?.user?.role === "admin";
  currentToken.current = token;
  const saveSession = useCallback((value) => {
    if (value)
      sessionStorage.setItem("forecourt-session", JSON.stringify(value));
    else {
      sessionStorage.removeItem("forecourt-session");
      requestId.current++;
      teamRequestId.current++;
      setVehicles([]);
      setUsers([]);
      setResult(emptyResult);
      setDetailsId(null);
      setImporting(false);
      setModal(null);
      setNotice("");
      setError("");
      setBusy(false);
    }
    currentToken.current = value?.access_token;
    setSession(value);
  }, []);
  useEffect(() => {
    setUnauthorizedHandler((expiredToken) => {
      if (expiredToken !== currentToken.current) return;
      requestId.current++;
      teamRequestId.current++;
      setDetailsId(null);
      setImporting(false);
      setModal(null);
      saveSession(null);
      setChecking(false);
    });
    return () => setUnauthorizedHandler(() => {});
  }, [saveSession]);
  useEffect(() => {
    if (!token) {
      setChecking(false);
      return;
    }
    let active = true;
    api("/auth/me", { token })
      .then((user) => {
        if (active)
          setSession((previous) => {
            const updated = { ...previous, user };
            sessionStorage.setItem(
              "forecourt-session",
              JSON.stringify(updated),
            );
            return updated;
          });
      })
      .catch((err) => {
        if (active) {
          setError(err.message);
          saveSession(null);
        }
      })
      .finally(() => {
        if (active) setChecking(false);
      });
    return () => {
      active = false;
    };
  }, [token, saveSession]);
  const loadVehicles = useCallback(async () => {
    if (!token || token !== currentToken.current) return;
    const id = ++requestId.current;
    setLoading(true);
    setError("");
    const query = new URLSearchParams(
      Object.entries({ ...applied, page, page_size: 12, sort }).filter(
        ([, value]) => value !== "",
      ),
    );
    try {
      const data = await api("/vehicles/search?" + query, { token });
      if (id === requestId.current && token === currentToken.current) {
        const lastPage = Math.max(1, Math.ceil(data.total / data.page_size));
        if (page > lastPage) {
          setPage(lastPage);
          return;
        }
        setVehicles(data.items);
        setResult(data);
      }
    } catch (err) {
      if (id === requestId.current) setError(err.message);
    } finally {
      if (id === requestId.current) setLoading(false);
    }
  }, [applied, page, sort, token]);
  useEffect(() => {
    if (token && !checking) loadVehicles();
    return () => {
      requestId.current++;
    };
  }, [token, checking, loadVehicles]);
  const loadUsers = useCallback(async () => {
    if (!token || token !== currentToken.current) return;
    const id = ++teamRequestId.current;
    setTeamLoading(true);
    setTeamError("");
    try {
      const data = await api("/users", { token });
      if (id === teamRequestId.current && token === currentToken.current)
        setUsers(data);
    } catch (err) {
      if (id === teamRequestId.current && token === currentToken.current)
        setTeamError(err.message);
    } finally {
      if (id === teamRequestId.current && token === currentToken.current)
        setTeamLoading(false);
    }
  }, [token]);
  useEffect(() => {
    if (view === "team" && admin) loadUsers();
    return () => {
      teamRequestId.current++;
    };
  }, [view, admin, loadUsers]);
  useEffect(() => {
    if (!notice) return;
    const timer = setTimeout(() => setNotice(""), 5000);
    return () => clearTimeout(timer);
  }, [notice]);
  function open(action, vehicle) {
    if (action === "details") {
      setDetailsId(vehicle.id);
      return;
    }
    setDetailsId(null);
    setModalError("");
    setModal({ action, vehicle });
  }
  async function submitAction(event) {
    event.preventDefault();
    if (busy) return;
    setModalError("");
    const { action, vehicle } = modal;
    const data = Object.fromEntries(new FormData(event.currentTarget));
    let path = "/vehicles";
    let method = "POST";
    let body;
    if (action === "add" || action === "edit") {
      try {
        body = vehicleBody(data);
      } catch (err) {
        setModalError(err.message);
        return;
      }
      if (action === "edit") {
        path += "/" + vehicle.id;
        method = "PUT";
      }
    } else if (action === "promote") {
      path = `/users/${vehicle.id}/promote`;
    } else {
      path += "/" + vehicle.id + (action === "delete" ? "" : "/" + action);
      method = action === "delete" ? "DELETE" : "POST";
      if (action === "restock") {
        const quantity = Number(data.quantity);
        if (
          !Number.isInteger(quantity) ||
          quantity < 1 ||
          quantity + vehicle.quantity >
            (vehicle.condition === "used" ? 1 : 1000000)
        ) {
          setModalError(
            vehicle.condition === "used"
              ? "A used listing can contain only one car."
              : "Enter a positive whole quantity within the stock limit.",
          );
          return;
        }
        body = { quantity };
      }
    }
    setBusy(true);
    try {
      await api(path, { token, method, ...(body ? { body } : {}) });
      if (token !== currentToken.current) return;
      setModal(null);
      setAnalyticsVersion((version) => version + 1);
      setNotice(
        {
          add: "Vehicle added to inventory.",
          edit: "Vehicle updated.",
          purchase: "Purchase complete. One vehicle deducted from stock.",
          restock: "Stock replenished.",
          delete: "Vehicle archived. Restore it from Archived vehicles.",
          promote: "Administrator access granted.",
        }[action],
      );
      if (action === "promote") await loadUsers();
      else await loadVehicles();
    } catch (err) {
      if (token !== currentToken.current) return;
      setModalError(err.message);
      if (action === "purchase") await loadVehicles();
    } finally {
      if (token === currentToken.current) setBusy(false);
    }
  }
  if (checking)
    return (
      <div className="page-loading">
        <Brand />
        <p>Checking your session…</p>
      </div>
    );
  if (!session)
    return (
      <Auth
        onSession={(value) => {
          setChecking(true);
          setResult(emptyResult);
          setVehicles([]);
          setUsers([]);
          saveSession(value);
          setView("inventory");
          setFilters(blankFilters);
          setApplied(blankFilters);
          setPage(1);
          setSort("newest");
          setNotice("");
          setError("");
          setBusy(false);
        }}
      />
    );
  const stock = result.summary.units;
  const value = result.summary.value;
  const totalPages = Math.max(1, Math.ceil(result.total / result.page_size));
  const activeFilters = Object.values(applied).some(Boolean);
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <Brand />
        <p className="nav-label">WORKSPACE</p>
        <nav>
          <button
            aria-current={view === "inventory" ? "page" : undefined}
            className={view === "inventory" ? "active" : ""}
            onClick={() => setView("inventory")}
          >
            <LayoutGrid size={18} />
            Inventory<span className="nav-count">{result.total}</span>
          </button>
          {admin && (
            <button
              aria-current={view === "analytics" ? "page" : undefined}
              className={view === "analytics" ? "active" : ""}
              onClick={() => setView("analytics")}
            >
              <BarChart3 size={18} />
              Analytics
            </button>
          )}
          {admin && (
            <button
              aria-current={view === "archive" ? "page" : undefined}
              className={view === "archive" ? "active" : ""}
              onClick={() => setView("archive")}
            >
              <Archive size={18} />
              Archived vehicles
            </button>
          )}
          {admin && (
            <button
              aria-current={view === "team" ? "page" : undefined}
              className={view === "team" ? "active" : ""}
              onClick={() => setView("team")}
            >
              <Users size={18} />
              Team access
            </button>
          )}
        </nav>
        <div className="sidebar-bottom">
          <div className="help-box">
            <CircleHelp size={19} />
            <p>
              Every great journey
              <br />
              starts in the forecourt.
            </p>
          </div>
          <div className="profile">
            <span className="avatar">
              {session.user.email[0].toUpperCase()}
            </span>
            <div>
              <strong>{session.user.email.split("@")[0]}</strong>
              <small>{admin ? "Administrator" : "Member"}</small>
            </div>
            <button
              aria-label="Sign out"
              onClick={() => {
                requestId.current++;
                teamRequestId.current++;
                currentToken.current = null;
                saveSession(null);
                setVehicles([]);
                setUsers([]);
                setModal(null);
                setDetailsId(null);
                setImporting(false);
                setNotice("");
                setBusy(false);
              }}
            >
              <LogOut size={17} />
            </button>
          </div>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div>
            <span className="muted">Workspace</span>
            <span className="crumb">/</span>
            {view === "inventory"
              ? "Vehicle inventory"
              : view === "archive"
                ? "Archived vehicles"
                : view === "analytics"
                  ? "Analytics"
                  : "Team access"}
          </div>
          <span className="role-badge">
            <ShieldCheck size={14} />
            {admin ? "Private admin workspace" : "Private member workspace"}
          </span>
        </header>
        <main className="main-content">
          {view === "inventory" ? (
            <>
              <section className="page-heading">
                <div>
                  <p className="eyebrow">
                    THE RIGHT VEHICLE. THE NEXT POSSIBILITY.
                  </p>
                  <h1>
                    Your forecourt, at a glance<span>.</span>
                  </h1>
                  <p className="muted">
                    Explore the collection and keep your next move in sight.
                  </p>
                </div>
                {admin && (
                  <div className="heading-actions">
                    <button
                      className="secondary"
                      onClick={() => setImporting(true)}
                    >
                      <Upload size={16} />
                      Import CSV
                    </button>
                    <button className="primary" onClick={() => open("add")}>
                      <Plus size={18} />
                      Add vehicle
                    </button>
                  </div>
                )}
              </section>
              <section className="stats-grid" aria-label="Inventory statistics">
                <div className="stat">
                  <span className="stat-icon">
                    <CarFront size={20} />
                  </span>
                  <div>
                    <p>Vehicle listings{activeFilters ? " · filtered" : ""}</p>
                    <strong>
                      {result.summary.listings.toLocaleString("en-IN")}
                    </strong>
                  </div>
                  <span className="stat-note">In the collection</span>
                </div>
                <div className="stat">
                  <span className="stat-icon">
                    <Package size={20} />
                  </span>
                  <div>
                    <p>Units in stock{activeFilters ? " · filtered" : ""}</p>
                    <strong>{Number(stock).toLocaleString("en-IN")}</strong>
                  </div>
                  <span className="stat-note">Ready for the road</span>
                </div>
                <div className="stat">
                  <span className="stat-icon">
                    <ArrowUpRight size={20} />
                  </span>
                  <div>
                    <p>Inventory value{activeFilters ? " · filtered" : ""}</p>
                    <strong className="value-number" title={money(value)}>
                      {compactMoney(value)}
                    </strong>
                  </div>
                  <span className="stat-note">INR · all matching stock</span>
                </div>
              </section>
              <section className="collection-banner">
                <div>
                  <span className="banner-tag">THE FORECOURT COLLECTION</span>
                  <h2>
                    Find your next
                    <br />
                    great drive.
                  </h2>
                  <p>
                    From everyday essentials to new adventures.
                    <br />
                    Your next chapter starts here.
                  </p>
                </div>
                <div className="banner-car">
                  <CarArt category="SUV" color="#b2bdb2" />
                </div>
                <span className="banner-mark">F.</span>
              </section>
              <section className="inventory-section">
                <div className="section-heading">
                  <h2>
                    Vehicle inventory <span>{result.total}</span>
                  </h2>
                  <span className="muted small">Browse. Discover. Drive.</span>
                </div>
                <InventoryFilters
                  filters={filters}
                  setFilters={setFilters}
                  applied={applied}
                  onApply={(value) => {
                    setPage(1);
                    setApplied(value);
                  }}
                />
                <div className="results-line">
                  <span aria-live="polite">
                    {loading
                      ? "Loading collection…"
                      : result.total
                        ? `${(page - 1) * result.page_size + 1}–${Math.min(page * result.page_size, result.total)} of ${result.total} vehicles`
                        : "0 vehicles"}
                  </span>
                  <Select
                    label="Sort inventory"
                    value={sort}
                    onChange={(e) => {
                      setPage(1);
                      setSort(e.target.value);
                    }}
                  >
                    {[
                      ["newest", "Newest first"],
                      ["price_asc", "Price: low to high"],
                      ["price_desc", "Price: high to low"],
                      ["year_desc", "Year: newest first"],
                      ["mileage_asc", "Mileage: low to high"],
                    ].map(([value, text]) => (
                      <option key={value} value={value}>
                        {text}
                      </option>
                    ))}
                  </Select>
                </div>
                {error && (
                  <div role="alert" className="error">
                    {error} <button onClick={loadVehicles}>Try again</button>
                  </div>
                )}
                {loading ? (
                  <div className="vehicle-grid" aria-label="Loading vehicles">
                    {[1, 2, 3].map((n) => (
                      <div key={n} className="skeleton" />
                    ))}
                  </div>
                ) : vehicles.length ? (
                  <div className="vehicle-grid">
                    {vehicles.map((v) => (
                      <VehicleCard
                        key={v.id}
                        vehicle={v}
                        admin={admin}
                        onAction={open}
                        busy={busy}
                      />
                    ))}
                  </div>
                ) : (
                  <div className="empty-state">
                    <CarFront size={38} />
                    <h3>
                      {activeFilters
                        ? "No matches this time."
                        : "A fresh start for your forecourt."}
                    </h3>
                    <p>
                      {activeFilters
                        ? "Try another make, category, or price range."
                        : admin
                          ? "Add your first vehicle to start building your collection."
                          : "Your dealership’s collection will appear here once vehicles are added."}
                    </p>
                    {!activeFilters && admin && (
                      <button className="primary" onClick={() => open("add")}>
                        <Plus size={16} />
                        Add first vehicle
                      </button>
                    )}
                  </div>
                )}
                {result.total > 0 && (
                  <nav className="pagination" aria-label="Inventory pages">
                    <button
                      className="secondary"
                      disabled={loading || page <= 1}
                      onClick={() => setPage((previous) => previous - 1)}
                      aria-label="Previous page"
                    >
                      Previous
                    </button>
                    <span aria-live="polite">
                      Page {page} of {totalPages}
                    </span>
                    <button
                      className="secondary"
                      disabled={loading || page >= totalPages}
                      onClick={() => setPage((previous) => previous + 1)}
                      aria-label="Next page"
                    >
                      Next
                    </button>
                  </nav>
                )}
                <p className="catalog-notice">
                  Synthetic inventory and INR asking prices for portfolio
                  demonstration. Photos are representative; details include
                  image credits.
                </p>
              </section>
            </>
          ) : view === "analytics" && admin ? (
            <Analytics
              token={token}
              refreshKey={analyticsVersion}
              onDetails={(v) => setDetailsId(v.id)}
            />
          ) : view === "archive" && admin ? (
            <ArchivedVehicles token={token} onRestored={loadVehicles} />
          ) : (
            <section>
              <div className="page-heading">
                <div>
                  <p className="eyebrow">PEOPLE BEHIND THE FORECOURT</p>
                  <h1>
                    Team access<span>.</span>
                  </h1>
                  <p className="muted">
                    Manage access within this workspace. Independent
                    registrations create separate private workspaces.
                  </p>
                </div>
              </div>
              {teamError && (
                <p className="error" role="alert">
                  {teamError}
                </p>
              )}
              <div className="team-list">
                {teamLoading ? (
                  <p>Loading team…</p>
                ) : (
                  users.map((user) => (
                    <div key={user.id} className="team-row">
                      <span className="avatar">
                        {user.email[0].toUpperCase()}
                      </span>
                      <div className="team-email">
                        <strong>{user.email}</strong>
                        <small>
                          {user.role === "admin"
                            ? "Full inventory and team access"
                            : "Browse and purchase vehicles"}
                        </small>
                      </div>
                      <span className="role-badge">{user.role}</span>
                      {user.role !== "admin" && (
                        <button
                          className="secondary"
                          onClick={() => open("promote", user)}
                        >
                          Make admin
                        </button>
                      )}
                    </div>
                  ))
                )}
              </div>
            </section>
          )}
          <footer className="page-footer">
            <span>
              FORECOURT <span className="footer-dot">•</span> A little closer to
              your next drive.
            </span>
            <span>
              Built to keep you moving <ArrowUpRight size={13} />
            </span>
          </footer>
        </main>
      </div>
      {notice && (
        <div role="status" className="toast">
          <Check size={18} />
          {notice}
          <button
            aria-label="Dismiss notification"
            onClick={() => setNotice("")}
          >
            <X size={16} />
          </button>
        </div>
      )}
      {detailsId && (
        <VehicleDetails
          key={detailsId}
          vehicleId={detailsId}
          token={token}
          admin={admin}
          onClose={() => setDetailsId(null)}
          onAction={open}
        />
      )}
      {importing && (
        <CsvImport
          token={token}
          onClose={() => setImporting(false)}
          onImported={(count) => {
            if (token !== currentToken.current) return;
            setImporting(false);
            setNotice(
              `${count} vehicle${count === 1 ? "" : "s"} imported successfully.`,
            );
            setAnalyticsVersion((version) => version + 1);
            loadVehicles();
          }}
        />
      )}
      {modal && (
        <Modal
          title={
            {
              add: "Add a vehicle",
              edit: "Edit vehicle",
              restock: "Replenish stock",
              delete: "Archive vehicle?",
              purchase: "Confirm your purchase",
              promote: "Grant administrator access?",
            }[modal.action]
          }
          onClose={() => setModal(null)}
          busy={busy}
          wide={["add", "edit"].includes(modal.action)}
        >
          <form onSubmit={submitAction}>
            {["add", "edit"].includes(modal.action) ? (
              <VehicleForm vehicle={modal.vehicle} />
            ) : modal.action === "restock" ? (
              <>
                <p className="muted">
                  Add units to {modal.vehicle.make} {modal.vehicle.model}.
                  Currently {modal.vehicle.quantity} in stock.
                </p>
                <Field
                  label="Units to add"
                  name="quantity"
                  type="number"
                  min="1"
                  max={
                    modal.vehicle.condition === "used"
                      ? Math.max(0, 1 - modal.vehicle.quantity)
                      : 1000000 - modal.vehicle.quantity
                  }
                  step="1"
                  defaultValue="1"
                  required
                />
              </>
            ) : modal.action === "purchase" ? (
              <div className="confirmation">
                <CarArt category={modal.vehicle.category} />
                <h3>
                  {modal.vehicle.make} {modal.vehicle.model}
                </h3>
                <p className="price">{money(modal.vehicle.price)}</p>
                <p className="muted">
                  Purchase one vehicle. Stock will decrease by one. This records
                  an inventory purchase; no payment is collected.
                </p>
              </div>
            ) : modal.action === "delete" ? (
              <p className="muted">
                Remove {modal.vehicle.make} {modal.vehicle.model} from
                inventory? You can restore it from Archived vehicles with its
                current stock quantity.
              </p>
            ) : (
              <p className="muted">
                Give <strong>{modal.vehicle.email}</strong> permission to manage
                vehicles, restock inventory, and promote other users?
              </p>
            )}
            {modalError && (
              <p className="error" role="alert">
                {modalError}
              </p>
            )}
            <div className="modal-buttons">
              <button
                type="button"
                className="secondary"
                disabled={busy}
                onClick={() => setModal(null)}
              >
                Cancel
              </button>
              <button
                className={
                  modal.action === "delete" ? "primary destructive" : "primary"
                }
                disabled={busy}
              >
                {busy
                  ? "Saving…"
                  : {
                      add: "Add vehicle",
                      edit: "Save changes",
                      restock: "Restock vehicle",
                      purchase: "Confirm purchase",
                      delete: "Archive vehicle",
                      promote: "Grant admin access",
                    }[modal.action]}
              </button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
}
