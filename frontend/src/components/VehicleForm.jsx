import { useState } from "react";
import { Field, Select } from "./ui";
import { safeExternalUrl, safeImageUrl } from "./VehicleImage";

export function vehicleBody(data) {
  const quantity = Number(data.quantity);
  if (data.condition === "used" && quantity > 1)
    throw new Error(
      "A used listing can contain only one car (quantity 0 or 1).",
    );
  if (!Number.isInteger(quantity) || quantity < 0 || quantity > 1000000)
    throw new Error("Quantity must be a whole number between 0 and 1,000,000.");
  for (const key of ["make", "model", "category"])
    if (!data[key]?.trim()) throw new Error(`Enter a ${key}.`);
  if (
    !data.price ||
    !/^\d+(\.\d{1,2})?$/.test(data.price) ||
    Number(data.price) > 1000000000
  )
    throw new Error(
      "Enter an INR price from 0 to 1,000,000,000 with up to two decimal places.",
    );
  const year = Number(data.year),
    mileage = Number(data.mileage_km);
  if (
    !Number.isInteger(year) ||
    year < 1990 ||
    year > new Date().getFullYear() + 1
  )
    throw new Error(
      `Enter a valid year between 1990 and ${new Date().getFullYear() + 1}.`,
    );
  if (!Number.isInteger(mileage) || mileage < 0 || mileage > 2000000)
    throw new Error("Mileage must be a whole number from 0 to 2,000,000 km.");
  if (data.info_url && !safeExternalUrl(data.info_url))
    throw new Error("Manufacturer information must use an HTTPS URL.");
  if (data.vin && !/^[A-HJ-NPR-Z0-9]{17}$/i.test(data.vin))
    throw new Error(
      "VIN must contain 17 letters and numbers, excluding I, O and Q.",
    );
  const images = JSON.parse(data.images || "[]");
  if (images.length > 8) throw new Error("Use at most 8 gallery images.");
  for (const image of images) {
    if (!safeImageUrl(image.url))
      throw new Error("Image URLs must use HTTPS or existing /cars/ assets.");
    if (!image.alt?.trim())
      throw new Error("Add alternative text for each image.");
    if (image.source_url && !safeExternalUrl(image.source_url))
      throw new Error("Image source links must use HTTPS.");
  }
  return {
    ...data,
    make: data.make.trim(),
    model: data.model.trim(),
    category: data.category.trim(),
    price: data.price,
    quantity,
    year,
    mileage_km: mileage,
    images,
    vin: data.vin || "",
  };
}

