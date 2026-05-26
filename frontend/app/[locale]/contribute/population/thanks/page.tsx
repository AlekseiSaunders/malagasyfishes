import { getTranslations } from "next-intl/server";

import { Link } from "@/i18n/routing";

export const dynamic = "force-dynamic";

export async function generateMetadata() {
  const t = await getTranslations("contribute.population.thanks");
  return { title: t("metaTitle") };
}

export default async function ContributePopulationThanksPage({
  searchParams,
}: {
  searchParams: { species?: string; id?: string };
}) {
  const t = await getTranslations("contribute.population.thanks");
  const speciesId =
    searchParams.species && /^\d+$/.test(searchParams.species)
      ? searchParams.species
      : null;

  return (
    <main className="mx-auto max-w-xl px-6 py-16">
      <header className="mb-6">
        <p className="font-sans text-[11px] font-bold uppercase tracking-[0.18em] text-slate-500">
          {t("eyebrow")}
        </p>
        <h1 className="mt-2 font-serif text-3xl text-slate-900">
          {t("title")}
        </h1>
      </header>

      <div className="rounded border border-slate-200 bg-white p-6">
        <p className="text-sm text-slate-800">{t("body1")}</p>
        <p className="mt-3 text-sm text-slate-700">{t("body2")}</p>
        <p className="mt-3 text-xs text-slate-500">{t("escalation")}</p>

        <div className="mt-6 flex flex-wrap gap-3">
          {speciesId ? (
            <Link
              href={`/species/${speciesId}/`}
              className="rounded border border-sky-600 px-4 py-2 text-sm font-medium text-sky-700 hover:bg-sky-50"
            >
              {t("backToSpecies")}
            </Link>
          ) : null}
          <Link
            href="/contribute/population"
            className="rounded bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-700"
          >
            {t("submitAnother")}
          </Link>
        </div>
      </div>
    </main>
  );
}
