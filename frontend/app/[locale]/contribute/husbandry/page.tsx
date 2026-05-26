import { Link } from "@/i18n/routing";
import { getTranslations } from "next-intl/server";

/**
 * Gate 09 placeholder for the Gate 10 husbandry contribute form.
 *
 * Spec §Sequencing (gate-09-husbandry-frontend.md): if Gate 10 slips, this
 * route renders a "coming soon" message with the mailto fallback. The demo
 * requires the CTA to be **present** as a visible frame — not functional.
 */
export async function generateMetadata() {
  const t = await getTranslations("contribute.husbandry");
  return { title: t("metaTitle") };
}

export default async function ContributeHusbandryStub({
  searchParams,
}: {
  searchParams: { species?: string };
}) {
  const speciesId = searchParams.species;
  const t = await getTranslations("contribute.husbandry");
  const subject = speciesId
    ? t("subjectForSpecies", { speciesId })
    : t("subjectGeneric");
  return (
    <main className="mx-auto max-w-2xl px-6 py-16">
      <h1 className="font-serif text-2xl text-slate-900">{t("title")}</h1>
      <p className="mt-4 text-slate-700">
        {t("bodyPrefix")}
        <a
          href={`mailto:alekseisaunders@gmail.com?subject=${encodeURIComponent(subject)}`}
          className="text-sky-700 hover:underline"
        >
          alekseisaunders@gmail.com
        </a>
        {t("bodySuffix")}
      </p>
      {speciesId ? (
        <p className="mt-6 text-sm">
          <Link
            href={`/species/${speciesId}/husbandry/`}
            className="text-sky-700 hover:underline"
          >
            {t("backToHusbandry")}
          </Link>
        </p>
      ) : null}
    </main>
  );
}
