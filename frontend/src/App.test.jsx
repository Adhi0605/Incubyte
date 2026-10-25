import { beforeEach, afterEach, expect, test, vi } from "vitest";
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import App from "./App";

const admin = {
  id: 1,
  email: "owner@example.com",
  role: "admin",
  workspace_id: 1,
};
const buyer = {
  id: 2,
  email: "buyer@example.com",
  role: "user",
  workspace_id: 1,
};
const car = {
  id: 1,
  make: "Toyota",
  model: "Camry",
  category: "Sedan",
  price: "3200000.50",
  condition: "new",
  year: 2025,
  mileage_km: 0,
  fuel_type: "Petrol",
  transmission: "Automatic",
  city: "Delhi",
  trim: "ZX",
  color: "White",
  description: "A synthetic Indian listing.",
  stock_number: "FC-001",
  info_url: "https://www.toyotabharat.com/",
  currency: "INR",
  images: [
    {
      url: "/cars/toyota.jpg",
      alt: "Representative Toyota",
      credit: "Test Photographer",
      source_url: "https://example.com/photo",
      license: "CC BY 4.0",
    },
  ],
  quantity: 2,
};
let user, cars, requests, total;
beforeEach(() => {
  sessionStorage.clear();
  user = buyer;
  cars = [{ ...car }];
  requests = [];
  total = 1;
  HTMLDialogElement.prototype.showModal = function () {
    this.setAttribute("open", "");
  };
  HTMLDialogElement.prototype.close = function () {
    this.removeAttribute("open");
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (path, options = {}) => {
      requests.push({ path, options });
      let data;
      if (path === "/api/auth/login" || path === "/api/auth/register")
        data = { access_token: "test-token", user };
      else if (path === "/api/auth/me") data = user;
      else if (path.startsWith("/api/vehicles/search"))
        data = {
          items: cars.filter((c) => !c.deleted_at).map((c) => ({ ...c })),
          total: cars.some((c) => !c.deleted_at) ? total : 0,
          page: Number(
            new URL(path, "http://local").searchParams.get("page") || 1,
          ),
          page_size: 12,
          summary: { listings: total, units: 240, value: "320000000" },
        };
      else if (path.startsWith("/api/analytics"))
        data = {
          summary: {
            recorded_sales: "12500000",
            units_sold: 12,
            average_sale_price: "1041666.67",
            inventory_value: "320000000",
            inventory_units: 240,
            active_listings: 200,
          },
          monthly_sales: [{ month: "2026-09", sales: "12500000", units: 12 }],
          by_brand: [{ name: "Toyota", sales: "12500000", units: 12 }],
          by_condition: [{ name: "new", sales: "12500000", units: 12 }],
          by_fuel: [{ name: "Petrol", units: 12 }],
          low_stock: [{ ...car, quantity: 1 }],
          aging_stock: [{ ...car, age_days: 120 }],
          demo_notice:
            "Includes synthetic transaction history; no payments collected.",
        };
      else if (path === "/api/vehicles/1" && options.method === "PUT")
        data = { ...cars[0], ...JSON.parse(options.body) };
      else if (path === "/api/vehicles/1" && !options.method)
        data = { ...cars[0] };
      else if (path === "/api/vehicles/import") data = { imported: 2 };
      else if (path === "/api/vehicles" && options.method === "POST")
        data = { ...car, ...JSON.parse(options.body) };
      else if (path === "/api/vehicles/archived")
        data = cars.filter((c) => c.deleted_at).map((c) => ({ ...c }));
      else if (path === "/api/vehicles/1" && options.method === "DELETE") {
        cars[0].deleted_at = "2026-10-24T10:00:00+00:00";
        return { ok: true, status: 204 };
      } else if (path === "/api/vehicles/1/restore") {
        cars[0].deleted_at = null;
        data = { ...cars[0] };
      } else if (path === "/api/vehicles/1/purchase") {
        cars[0].quantity--;
        data = { ...cars[0] };
      } else if (path === "/api/vehicles/1/restock") {
        cars[0].quantity += JSON.parse(options.body).quantity;
        data = { ...cars[0] };
      } else if (path === "/api/users/2/promote")
        data = { ...buyer, role: "admin", workspace_id: 1 };
      else if (path === "/api/users")
        data = [
          admin,
          requests.some((r) => r.path.endsWith("/promote"))
            ? { ...buyer, role: "admin" }
            : buyer,
        ];
      else throw new Error("Unexpected request: " + path);
      return {
        ok: true,
        status:
          path === "/api/vehicles/import" ||
          (path === "/api/vehicles" && options.method === "POST") ||
          path === "/api/auth/register"
            ? 201
            : 200,
        json: async () => data,
      };
    }),
  );
});
afterEach(() => {
  vi.unstubAllGlobals();
  sessionStorage.clear();
});
function savedSession(person) {
  user = person;
  sessionStorage.setItem(
    "forecourt-session",
    JSON.stringify({ access_token: "test-token", user: person }),
  );
}

