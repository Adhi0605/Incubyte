import { useState } from "react";
import { Search, SlidersHorizontal, X } from "lucide-react";
import { Field, Select } from "./ui";
export const blankFilters = {
  make: "",
  model: "",
  category: "",
  condition: "",
  fuel_type: "",
  transmission: "",
  city: "",
  min_price: "",
  max_price: "",
  min_year: "",
  max_year: "",
};
export default function InventoryFilters({
  filters,
  setFilters,
  applied,
  onApply,
}) {
  const [error, setError] = useState("");
  const update = (key) => (e) =>
    setFilters({ ...filters, [key]: e.target.value });
  const active = Object.values(applied).some(Boolean);
  return (
    <form
      className="filter-panel"
      onSubmit={(e) => {
        e.preventDefault();
        if (
          filters.min_price !== "" &&
          filters.max_price !== "" &&
          Number(filters.min_price) > Number(filters.max_price)
        ) {
          setError("Minimum price must not exceed maximum price.");
          return;
        }
        if (
          filters.min_year &&
          filters.max_year &&
          Number(filters.min_year) > Number(filters.max_year)
        ) {
          setError("Minimum year must not exceed maximum year.");
          return;
        }
        setError("");
        onApply({ ...filters });
      }}
    >
      <div className="filter-title">
        <SlidersHorizontal size={16} />
        <span>Find your fit</span>
      </div>
      <div className="filter-fields">
        <Field
          label="Make"
          placeholder="e.g. Tata"
          value={filters.make}
          onChange={update("make")}
          maxLength={100}
        />
        <Field
          label="Model"
          placeholder="e.g. Nexon"
          value={filters.model}
          onChange={update("model")}
          maxLength={100}
        />
        <Field
          label="Category"
          placeholder="e.g. SUV"
          value={filters.category}
          onChange={update("category")}
          maxLength={100}
        />
        <Select
          label="Condition"
          value={filters.condition}
          onChange={update("condition")}
        >
          <option value="">Any condition</option>
          <option value="new">New</option>
          <option value="used">Used</option>
        </Select>
        <Select
          label="Fuel"
          value={filters.fuel_type}
          onChange={update("fuel_type")}
        >
          <option value="">Any fuel</option>
          {["Petrol", "Diesel", "Electric", "Hybrid", "CNG"].map((v) => (
            <option key={v}>{v}</option>
          ))}
        </Select>
        <Select
          label="Transmission"
          value={filters.transmission}
          onChange={update("transmission")}
        >
          <option value="">Any transmission</option>
          {["Manual", "Automatic"].map((v) => (
            <option key={v}>{v}</option>
          ))}
        </Select>
        <Field
          label="City"
          placeholder="e.g. Bengaluru"
          value={filters.city}
          onChange={update("city")}
          maxLength={100}
        />
        <Field
          label="Min price (₹)"
          type="number"
          min="0"
          max="1000000000"
          step="0.01"
          placeholder="Any"
          value={filters.min_price}
          onChange={update("min_price")}
        />
        <Field
          label="Max price (₹)"
          type="number"
          min="0"
          max="1000000000"
          step="0.01"
          placeholder="Any"
          value={filters.max_price}
          onChange={update("max_price")}
        />
        <Field
          label="Min year"
          type="number"
          min="1990"
          max={new Date().getFullYear() + 1}
          placeholder="Any"
          value={filters.min_year}
          onChange={update("min_year")}
        />
        <Field
          label="Max year"
          type="number"
          min="1990"
          max={new Date().getFullYear() + 1}
          placeholder="Any"
          value={filters.max_year}
          onChange={update("max_year")}
        />
        <button className="primary search-button">
          <Search size={17} />
          Search
        </button>
      </div>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {active && (
        <button
          type="button"
          className="clear-button"
          onClick={() => {
            setFilters({ ...blankFilters });
            onApply({ ...blankFilters });
            setError("");
          }}
        >
          Clear filters <X size={13} />
        </button>
      )}
    </form>
  );
}