export default function VehicleForm({ vehicle }) {
  const [condition, setCondition] = useState(vehicle?.condition || "new");
  const [images, setImages] = useState(vehicle?.images || []);
  const updateImage = (i, key, value) =>
    setImages((previous) =>
      previous.map((v, n) => (n === i ? { ...v, [key]: value } : v)),
    );
  return (
    <>
      <div className="modal-fields">
        {["make", "model", "category"].map((key) => (
          <Field
            key={key}
            label={key[0].toUpperCase() + key.slice(1)}
            name={key}
            defaultValue={vehicle?.[key] || ""}
            required
            maxLength={100}
          />
        ))}
        <Select
          label="Condition"
          name="condition"
          value={condition}
          onChange={(e) => setCondition(e.target.value)}
        >
          <option value="new">New</option>
          <option value="used">Used</option>
        </Select>
        <Field
          label="Price (INR)"
          name="price"
          type="number"
          min="0"
          max="1000000000"
          step="0.01"
          defaultValue={vehicle?.price ?? ""}
          required
        />
        <Field
          label="Quantity in stock"
          name="quantity"
          type="number"
          min="0"
          max={condition === "used" ? "1" : "1000000"}
          step="1"
          defaultValue={vehicle?.quantity ?? 0}
          required
        />
        <Field
          label="Year"
          name="year"
          type="number"
          min="1990"
          max={new Date().getFullYear() + 1}
          step="1"
          defaultValue={vehicle?.year || new Date().getFullYear()}
          required
        />
        <Field
          label="Trim"
          name="trim"
          defaultValue={vehicle?.trim || ""}
          maxLength={100}
        />
        <Field
          label="Mileage (km)"
          name="mileage_km"
          type="number"
          min="0"
          max="2000000"
          step="1"
          defaultValue={vehicle?.mileage_km ?? 0}
          required
        />
        <Select
          label="Fuel"
          name="fuel_type"
          defaultValue={vehicle?.fuel_type || "Petrol"}
          required
        >
          {["Petrol", "Diesel", "Electric", "Hybrid", "CNG"].map((v) => (
            <option key={v}>{v}</option>
          ))}
        </Select>
        <Select
          label="Transmission"
          name="transmission"
          defaultValue={vehicle?.transmission || "Manual"}
          required
        >
          {["Manual", "Automatic"].map((v) => (
            <option key={v}>{v}</option>
          ))}
        </Select>
        <Field
          label="Colour"
          name="color"
          defaultValue={vehicle?.color || "White"}
          maxLength={80}
        />
        <Field
          label="City"
          name="city"
          defaultValue={vehicle?.city || "Bengaluru"}
          maxLength={100}
        />
        <Field
          label="Stock number"
          name="stock_number"
          defaultValue={vehicle?.stock_number || ""}
          maxLength={80}
        />
        <Field
          label="VIN (optional)"
          name="vin"
          defaultValue={vehicle?.vin || ""}
          minLength={17}
          maxLength={17}
          pattern="[A-HJ-NPR-Za-hj-npr-z0-9]{17}"
        />
        <Field
          label="Manufacturer / model URL"
          name="info_url"
          type="url"
          pattern="https://.*"
          defaultValue={vehicle?.info_url || ""}
          maxLength={2000}
        />
        <label className="field field-full">
          <span>Description</span>
          <textarea
            name="description"
            defaultValue={vehicle?.description || ""}
            maxLength={4000}
            rows={3}
          />
        </label>
      </div>
      {condition === "used" && (
        <p className="form-help">
          Each used listing represents one physical car. Quantity must be 0 or
          1.
        </p>
      )}
      <fieldset className="image-editor">
        <legend>Gallery images</legend>
        <p className="form-help">
          Use HTTPS image links and include attribution. Local supplied photos
          are preserved when editing.
        </p>
        {images.map((item, i) => (
          <div className="image-editor-row" key={i}>
            <Field
              label={`Image ${i + 1} URL`}
              value={item.url}
              onChange={(e) => updateImage(i, "url", e.target.value)}
              required
              maxLength={2000}
            />
            <Field
              label={`Image ${i + 1} alternative text`}
              value={item.alt}
              onChange={(e) => updateImage(i, "alt", e.target.value)}
              required
              maxLength={200}
            />
            <Field
              label={`Image ${i + 1} credit`}
              value={item.credit || ""}
              onChange={(e) => updateImage(i, "credit", e.target.value)}
              maxLength={300}
            />
            <Field
              label={`Image ${i + 1} source URL`}
              type="url"
              pattern="https://.*"
              value={item.source_url || ""}
              onChange={(e) => updateImage(i, "source_url", e.target.value)}
              maxLength={2000}
            />
            <Field
              label={`Image ${i + 1} license`}
              value={item.license || ""}
              onChange={(e) => updateImage(i, "license", e.target.value)}
              maxLength={100}
            />
            <button
              type="button"
              className="danger-text"
              onClick={() =>
                setImages((previous) => previous.filter((_, n) => n !== i))
              }
            >
              Remove image {i + 1}
            </button>
          </div>
        ))}
        <button
          type="button"
          className="secondary"
          disabled={images.length >= 8}
          onClick={() =>
            setImages((previous) => [
              ...previous,
              { url: "", alt: "", credit: "", source_url: "", license: "" },
            ])
          }
        >
          Add gallery image
        </button>
        <input type="hidden" name="images" value={JSON.stringify(images)} />
      </fieldset>
    </>
  );
}