test("sign in restores inventory and sign out removes the session", async () => {
  render(<App />);
  fireEvent.change(screen.getByLabelText("Email address"), {
    target: { value: buyer.email },
  });
  fireEvent.change(screen.getByLabelText("Password"), {
    target: { value: "BuyerPassword123!" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
  expect(await screen.findByText("Camry")).toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: /add vehicle/i }),
  ).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Sign out" }));
  expect(
    await screen.findByRole("button", { name: "Sign in" }),
  ).toBeInTheDocument();
  expect(sessionStorage.getItem("forecourt-session")).toBeNull();
});

test("purchase requires confirmation, sends no quantity, and refreshes stock", async () => {
  savedSession(buyer);
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: /^purchase$/i }));
  expect(screen.getByRole("dialog")).toHaveTextContent(
    "Stock will decrease by one",
  );
  fireEvent.click(screen.getByRole("button", { name: "Confirm purchase" }));
  await waitFor(() =>
    expect(screen.getByText("1 in stock")).toBeInTheDocument(),
  );
  const request = requests.find((r) => r.path.endsWith("/purchase"));
  expect(request.options.method).toBe("POST");
  expect(request.options.body).toBeUndefined();
});

test("admin restocks and promotes a registered user", async () => {
  savedSession(admin);
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: "Restock" }));
  fireEvent.change(screen.getByLabelText("Units to add"), {
    target: { value: "3" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Restock vehicle" }));
  await waitFor(() =>
    expect(screen.getByText("5 in stock")).toBeInTheDocument(),
  );
  expect(
    JSON.parse(requests.find((r) => r.path.endsWith("/restock")).options.body),
  ).toEqual({ quantity: 3 });
  fireEvent.click(screen.getByRole("button", { name: /team access/i }));
  fireEvent.click(await screen.findByRole("button", { name: "Make admin" }));
  fireEvent.click(screen.getByRole("button", { name: "Grant admin access" }));
  await waitFor(() =>
    expect(requests.some((r) => r.path === "/api/users/2/promote")).toBe(true),
  );
  await waitFor(() =>
    expect(
      screen.queryByRole("button", { name: "Make admin" }),
    ).not.toBeInTheDocument(),
  );
});

test("search forwards all supplied filters", async () => {
  savedSession(buyer);
  render(<App />);
  await screen.findByText("Camry");
  for (const [label, value] of [
    ["Make", "Toyota"],
    ["Model", "Camry"],
    ["Category", "Sedan"],
    ["Transmission", "Automatic"],
    ["City", "Delhi"],
    ["Min year", "2020"],
    ["Max year", "2026"],
    ["Min price (₹)", "30000"],
    ["Max price (₹)", "40000"],
  ]) {
    fireEvent.change(screen.getByLabelText(label), { target: { value } });
  }
  fireEvent.click(screen.getByRole("button", { name: "Search" }));
  await waitFor(() =>
    expect(
      requests.some((r) =>
        [
          "make=Toyota",
          "model=Camry",
          "category=Sedan",
          "transmission=Automatic",
          "city=Delhi",
          "min_year=2020",
          "max_year=2026",
          "min_price=30000",
          "max_price=40000",
        ].every((part) => r.path.includes(part)),
      ),
    ).toBe(true),
  );
});

test("expired saved sessions return to sign in", async () => {
  savedSession(buyer);
  fetch.mockResolvedValue({
    ok: false,
    status: 401,
    json: async () => ({ detail: "Invalid or expired session" }),
  });
  render(<App />);
  expect(
    await screen.findByRole("button", { name: "Sign in" }),
  ).toBeInTheDocument();
  expect(sessionStorage.getItem("forecourt-session")).toBeNull();
});

test("admins archive and restore a vehicle with its original stock", async () => {
  savedSession(admin);
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: "Delete" }));
  expect(screen.getByRole("dialog")).toHaveTextContent(
    /restore.*archived vehicles/i,
  );
  fireEvent.click(screen.getByRole("button", { name: "Archive vehicle" }));
  await waitFor(() =>
    expect(screen.queryByText("Camry")).not.toBeInTheDocument(),
  );
  fireEvent.click(screen.getByRole("button", { name: "Archived vehicles" }));
  fireEvent.click(await screen.findByRole("button", { name: "Restore" }));
  expect(requests.some((r) => r.path.endsWith("/restore"))).toBe(false);
  fireEvent.click(screen.getByRole("button", { name: "Confirm restore" }));
  await waitFor(() =>
    expect(screen.queryByText("Camry")).not.toBeInTheDocument(),
  );
  expect(requests.find((r) => r.path.endsWith("/restore")).options.method).toBe(
    "POST",
  );
  fireEvent.click(screen.getByRole("button", { name: /^Inventory/ }));
  expect(await screen.findByText("Camry")).toBeInTheDocument();
  expect(screen.getByText("2 in stock")).toBeInTheDocument();
});

