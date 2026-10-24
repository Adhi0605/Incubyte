import { useCallback, useEffect, useRef, useState } from "react";
import {
  ArrowUpRight,
  CarFront,
  Check,
  ChevronDown,
  CircleHelp,
  LayoutGrid,
  LogOut,
  Package,
  Plus,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  Users,
  X,
} from "lucide-react";
import { api, setUnauthorizedHandler } from "./api";
import { VehicleCard, money } from "./VehicleCard";
import { CarArt } from "./CarArt";
import Auth from "./components/Auth";
import { Brand, Field, Modal } from "./components/ui";

const blankFilters = {
  make: "",
  model: "",
  category: "",
  min_price: "",
  max_price: "",
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
  const token = session?.access_token;
  const admin = session?.user?.role === "admin";
  const saveSession = useCallback((value) => {
    if (value)
      sessionStorage.setItem("forecourt-session", JSON.stringify(value));
    else sessionStorage.removeItem("forecourt-session");
    setSession(value);
  }, []);
  useEffect(() => {
    setUnauthorizedHandler(() => {
      saveSession(null);
      setChecking(false);
    });
  }, [saveSession]);
  useEffect(() => {
    if (!token) {
      setChecking(false);
      return;
    }
    let active = true;
    api("/auth/me", { token })
      .then((user) => {
        if (active) setSession((previous) => ({ ...previous, user }));
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
    const id = ++requestId.current;
    setLoading(true);
    setError("");
    const query = new URLSearchParams(
      Object.entries(applied).filter(([, value]) => value !== ""),
    );
    try {
      const data = await api("/vehicles/search?" + query, { token });
      if (id === requestId.current) setVehicles(data);
    } catch (err) {
      if (id === requestId.current) setError(err.message);
    } finally {
      if (id === requestId.current) setLoading(false);
    }
  }, [applied, token]);
  useEffect(() => {
    if (token && !checking) loadVehicles();
  }, [token, checking, loadVehicles]);
  const loadUsers = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setUsers(await api("/users", { token }));
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [token]);
  useEffect(() => {
    if (view === "team" && admin) loadUsers();
  }, [view, admin, loadUsers]);
  useEffect(() => {
    if (!notice) return;
    const timer = setTimeout(() => setNotice(""), 5000);
    return () => clearTimeout(timer);
  }, [notice]);
  function open(action, vehicle) {
    setModalError("");
    setModal({ action, vehicle });
  }
  async function submitAction(event) {
    event.preventDefault();
    setBusy(true);
    setModalError("");
    const { action, vehicle } = modal;
    const data = Object.fromEntries(new FormData(event.currentTarget));
    let path = "/vehicles";
    let method = "POST";
    let body;
    if (action === "add" || action === "edit") {
      body = { ...data, quantity: Number(data.quantity) };
      if (action === "edit") {
        path += "/" + vehicle.id;
        method = "PUT";
      }
    } else if (action === "promote") {
      path = `/users/${vehicle.id}/promote`;
    } else {
      path += "/" + vehicle.id + (action === "delete" ? "" : "/" + action);
      method = action === "delete" ? "DELETE" : "POST";
      if (action === "restock") body = { quantity: Number(data.quantity) };
    }
    try {
      await api(path, { token, method, ...(body ? { body } : {}) });
      setModal(null);
      setNotice(
        {
          add: "Vehicle added to inventory.",
          edit: "Vehicle updated.",
          purchase: "Purchase complete. One vehicle deducted from stock.",
          restock: "Stock replenished.",
          delete: "Vehicle removed.",
          promote: "Administrator access granted.",
        }[action],
      );
      if (action === "promote") await loadUsers();
      else await loadVehicles();
    } catch (err) {
      setModalError(err.message);
      if (action === "purchase") await loadVehicles();
    } finally {
      setBusy(false);
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
          saveSession(value);
          setView("inventory");
          setFilters(blankFilters);
          setApplied(blankFilters);
        }}
      />
    );
  const stock = vehicles.reduce((sum, v) => sum + v.quantity, 0);
  const value = vehicles.reduce(
    (sum, v) => sum + Number(v.price) * v.quantity,
    0,
  );
  const activeFilters = Object.values(applied).some(Boolean);
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <Brand />
        <p className="nav-label">WORKSPACE</p>
        <nav>
          <button
            className={view === "inventory" ? "active" : ""}
            onClick={() => setView("inventory")}
          >
            <LayoutGrid size={18} />
            Inventory<span className="nav-count">{vehicles.length}</span>
          </button>
          {admin && (
            <button
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
                saveSession(null);
                setVehicles([]);
                setUsers([]);
                setModal(null);
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
            {view === "inventory" ? "Vehicle inventory" : "Team access"}
          </div>
          <span className="role-badge">
            <ShieldCheck size={14} />
            {admin ? "Admin workspace" : "Member workspace"}
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
                  <button className="primary" onClick={() => open("add")}>
                    <Plus size={18} />
                    Add vehicle
                  </button>
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
                      {vehicles.length.toString().padStart(2, "0")}
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
                    <strong>{stock.toString().padStart(2, "0")}</strong>
                  </div>
                  <span className="stat-note">Ready for the road</span>
                </div>
                <div className="stat">
                  <span className="stat-icon">
                    <ArrowUpRight size={20} />
                  </span>
                  <div>
                    <p>Inventory value{activeFilters ? " · filtered" : ""}</p>
                    <strong className="value-number">{money(value)}</strong>
                  </div>
                  <span className="stat-note">USD · current stock</span>
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
                    Vehicle inventory <span>{vehicles.length}</span>
                  </h2>
                  <span className="muted small">Browse. Discover. Drive.</span>
                </div>
                <form
                  className="filter-panel"
                  onSubmit={(e) => {
                    e.preventDefault();
                    setApplied({ ...filters });
                  }}
                >
                  <div className="filter-title">
                    <SlidersHorizontal size={16} />
                    <span>Find your fit</span>
                  </div>
                  <div className="filter-fields">
                    <Field
                      label="Make"
                      placeholder="e.g. Toyota"
                      value={filters.make}
                      onChange={(e) =>
                        setFilters({ ...filters, make: e.target.value })
                      }
                    />
                    <Field
                      label="Model"
                      placeholder="e.g. Camry"
                      value={filters.model}
                      onChange={(e) =>
                        setFilters({ ...filters, model: e.target.value })
                      }
                    />
                    <Field
                      label="Category"
                      placeholder="e.g. SUV"
                      value={filters.category}
                      onChange={(e) =>
                        setFilters({ ...filters, category: e.target.value })
                      }
                    />
                    <Field
                      label="Min price ($)"
                      type="number"
                      min="0"
                      max="1000000000"
                      step="0.01"
                      placeholder="Any"
                      value={filters.min_price}
                      onChange={(e) =>
                        setFilters({ ...filters, min_price: e.target.value })
                      }
                    />
                    <Field
                      label="Max price ($)"
                      type="number"
                      min="0"
                      max="1000000000"
                      step="0.01"
                      placeholder="Any"
                      value={filters.max_price}
                      onChange={(e) =>
                        setFilters({ ...filters, max_price: e.target.value })
                      }
                    />
                    <button className="primary search-button">
                      <Search size={17} />
                      Search
                    </button>
                  </div>
                  {activeFilters && (
                    <button
                      type="button"
                      className="clear-button"
                      onClick={() => {
                        setFilters(blankFilters);
                        setApplied(blankFilters);
                      }}
                    >
                      Clear filters <X size={13} />
                    </button>
                  )}
                </form>
                <div className="results-line">
                  <span>
                    {loading
                      ? "Loading collection…"
                      : `${vehicles.length} vehicle${vehicles.length === 1 ? "" : "s"} in your collection`}
                  </span>
                  <span className="flex items-center gap-1">
                    Newest first
                    <ChevronDown size={13} />
                  </span>
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
              </section>
            </>
          ) : (
            <section>
              <div className="page-heading">
                <div>
                  <p className="eyebrow">PEOPLE BEHIND THE FORECOURT</p>
                  <h1>
                    Team access<span>.</span>
                  </h1>
                  <p className="muted">
                    Manage who can maintain inventory and invite other
                    administrators.
                  </p>
                </div>
              </div>
              {error && (
                <p className="error" role="alert">
                  {error}
                </p>
              )}
              <div className="team-list">
                {loading ? (
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
      {modal && (
        <Modal
          title={
            {
              add: "Add a vehicle",
              edit: "Edit vehicle",
              restock: "Replenish stock",
              delete: "Delete vehicle?",
              purchase: "Confirm your purchase",
              promote: "Grant administrator access?",
            }[modal.action]
          }
          onClose={() => setModal(null)}
          busy={busy}
        >
          <form onSubmit={submitAction}>
            {["add", "edit"].includes(modal.action) ? (
              <div className="modal-fields">
                {["make", "model", "category"].map((key) => (
                  <Field
                    key={key}
                    label={key[0].toUpperCase() + key.slice(1)}
                    name={key}
                    defaultValue={modal.vehicle?.[key] || ""}
                    required
                    maxLength={100}
                  />
                ))}
                <Field
                  label="Price (USD)"
                  name="price"
                  type="number"
                  min="0"
                  max="1000000000"
                  step="0.01"
                  defaultValue={modal.vehicle?.price || ""}
                  required
                />
                <Field
                  label="Quantity in stock"
                  name="quantity"
                  type="number"
                  min="0"
                  max="1000000"
                  step="1"
                  defaultValue={modal.vehicle?.quantity ?? 0}
                  required
                />
              </div>
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
                  max="1000000"
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
                inventory? This cannot be undone.
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
                      delete: "Delete vehicle",
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
