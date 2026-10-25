import { useEffect, useState } from "react";
import { ExternalLink } from "lucide-react";
import { api } from "../api";
import { money } from "../VehicleCard";
import { Modal } from "./ui";
import VehicleImage, { safeExternalUrl } from "./VehicleImage";

export default function VehicleDetails({
  vehicleId,
  token,
  onClose,
  onAction,
  admin,
}) {
  const [vehicle, setVehicle] = useState(null);
  const [error, setError] = useState("");
  const [index, setIndex] = useState(0);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setError("");
    setVehicle(null);
    api(`/vehicles/${vehicleId}`, { token, signal: controller.signal })
      .then((v) => {
        if (!controller.signal.aborted) {
          setVehicle(v);
          setIndex(0);
        }
      })
      .catch((e) => {
        if (!controller.signal.aborted) setError(e.message);
      });
    return () => controller.abort();
  }, [vehicleId, token, retry]);
  const image = vehicle?.images?.[index];
  const external = safeExternalUrl(vehicle?.info_url);
  const source = safeExternalUrl(image?.source_url);
  return (
    <Modal
      title={vehicle ? `${vehicle.make} ${vehicle.model}` : "Vehicle details"}
      onClose={onClose}
      wide
    >
      {error ? (
        <p role="alert" className="error">
          {error}{" "}
          <button onClick={() => setRetry((n) => n + 1)}>Try again</button>
        </p>
      ) : !vehicle ? (
        <p role="status">Loading vehicle details…</p>
      ) : (
        <>
          <div className="detail-layout">
            <section className="gallery" aria-label="Vehicle gallery">
              <div className="gallery-main">
                <VehicleImage vehicle={vehicle} image={image} eager />
              </div>
              {vehicle.images?.length > 1 && (
                <div
                  className="gallery-thumbnails"
                  aria-label="Choose an image"
                >
                  {vehicle.images.map((item, i) => (
                    <button
                      key={`${item.url}-${i}`}
                      aria-label={`Show image ${i + 1}`}
                      aria-pressed={index === i}
                      onClick={() => setIndex(i)}
                    >
                      <VehicleImage vehicle={vehicle} image={item} />
                    </button>
                  ))}
                </div>
              )}
              <p className="image-credit">
                Representative imagery; this is a synthetic listing.
              </p>
              {image && (
                <p className="image-credit">
                  {image.credit || "Credit not provided"}
                  {image.license && ` · ${image.license}`}{" "}
                  {source && (
                    <a href={source} target="_blank" rel="noopener noreferrer">
                      Photo source <ExternalLink size={12} />
                    </a>
                  )}
                </p>
              )}
            </section>
            <section className="detail-overview">
              <span className={`condition-badge ${vehicle.condition}`}>
                {vehicle.condition === "used" ? "Used" : "New"}
              </span>
              <p className="detail-price">{money(vehicle.price)}</p>
              <p className="muted">INR · synthetic asking price</p>
              <p>{vehicle.description || "No description available."}</p>
              <p className="stock-tag">
                {vehicle.quantity
                  ? `${vehicle.quantity} in stock`
                  : "Out of stock"}
              </p>
              {external && (
                <a
                  className="external-link"
                  href={external}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  Manufacturer / model information <ExternalLink size={15} />
                </a>
              )}
              {!vehicle.deleted_at && (
                <div className="detail-actions">
                  <button
                    className="primary"
                    disabled={!vehicle.quantity}
                    onClick={() => onAction("purchase", vehicle)}
                  >
                    Purchase
                  </button>
                  {admin && (
                    <button
                      className="secondary"
                      onClick={() => onAction("edit", vehicle)}
                    >
                      Edit vehicle
                    </button>
                  )}
                </div>
              )}
            </section>
          </div>
          <h3 className="spec-title">Full specifications</h3>
          <dl className="spec-grid">
            {[
              ["Make", vehicle.make],
              ["Model", vehicle.model],
              ["Category", vehicle.category],
              ["Year", vehicle.year],
              ["Trim", vehicle.trim],
              [
                "Mileage",
                vehicle.mileage_km != null
                  ? `${Number(vehicle.mileage_km).toLocaleString("en-IN")} km`
                  : null,
              ],
              ["Fuel", vehicle.fuel_type],
              ["Transmission", vehicle.transmission],
              ["Colour", vehicle.color],
              ["City", vehicle.city],
              ["Stock number", vehicle.stock_number],
              ["VIN", vehicle.vin],
              [
                "Created",
                vehicle.created_at &&
                  new Date(vehicle.created_at).toLocaleDateString("en-IN"),
              ],
              [
                "Updated",
                vehicle.updated_at &&
                  new Date(vehicle.updated_at).toLocaleDateString("en-IN"),
              ],
            ].map(([label, value]) => (
              <div key={label}>
                <dt>{label}</dt>
                <dd>
                  {value === "" || value == null ? "Not specified" : value}
                </dd>
              </div>
            ))}
          </dl>
        </>
      )}
    </Modal>
  );
}