test("regular members have no archive navigation", async () => {
  savedSession(buyer);
  render(<App />);
  await screen.findByText("Camry");
  expect(
    screen.queryByRole("button", { name: "Archived vehicles" }),
  ).not.toBeInTheDocument();
  expect(requests.some((r) => r.path === "/api/vehicles/archived")).toBe(false);
});

test("restore can be cancelled and failures preserve the archived vehicle", async () => {
  savedSession(admin);
  cars[0].deleted_at = "2026-10-24T10:00:00+00:00";
  const original = fetch.getMockImplementation();
  fetch.mockImplementation((path, options) =>
    path.endsWith("/restore")
      ? Promise.resolve({
          ok: false,
          status: 409,
          json: async () => ({ detail: "Vehicle is already active" }),
        })
      : original(path, options),
  );
  render(<App />);
  fireEvent.click(
    await screen.findByRole("button", { name: "Archived vehicles" }),
  );
  fireEvent.click(await screen.findByRole("button", { name: "Restore" }));
  fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Restore" }));
  fireEvent.click(screen.getByRole("button", { name: "Confirm restore" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Vehicle is already active",
  );
  expect(screen.getByRole("dialog")).toBeInTheDocument();
  expect(cars[0].deleted_at).toBeTruthy();
});

test("registration automatically opens a persistent private admin workspace", async () => {
  user = admin;
  render(<App />);
  fireEvent.click(screen.getByRole("button", { name: "Create an account" }));
  expect(screen.getByText(/private workspace/i)).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Email address"), {
    target: { value: admin.email },
  });
  fireEvent.change(screen.getByLabelText("Password"), {
    target: { value: "StrongPassword123!" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Create account" }));
  expect(
    await screen.findByRole("button", { name: "Add vehicle" }),
  ).toBeInTheDocument();
  expect(
    JSON.parse(sessionStorage.getItem("forecourt-session")).user.workspace_id,
  ).toBe(1);
  expect(
    screen.queryByRole("button", { name: /start.*demo|reset/i }),
  ).not.toBeInTheDocument();
});

test("server pagination uses full summary and resets page when filters or sorting change", async () => {
  savedSession(admin);
  total = 200;
  render(<App />);
  await screen.findByText("Camry");
  expect(screen.getByText(/1–12 of 200/)).toBeInTheDocument();
  expect(screen.getByLabelText("Inventory statistics")).toHaveTextContent(
    "240",
  );
  fireEvent.click(screen.getByRole("button", { name: "Next page" }));
  await waitFor(() =>
    expect(requests.some((r) => r.path.includes("page=2"))).toBe(true),
  );
  fireEvent.change(screen.getByLabelText("Condition"), {
    target: { value: "used" },
  });
  fireEvent.change(screen.getByLabelText("Fuel"), {
    target: { value: "Diesel" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Search" }));
  await waitFor(() => expect(requests.at(-1).path).toContain("condition=used"));
  expect(requests.at(-1).path).toContain("fuel_type=Diesel");
  expect(
    new URL(requests.at(-1).path, "http://local").searchParams.get("page"),
  ).toBe("1");
  fireEvent.change(screen.getByLabelText("Sort inventory"), {
    target: { value: "price_asc" },
  });
  await waitFor(() => expect(requests.at(-1).path).toContain("sort=price_asc"));
});

test("details fetch full specifications, gallery attribution and safe external links", async () => {
  savedSession(admin);
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: /view details/i }));
  const dialog = await screen.findByRole("dialog");
  expect(
    await within(dialog).findByText("A synthetic Indian listing."),
  ).toBeInTheDocument();
  expect(within(dialog).getByText("FC-001")).toBeInTheDocument();
  expect(within(dialog).getByText(/Test Photographer/)).toBeInTheDocument();
  expect(
    within(dialog).getByRole("link", { name: /manufacturer/i }),
  ).toHaveAttribute("rel", "noopener noreferrer");
  expect(requests.some((r) => r.path === "/api/vehicles/1")).toBe(true);
});

test("admin analytics has date filters, accessible charts and stock insights", async () => {
  savedSession(admin);
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: "Analytics" }));
  expect(
    await screen.findByText("Recorded sales", { selector: "p" }),
  ).toBeInTheDocument();
  expect(
    await screen.findByRole("img", { name: /monthly recorded sales/i }),
  ).toBeInTheDocument();
  expect(
    screen.getByText(/synthetic transaction history/i),
  ).toBeInTheDocument();
  expect(
    screen.getByRole("heading", { name: "Low stock" }),
  ).toBeInTheDocument();
  expect(
    screen.getByRole("heading", { name: "Aging stock" }),
  ).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("From date"), {
    target: { value: "2026-09-01" },
  });
  fireEvent.change(screen.getByLabelText("To date"), {
    target: { value: "2026-09-30" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Apply dates" }));
  await waitFor(() =>
    expect(requests.at(-1).path).toContain(
      "start_date=2026-09-01&end_date=2026-09-30",
    ),
  );
});

test("members cannot access analytics or CSV import", async () => {
  savedSession(buyer);
  render(<App />);
  await screen.findByText("Camry");
  expect(
    screen.queryByRole("button", { name: "Analytics" }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "Import CSV" }),
  ).not.toBeInTheDocument();
});

test("used vehicle form limits quantity to one and rejects invalid submissions", async () => {
  savedSession(admin);
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: "Add vehicle" }));
  const dialog = screen.getByRole("dialog");
  fireEvent.change(within(dialog).getByLabelText("Condition"), {
    target: { value: "used" },
  });
  const quantity = within(dialog).getByLabelText("Quantity in stock");
  expect(quantity).toHaveAttribute("max", "1");
  fireEvent.change(quantity, { target: { value: "2" } });
  fireEvent.submit(dialog.querySelector("form"));
  expect(await within(dialog).findByRole("alert")).toHaveTextContent(
    /used.*one|used.*1/i,
  );
  expect(
    requests.some(
      (r) => r.path === "/api/vehicles" && r.options.method === "POST",
    ),
  ).toBe(false);
});

