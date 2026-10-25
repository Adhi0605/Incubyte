import { useState } from "react";
import { CarArt } from "../CarArt";

export const safeExternalUrl = (url) => {
  try {
    const parsed = new URL(url);
    return parsed.protocol === "https:" && !parsed.username && !parsed.password
      ? parsed.href
      : null;
  } catch {
    return null;
  }
};
export const safeImageUrl = (url) =>
  typeof url === "string" &&
  (/^\/cars\/[a-z0-9_.-]+$/i.test(url) || safeExternalUrl(url))
    ? url
    : null;

export default function VehicleImage({
  vehicle,
  image = vehicle.images?.[0],
  eager = false,
}) {
  const [failedUrl, setFailedUrl] = useState(null);
  const url = safeImageUrl(image?.url);
  if (!url || failedUrl === url)
    return (
      <div className="image-fallback">
        <CarArt category={vehicle.category} color="#a5b9aa" />
        <span>
          {url
            ? "Image unavailable · illustration"
            : "Representative illustration"}
        </span>
      </div>
    );
  return (
    <img
      className="vehicle-photo"
      src={url}
      alt={image.alt || `Representative ${vehicle.make} ${vehicle.model}`}
      loading={eager ? "eager" : "lazy"}
      onError={() => setFailedUrl(url)}
    />
  );
}
