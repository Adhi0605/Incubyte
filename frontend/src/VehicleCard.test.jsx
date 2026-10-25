import { render, screen, fireEvent } from "@testing-library/react";
import { vi, test, expect } from "vitest";
import { VehicleCard } from "./VehicleCard";
const vehicle = {
  id: 1,
  make: "Toyota",
  model: "Camry",
  category: "Sedan",
  price: "32000.50",
  quantity: 0,
};
test("out-of-stock vehicles remain visible and cannot be purchased", () => {
  render(<VehicleCard vehicle={vehicle} admin={false} onAction={vi.fn()} />);
  expect(screen.getByText("Camry")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /out of stock/i })).toBeDisabled();
  expect(
    screen.queryByRole("button", { name: /restock/i }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: /edit/i }),
  ).not.toBeInTheDocument();
});
test("purchase sends the selected vehicle and pending purchase is disabled", () => {
  const action = vi.fn();
  const stocked = { ...vehicle, quantity: 3 };
  const { rerender } = render(
    <VehicleCard vehicle={stocked} admin={false} onAction={action} />,
  );
  fireEvent.click(screen.getByRole("button", { name: /purchase/i }));
  expect(action).toHaveBeenCalledWith("purchase", stocked);
  rerender(
    <VehicleCard vehicle={stocked} admin={false} onAction={action} busy />,
  );
  expect(screen.getByRole("button", { name: /purchase/i })).toBeDisabled();
});
test("admins can edit, restock and delete", () => {
  const action = vi.fn();
  render(<VehicleCard vehicle={vehicle} admin onAction={action} />);
  for (const name of ["Edit", "Restock", "Delete"]) {
    fireEvent.click(
      screen.getByRole("button", { name: new RegExp(name, "i") }),
    );
    expect(action).toHaveBeenCalledWith(name.toLowerCase(), vehicle);
  }
});

test("archived cards expose only an admin restore action", () => {
  const action = vi.fn();
  const archived = {
    ...vehicle,
    quantity: 3,
    deleted_at: "2026-10-24T10:00:00+00:00",
  };
  const { rerender } = render(
    <VehicleCard vehicle={archived} admin onAction={action} />,
  );
  for (const name of ["Purchase", "Edit", "Restock", "Delete"]) {
    expect(screen.queryByRole("button", { name })).not.toBeInTheDocument();
  }
  fireEvent.click(screen.getByRole("button", { name: "Restore" }));
  expect(action).toHaveBeenCalledWith("restore", archived);
  rerender(<VehicleCard vehicle={archived} admin onAction={action} busy />);
  expect(screen.getByRole("button", { name: "Restore" })).toBeDisabled();
  rerender(<VehicleCard vehicle={archived} admin={false} onAction={action} />);
  expect(
    screen.queryByRole("button", { name: "Restore" }),
  ).not.toBeInTheDocument();
});

test("cards show INR, condition and an API image that falls back accessibly", () => {
  render(
    <VehicleCard
      vehicle={{
        ...vehicle,
        condition: "used",
        images: [{ url: "/cars/test.jpg", alt: "Representative Toyota" }],
      }}
      admin
      onAction={vi.fn()}
    />,
  );
  expect(screen.getByText("Used")).toBeInTheDocument();
  expect(screen.getByText(/₹32,000.50/)).toBeInTheDocument();
  const img = screen.getByRole("img", { name: "Representative Toyota" });
  expect(img).toHaveAttribute("loading", "lazy");
  fireEvent.error(img);
  expect(screen.getByText(/image unavailable/i)).toBeInTheDocument();
});

test("used vehicles already in stock cannot be restocked", () => {
  render(
    <VehicleCard
      vehicle={{ ...vehicle, condition: "used", quantity: 1 }}
      admin
      onAction={vi.fn()}
    />,
  );
  expect(screen.getByRole("button", { name: "Restock" })).toBeDisabled();
});