test("CSV import previews text, submits JSON and refreshes inventory", async () => {
  savedSession(admin);
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: "Import CSV" }));
  const csv = "make,model,category,price,quantity\nTata,Nexon,SUV,950000,2";
  fireEvent.change(screen.getByLabelText("CSV contents"), {
    target: { value: csv },
  });
  fireEvent.click(screen.getByRole("button", { name: "Import vehicles" }));
  expect(await screen.findByText(/2 vehicles imported/i)).toBeInTheDocument();
  expect(
    JSON.parse(
      requests.find((r) => r.path === "/api/vehicles/import").options.body,
    ),
  ).toEqual({ csv });
});

test("expanded editing preserves API images and sends a valid optional VIN", async () => {
  savedSession(admin);
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: "Edit" }));
  const dialog = screen.getByRole("dialog");
  fireEvent.change(within(dialog).getByLabelText("Trim"), {
    target: { value: "ZX Premium" },
  });
  fireEvent.click(within(dialog).getByRole("button", { name: "Save changes" }));
  await waitFor(() =>
    expect(
      requests.some(
        (r) => r.path === "/api/vehicles/1" && r.options.method === "PUT",
      ),
    ).toBe(true),
  );
  const body = JSON.parse(
    requests.find((r) => r.options.method === "PUT").options.body,
  );
  expect(body.vin).toBe("");
  expect(body.images).toEqual(car.images);
  expect(body).toMatchObject({
    year: 2025,
    quantity: 2,
    mileage_km: 0,
    trim: "ZX Premium",
  });
});

