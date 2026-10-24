import { beforeEach, afterEach, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import App from "./App";

const admin = { id: 1, email: "owner@example.com", role: "admin" };
const buyer = { id: 2, email: "buyer@example.com", role: "user" };
const car = {
  id: 1,
  make: "Toyota",
  model: "Camry",
  category: "Sedan",
  price: "32000.50",
  quantity: 2,
};
let user, cars, requests;
beforeEach(() => {
  sessionStorage.clear();
  user = buyer;
  cars = [{ ...car }];
  requests = [];
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
        data = cars.filter((c) => !c.deleted_at).map((c) => ({ ...c }));
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
        data = { ...buyer, role: "admin" };
      else if (path === "/api/users")
        data = [
          admin,
          requests.some((r) => r.path.endsWith("/promote"))
            ? { ...buyer, role: "admin" }
            : buyer,
        ];
      else throw new Error("Unexpected request: " + path);
      return { ok: true, status: 200, json: async () => data };
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
    ["Min price ($)", "30000"],
    ["Max price ($)", "40000"],
  ]) {
    fireEvent.change(screen.getByLabelText(label), { target: { value } });
  }
  fireEvent.click(screen.getByRole("button", { name: "Search" }));
  await waitFor(() =>
    expect(
      requests.some((r) =>
        r.path.includes(
          "make=Toyota&model=Camry&category=Sedan&min_price=30000&max_price=40000",
        ),
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
