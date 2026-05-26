import { getTranslations } from "next-intl/server";
import Link from "next/link";
import { redirect } from "next/navigation";

import ActivityFeed from "@/components/institution/ActivityFeed";
import AggregatePanel from "@/components/institution/AggregatePanel";
import { ApiError, apiFetch } from "@/lib/api";
import { getServerDrfToken } from "@/lib/auth";
import {
  fetchInstitutionPopulations,
  fetchInstitutionSummary,
} from "@/lib/institutionDashboard";
import type { MeResponse } from "@/lib/me";

export const dynamic = "force-dynamic";

export async function generateMetadata() {
  const t = await getTranslations("dashboard.institution");
  return {
    title: t("metaTitle"),
    description: t("metaDescription"),
  };
}


export default async function InstitutionDashboardPage() {
  const drfToken = await getServerDrfToken();
  if (!drfToken) {
    redirect("/login?callbackUrl=/dashboard/institution");
  }

  // Page-level gate: redirect to /account if claim is not approved.
  // Middleware checks tier+token (cheap); the rich check happens here.
  let me: MeResponse | null = null;
  try {
    me = await apiFetch<MeResponse>("/api/v1/auth/me/", {
      authToken: drfToken,
      revalidate: 0,
    });
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      redirect("/login?callbackUrl=/dashboard/institution");
    }
    throw error;
  }

  if (!me) {
    redirect("/account");
  }

  const membership = me.institution_membership;
  if (!membership || membership.claim_status !== "approved") {
    redirect("/account");
  }

  const t = await getTranslations("dashboard.institution");
  const [populations, summary] = await Promise.all([
    fetchInstitutionPopulations(drfToken),
    fetchInstitutionSummary(drfToken),
  ]);

  return (
    <main className="mx-auto max-w-5xl px-6 py-12">
      <header className="mb-8">
        <p className="font-sans text-[11px] font-bold uppercase tracking-[0.18em] text-slate-500">
          {t("eyebrow")}
        </p>
        <h1 className="mt-2 font-serif text-3xl text-slate-900">{t("title")}</h1>
        <p className="mt-3 max-w-3xl text-sm text-slate-600">
          {t("subtitle", { institution: membership.institution_name ?? "" })}
        </p>
        <p className="mt-3 flex flex-wrap gap-x-5 gap-y-2">
          <Link
            href="/dashboard/institution/breeding-events"
            className="text-sm text-sky-700 underline underline-offset-2 hover:text-sky-900"
          >
            {t("breedingEventsLink")}
          </Link>
          <Link
            href="/dashboard/institution/field-programs"
            className="text-sm text-sky-700 underline underline-offset-2 hover:text-sky-900"
          >
            {t("fieldProgramsLink")}
          </Link>
        </p>
      </header>

      <AggregatePanel summary={summary} />

      {summary?.recent_activity ? (
        <ActivityFeed rows={summary.recent_activity} />
      ) : null}

      {populations === null ? (
        <p
          role="alert"
          className="rounded border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800"
        >
          {t("transientError")}
        </p>
      ) : populations.results.length === 0 ? (
        <div className="rounded border border-slate-200 bg-white p-6">
          <p className="text-sm text-slate-700">{t("emptyState.message")}</p>
          <p className="mt-2 text-xs text-slate-500">
            {t.rich("emptyState.contact", {
              email: (chunks) => (
                <a
                  href="mailto:alekseisaunders@gmail.com"
                  className="text-sky-700 underline underline-offset-2 hover:text-sky-900"
                >
                  {chunks}
                </a>
              ),
            })}
          </p>
        </div>
      ) : (
        <div className="overflow-hidden rounded border border-slate-200 bg-white">
          <table className="min-w-full text-sm">
            <thead className="bg-slate-50 text-left text-[11px] font-medium uppercase tracking-wider text-slate-500">
              <tr>
                <th className="px-4 py-3">{t("table.species")}</th>
                <th className="px-4 py-3">{t("table.count")}</th>
                <th className="px-4 py-3">{t("table.breeding")}</th>
                <th className="px-4 py-3">{t("table.lastCensus")}</th>
                <th className="px-4 py-3 text-right">{t("table.actions")}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {populations.results.map((row) => (
                <tr key={row.id} className="hover:bg-slate-50">
                  <td className="px-4 py-3">
                    <span className="font-serif italic text-slate-900">
                      {row.species.scientific_name}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-slate-700">
                    {row.count_total ?? "—"}
                  </td>
                  <td className="px-4 py-3 text-slate-700">
                    {t(`breedingStatus.${row.breeding_status}`)}
                  </td>
                  <td className="px-4 py-3 text-slate-700">
                    {row.last_census_date ?? t("table.never")}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <Link
                      href={`/dashboard/institution/populations/${row.id}/edit`}
                      className="text-sky-700 underline underline-offset-2 hover:text-sky-900"
                    >
                      {t("table.edit")}
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </main>
  );
}