test("gallery switches photos and exposes the selected image credit", async () => {
  savedSession(admin);
  cars[0].images = [
    ...car.images,
    {
      url: "/cars/second.jpg",
      alt: "Rear representative view",
      credit: "Second Photographer",
      license: "CC0",
      source_url: "https://example.com/second",
    },
  ];
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: /view details/i }));
  fireEvent.click(await screen.findByRole("button", { name: "Show image 2" }));
  expect(screen.getByText(/Second Photographer/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Show image 2" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  expect(screen.getByRole("link", { name: /photo source/i })).toHaveAttribute(
    "href",
    "https://example.com/second",
  );
});

test("invalid filter ranges do not request inventory, and clearing filters resets them", async () => {
  savedSession(admin);
  render(<App />);
  await screen.findByText("Camry");
  const count = requests.length;
  fireEvent.change(screen.getByLabelText("Min price (₹)"), {
    target: { value: "900000" },
  });
  fireEvent.change(screen.getByLabelText("Max price (₹)"), {
    target: { value: "800000" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Search" }));
  expect(screen.getByRole("alert")).toHaveTextContent(/minimum price/i);
  expect(requests).toHaveLength(count);
  fireEvent.change(screen.getByLabelText("Max price (₹)"), {
    target: { value: "1000000" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Search" }));
  await waitFor(() =>
    expect(requests.at(-1).path).toContain("min_price=900000"),
  );
  fireEvent.click(screen.getByRole("button", { name: /clear filters/i }));
  await waitFor(() => expect(requests.at(-1).path).not.toContain("min_price="));
  expect(screen.getByLabelText("Min price (₹)")).toHaveValue(null);
});

test("CSV errors keep input for correction and do not report success", async () => {
  savedSession(admin);
  const original = fetch.getMockImplementation();
  fetch.mockImplementation((path, options) =>
    path === "/api/vehicles/import"
      ? Promise.resolve({
          ok: false,
          status: 422,
          json: async () => ({ detail: "Row 2: used quantity must be 0 or 1" }),
        })
      : original(path, options),
  );
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: "Import CSV" }));
  fireEvent.change(screen.getByLabelText("CSV contents"), {
    target: { value: "make,quantity\nTata,2" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Import vehicles" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Row 2");
  expect(screen.getByLabelText("CSV contents")).toHaveValue(
    "make,quantity\nTata,2",
  );
});

test("analytics handles API failure, retries, and shows empty date ranges", async () => {
  savedSession(admin);
  let attempt = 0;
  const original = fetch.getMockImplementation();
  fetch.mockImplementation((path, options) => {
    if (!path.startsWith("/api/analytics")) return original(path, options);
    attempt++;
    return Promise.resolve(
      attempt === 1
        ? {
            ok: false,
            status: 500,
            json: async () => ({ detail: "Analytics temporarily unavailable" }),
          }
        : {
            ok: true,
            status: 200,
            json: async () => ({
              summary: {
                recorded_sales: "0",
                units_sold: 0,
                average_sale_price: "0",
                inventory_value: "0",
                inventory_units: 0,
                active_listings: 0,
              },
              monthly_sales: [],
              by_brand: [],
              by_condition: [],
              by_fuel: [],
              low_stock: [],
              aging_stock: [],
            }),
          },
    );
  });
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: "Analytics" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Analytics temporarily unavailable",
  );
  fireEvent.click(screen.getByRole("button", { name: "Try again" }));
  expect(
    await screen.findByText("Recorded sales", { selector: "p" }),
  ).toBeInTheDocument();
  expect(
    screen.getAllByText("No recorded sales in this date range."),
  ).toHaveLength(4);
});

test("signing into another workspace clears the previous workspace summary while loading", async () => {
  savedSession(admin);
  total = 200;
  render(<App />);
  await screen.findByText("Camry");
  fireEvent.click(screen.getByRole("button", { name: "Sign out" }));
  const original = fetch.getMockImplementation();
  fetch.mockImplementation((path, options) =>
    path.startsWith("/api/vehicles/search")
      ? new Promise(() => {})
      : original(path, options),
  );
  user = { ...admin, id: 3, email: "second@example.com", workspace_id: 2 };
  fireEvent.change(screen.getByLabelText("Email address"), {
    target: { value: user.email },
  });
  fireEvent.change(screen.getByLabelText("Password"), {
    target: { value: "StrongPassword123!" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
  const stats = await screen.findByLabelText("Inventory statistics");
  expect(stats).not.toHaveTextContent("200");
  expect(screen.queryByText("Camry")).not.toBeInTheDocument();
});

test("a purchase from analytics details refreshes analytics after the mutation", async () => {
  savedSession(admin);
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: "Analytics" }));
  const lowStock = await screen.findByRole("heading", { name: "Low stock" });
  fireEvent.click(
    within(lowStock.closest("section")).getByRole("button", {
      name: "Toyota Camry",
    }),
  );
  fireEvent.click(await screen.findByRole("button", { name: "Purchase" }));
  fireEvent.click(screen.getByRole("button", { name: "Confirm purchase" }));
  await waitFor(() =>
    expect(
      requests.filter((r) => r.path.startsWith("/api/analytics")),
    ).toHaveLength(2),
  );
});

test("analytics stock insights start compact and expand on request", async () => {
  savedSession(admin);
  const original = fetch.getMockImplementation();
  fetch.mockImplementation(async (path, options) => {
    const response = await original(path, options);
    if (!path.startsWith("/api/analytics")) return response;
    const data = await response.json();
    data.low_stock = Array.from({ length: 15 }, (_, i) => ({
      ...car,
      id: i + 1,
      model: `Stock ${i + 1}`,
      quantity: 1,
    }));
    return { ...response, json: async () => data };
  });
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: "Analytics" }));
  const heading = await screen.findByRole("heading", { name: "Low stock" });
  const panel = heading.closest("section");
  await within(panel).findByRole("button", { name: "Toyota Stock 1" });
  expect(
    within(panel).queryByRole("button", { name: "Toyota Stock 7" }),
  ).not.toBeInTheDocument();
  fireEvent.click(
    within(panel).getByRole("button", { name: "Show all 15 vehicles" }),
  );
  expect(
    within(panel).getByRole("button", { name: "Toyota Stock 15" }),
  ).toBeInTheDocument();
  fireEvent.click(
    within(panel).getByRole("button", { name: "Show fewer vehicles" }),
  );
  expect(
    within(panel).queryByRole("button", { name: "Toyota Stock 15" }),
  ).not.toBeInTheDocument();
});
