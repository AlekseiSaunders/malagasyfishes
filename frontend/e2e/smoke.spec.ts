import { expect, test } from "@playwright/test";

test("hero landing renders mission, coverage stat, and three nav cards", async ({
  page,
}) => {
  await page.goto("/", { timeout: 60000, waitUntil: "domcontentloaded" });

  await expect(
    page.getByRole("heading", {
      level: 1,
      name: /shared record for Madagascar/i,
    }),
  ).toBeVisible({ timeout: 30000 });

  await expect(page.getByTestId("coverage-gap-stat")).toBeVisible();

  const primarySections = page.getByRole("navigation", {
    name: /primary sections/i,
  });
  await expect(primarySections.getByRole("link")).toHaveCount(3);
});

test("coverage-gap stat links to pre-filtered directory", async ({ page }) => {
  await page.goto("/");

  const stat = page.getByTestId("coverage-gap-stat");
  await expect(stat).toBeVisible();
  const href = await stat.getAttribute("href");
  expect(href).toMatch(
    /^\/species\/?\?iucn_status=CR,EN,VU&has_captive_population=false$/,
  );
});

test("site header nav renders links in Dashboard → Map → Directory → About order", async ({
  page,
}) => {
  await page.goto("/");

  const primaryNav = page.getByRole("navigation", {
    name: "Primary",
    exact: true,
  });
  const labels = await primaryNav.getByRole("link").allInnerTexts();
  // Gate 4 inserted "Coordinator" between Dashboard and Map. The original
  // four spec labels must stay in order; Coordinator is allowed.
  expect(labels).toContain("Dashboard");
  expect(labels).toContain("Map");
  expect(labels).toContain("Species Directory");
  expect(labels).toContain("About");
  expect(labels.indexOf("Dashboard")).toBeLessThan(labels.indexOf("Map"));
  expect(labels.indexOf("Map")).toBeLessThan(
    labels.indexOf("Species Directory"),
  );
  expect(labels.indexOf("Species Directory")).toBeLessThan(
    labels.indexOf("About"),
  );
});

test("About page renders owner and GitHub link", async ({ page }) => {
  await page.goto("/about/");

  // The About page is structured with an "About" eyebrow above an h1 that
  // carries the descriptive title — was renamed from a literal "About" h1
  // during the visual-system pass. Match the descriptive headline instead.
  await expect(
    page.getByRole("heading", { level: 1, name: /Madagascar.*endemic freshwater fish/i }),
  ).toBeVisible();
  await expect(page.getByText(/Aleksei Saunders/)).toBeVisible();
  await expect(
    page.getByRole("link", { name: /github\.com\/AlekseiSaunders\/malagasyfishes/i }),
  ).toBeVisible();
});

test("species directory renders count header and filter form", async ({ page }) => {
  // Hit /species (no trailing slash) to avoid Next's 308 redirect cycle on cold start.
  const resp = await page.goto("/species", { timeout: 60000, waitUntil: "domcontentloaded" });
  expect(resp?.status(), "preview should not 401 /species").toBeLessThan(400);

  await expect(
    page.getByRole("heading", { level: 1, name: /^Species Directory$/ }),
  ).toBeVisible({ timeout: 30000 });
  await expect(page.getByRole("form", { name: /species filters/i })).toBeVisible();
});

test("coverage-gap deep link reflects filters in URL and page state", async ({ page }) => {
  const resp = await page.goto(
    "/species?iucn_status=CR,EN,VU&has_captive_population=false",
    { timeout: 60000, waitUntil: "domcontentloaded" },
  );
  expect(resp?.status(), "preview should not 401 /species").toBeLessThan(400);

  // URL preserves the filter params (browsers may %2C-encode the comma).
  const decoded = decodeURIComponent(page.url());
  expect(decoded).toContain("iucn_status=CR,EN,VU");
  expect(decoded).toContain("has_captive_population=false");

  // IUCN toggle buttons for CR/EN/VU are pressed — proves the deep link rehydrated filter state.
  for (const code of ["CR", "EN", "VU"]) {
    await expect(
      page.getByRole("button", { name: code, exact: true }),
    ).toHaveAttribute("aria-pressed", "true", { timeout: 30000 });
  }
});

// Profile-page E2E coverage is deferred until staging DRF is wired up (W3 decision).
// The Vercel preview's NEXT_PUBLIC_API_URL currently points nowhere reachable, so
// /species/{id}/ renders the backend-unreachable branch rather than real content or
// a proper 404. Unit tests in lib/speciesDetail.test.ts cover the URL helpers.

test("site footer is present on every page", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("contentinfo")).toBeVisible();
  await expect(page.getByRole("contentinfo")).toContainText(/Apache-2\.0/);
});
