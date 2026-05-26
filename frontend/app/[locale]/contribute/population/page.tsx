import { getTranslations } from "next-intl/server";
import { redirect } from "next/navigation";

import { apiFetch } from "@/lib/api";
import { getServerDrfToken } from "@/lib/auth";

import PopulationSubmissionForm, {
  type SpeciesPickerOption,
} from "./PopulationSubmissionForm";

export const dynamic = "force-dynamic";

export async function generateMetadata() {
  const t = await getTranslations("contribute.population");
  return {
    title: t("metaTitle"),
    description: t("metaDescription"),
  };
}

interface SpeciesListResponse {
  count: number;
  results: Array<{
    id: number;
    scientific_name: string;
    family: string;
    iucn_status: string | null;
    common_names?: Array<{ name: string; language: string }>;
  }>;
}

export default async function ContributePopulationPage({
  searchParams,
}: {
  searchParams: { species?: string };
}) {
  // Middleware also gates this path, but defense-in-depth — if a
  // misconfigured deploy left the route reachable, we redirect home
  // rather than render an empty form.
  const drfToken = await getServerDrfToken();
  if (!drfToken) {
    redirect("/login?callbackUrl=/contribute/population");
  }

  const t = await getTranslations("contribute.population");

  // Fetch the entire species list (~150 rows; small payload). Client-side
  // filtering is faster + simpler than a per-keystroke API call, and
  // species don't churn.
  const speciesResponse = await apiFetch<SpeciesListResponse>(
    "/api/v1/species/?page_size=300",
    { authToken: drfToken, revalidate: 0 },
  );

  const species: SpeciesPickerOption[] = speciesResponse.results.map((s) => ({
    id: s.id,
    scientific_name: s.scientific_name,
    family: s.family,
    iucn_status: s.iucn_status,
    common_name: s.common_names?.[0]?.name ?? null,
  }));

  // Pre-fill from `?species={id}` (Gate 15 AC-15.2).
  const rawSpecies = searchParams.species;
  const preselectedSpeciesId =
    rawSpecies && /^\d+$/.test(rawSpecies) ? Number(rawSpecies) : null;
  const validPreselect =
    preselectedSpeciesId != null &&
    species.some((s) => s.id === preselectedSpeciesId)
      ? preselectedSpeciesId
      : null;

  // Today's ISO date — passed to client so the date input's default
  // matches across SSR + hydration without a Date() call in the client.
  const todayIso = new Date().toISOString().slice(0, 10);

  return (
    <main className="mx-auto max-w-2xl px-6 py-12">
      <header className="mb-8">
        <p className="font-sans text-[11px] font-bold uppercase tracking-[0.18em] text-slate-500">
          {t("eyebrow")}
        </p>
        <h1 className="mt-2 font-serif text-3xl text-slate-900">
          {t("title")}
        </h1>
        <p className="mt-3 text-sm text-slate-600">{t("subtitle")}</p>
      </header>
      <PopulationSubmissionForm
        species={species}
        preselectedSpeciesId={validPreselect}
        todayIso={todayIso}
      />
    </main>
  );
}
