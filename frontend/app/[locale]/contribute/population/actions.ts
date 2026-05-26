"use server";

import { getTranslations } from "next-intl/server";

import { resolveBaseUrl } from "@/lib/api";
import { getServerDrfToken } from "@/lib/auth";

/**
 * Gate 15 — submit a population to the curated submission queue.
 *
 * Uses raw fetch + DRF token (the existing pattern from signup/actions.ts
 * and verify/page.tsx) rather than apiFetch, because apiFetch is GET-only.
 * Translates server errors into a field-pointed `errors` map that the
 * client form renders inline.
 *
 * On success: returns `{ ok: true, submissionId, speciesId }` so the
 * client can route to `/contribute/population/thanks?...`.
 */

export interface PopulationSubmissionPayload {
  species: number | null;
  count_total: number;
  count_male: number;
  count_female: number;
  count_unsexed: number;
  breeding_status: "breeding" | "non-breeding" | "unknown";
  last_census_date: string;
  notes: string;
  /** Honeypot field. Real users leave it empty; bots fill it. */
  website?: string;
}

export type PopulationSubmissionErrors = {
  species?: string;
  count_total?: string;
  count_male?: string;
  count_female?: string;
  count_unsexed?: string;
  breeding_status?: string;
  last_census_date?: string;
  notes?: string;
  form?: string;
};

export type PopulationSubmissionResult =
  | { ok: true; submissionId: number; speciesId: number | null }
  | { ok: false; errors: PopulationSubmissionErrors }
  | { ok: false; transientError: string };

export async function submitPopulationAction(
  payload: PopulationSubmissionPayload,
): Promise<PopulationSubmissionResult> {
  const t = await getTranslations("contribute.population.errors");
  const drfToken = await getServerDrfToken();
  if (!drfToken) {
    return { ok: false, transientError: t("notAuthenticated") };
  }

  let response: Response;
  try {
    response = await fetch(
      `${resolveBaseUrl()}/api/v1/contribute/populations/`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Token ${drfToken}`,
        },
        body: JSON.stringify(payload),
        cache: "no-store",
      },
    );
  } catch {
    return { ok: false, transientError: t("unexpected") };
  }

  if (response.status === 201) {
    const body = (await response.json()) as { id: number; status: string };
    return {
      ok: true,
      submissionId: body.id,
      speciesId: payload.species,
    };
  }

  if (response.status === 400) {
    let errorBody: unknown;
    try {
      errorBody = await response.json();
    } catch {
      return { ok: false, errors: { form: t("unexpected") } };
    }
    return { ok: false, errors: parseFieldErrors(errorBody) };
  }

  if (response.status === 429) {
    return { ok: false, transientError: t("rateLimited") };
  }
  if (response.status === 404) {
    return { ok: false, transientError: t("notAvailable") };
  }
  if (response.status === 401 || response.status === 403) {
    return { ok: false, transientError: t("notAuthenticated") };
  }
  return { ok: false, transientError: t("unexpected") };
}

function parseFieldErrors(rawBody: unknown): PopulationSubmissionErrors {
  if (typeof rawBody !== "object" || rawBody === null) {
    return { form: typeof rawBody === "string" ? rawBody : "Unknown error" };
  }
  const result: PopulationSubmissionErrors = {};
  for (const [field, errs] of Object.entries(rawBody as Record<string, unknown>)) {
    const messages = Array.isArray(errs) ? errs : [errs];
    const first = messages[0];
    const text = typeof first === "string" ? first : JSON.stringify(first);
    if (field in EMPTY_ERRORS) {
      result[field as keyof PopulationSubmissionErrors] = text;
    } else {
      result.form = result.form ? `${result.form}; ${text}` : text;
    }
  }
  return result;
}

const EMPTY_ERRORS: Record<keyof PopulationSubmissionErrors, true> = {
  species: true,
  count_total: true,
  count_male: true,
  count_female: true,
  count_unsexed: true,
  breeding_status: true,
  last_census_date: true,
  notes: true,
  form: true,
};
