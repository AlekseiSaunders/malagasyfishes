"use client";

import { useTranslations } from "next-intl";
import { useMemo, useState, useTransition } from "react";

import { useRouter } from "@/i18n/routing";

import {
  submitPopulationAction,
  type PopulationSubmissionErrors,
} from "./actions";

type BreedingStatus = "breeding" | "non-breeding" | "unknown";

export interface SpeciesPickerOption {
  id: number;
  scientific_name: string;
  family: string;
  iucn_status: string | null;
  common_name: string | null;
}

interface Props {
  species: SpeciesPickerOption[];
  /** Pre-fill from `?species={id}` query param (Gate 15 AC-15.2). */
  preselectedSpeciesId: number | null;
  /** Today in ISO format — passed from server so date defaults are stable in tests. */
  todayIso: string;
}

const NOTES_MAX = 1000;
const NOTES_WARN_AT = 800;

export default function PopulationSubmissionForm({
  species,
  preselectedSpeciesId,
  todayIso,
}: Props) {
  const t = useTranslations("contribute.population.form");
  const tBreeding = useTranslations("contribute.population.breeding");
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [errors, setErrors] = useState<PopulationSubmissionErrors>({});
  const [transientError, setTransientError] = useState<string | null>(null);

  // --- form state ---
  const [speciesId, setSpeciesId] = useState<number | null>(
    preselectedSpeciesId,
  );
  const [speciesQuery, setSpeciesQuery] = useState<string>(() => {
    if (preselectedSpeciesId == null) return "";
    const found = species.find((s) => s.id === preselectedSpeciesId);
    return found?.scientific_name ?? "";
  });
  const [countTotal, setCountTotal] = useState<string>("");
  const [showBreakdown, setShowBreakdown] = useState<boolean>(false);
  const [countMale, setCountMale] = useState<string>("");
  const [countFemale, setCountFemale] = useState<string>("");
  const [countUnsexed, setCountUnsexed] = useState<string>("");
  const [breedingStatus, setBreedingStatus] =
    useState<BreedingStatus>("unknown");
  const [lastCensusDate, setLastCensusDate] = useState<string>(todayIso);
  const [notes, setNotes] = useState<string>("");
  const [reconcileModalOpen, setReconcileModalOpen] = useState<boolean>(false);

  // --- derived helpers ---
  const parseCount = (s: string): number =>
    s.trim() === "" || !Number.isFinite(Number(s)) ? 0 : Math.trunc(Number(s));

  const breakdownTotal =
    parseCount(countMale) + parseCount(countFemale) + parseCount(countUnsexed);
  const totalNum = parseCount(countTotal);
  const breakdownMismatch =
    showBreakdown && breakdownTotal > 0 && breakdownTotal !== totalNum;

  const filteredSpecies = useMemo(() => {
    if (!speciesQuery.trim()) return species.slice(0, 12);
    const q = speciesQuery.toLowerCase();
    return species
      .filter(
        (s) =>
          s.scientific_name.toLowerCase().includes(q) ||
          (s.common_name && s.common_name.toLowerCase().includes(q)) ||
          s.family.toLowerCase().includes(q),
      )
      .slice(0, 24);
  }, [species, speciesQuery]);

  // --- submit ---
  function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setErrors({});
    setTransientError(null);

    // UX §5: if breakdown doesn't reconcile, surface as a soft modal,
    // NOT a blocking error. Three choices: match total to breakdown,
    // keep total + put extras in unsexed, or let me fix it.
    if (breakdownMismatch && breakdownTotal < totalNum) {
      // breakdown sums to LESS than total — modal offers "put extras in unsexed"
      setReconcileModalOpen(true);
      return;
    }
    if (breakdownMismatch && breakdownTotal > totalNum) {
      // breakdown EXCEEDS total — must be fixed before submit (would 400)
      setErrors({
        count_total: t("countSplitExceedsTotal", {
          breakdown: breakdownTotal,
          total: totalNum,
        }),
      });
      return;
    }

    doSubmit();
  }

  function doSubmit() {
    startTransition(async () => {
      const result = await submitPopulationAction({
        species: speciesId,
        count_total: totalNum,
        count_male: parseCount(countMale),
        count_female: parseCount(countFemale),
        count_unsexed: parseCount(countUnsexed),
        breeding_status: breedingStatus,
        last_census_date: lastCensusDate,
        notes,
      });

      if (result.ok) {
        const params = new URLSearchParams();
        if (result.speciesId != null) {
          params.set("species", String(result.speciesId));
        }
        params.set("id", String(result.submissionId));
        router.push(`/contribute/population/thanks?${params.toString()}`);
        return;
      }
      if ("transientError" in result) {
        setTransientError(result.transientError);
        return;
      }
      setErrors(result.errors);
    });
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="space-y-6 rounded border border-slate-200 bg-white p-6"
    >
      {/* Honeypot — sr-only, defeated by the screen-reader-aware bot too
          rarely to matter for our threat model. */}
      <input
        type="text"
        name="website"
        autoComplete="off"
        tabIndex={-1}
        aria-hidden="true"
        className="sr-only"
        // We don't bind it; intentionally empty in normal flow. Bots will
        // fill it, which becomes a `website` field in the POST body —
        // handled by the serializer's silent-spam path.
      />

      {errors.form ? (
        <p
          role="alert"
          className="rounded border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800"
        >
          {errors.form}
        </p>
      ) : null}

      {transientError ? (
        <p
          role="alert"
          className="rounded border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800"
        >
          {transientError}
        </p>
      ) : null}

      {/* Species selector — autocomplete from the existing list. No
          'Other' option per Gate 15 Q2 lock. Inline help text below
          tells submitters to email for unlisted species. */}
      <div>
        <label
          htmlFor="species-search"
          className="block text-sm font-medium text-slate-900"
        >
          {t("speciesLabel")}
        </label>
        <input
          id="species-search"
          type="text"
          autoComplete="off"
          value={speciesQuery}
          onChange={(e) => {
            setSpeciesQuery(e.target.value);
            setSpeciesId(null);
          }}
          placeholder={t("speciesPlaceholder")}
          className="mt-1 block w-full rounded border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
          aria-describedby="species-help species-error"
        />
        {speciesQuery.trim() && filteredSpecies.length > 0 && !speciesId ? (
          <ul className="mt-2 max-h-64 overflow-y-auto rounded border border-slate-200 bg-white">
            {filteredSpecies.map((s) => (
              <li key={s.id}>
                <button
                  type="button"
                  onClick={() => {
                    setSpeciesId(s.id);
                    setSpeciesQuery(s.scientific_name);
                  }}
                  className="block w-full px-3 py-2 text-left text-sm hover:bg-slate-50"
                >
                  <span className="font-serif italic text-slate-900">
                    {s.scientific_name}
                  </span>
                  {s.common_name ? (
                    <span className="ml-2 text-slate-600">
                      · {s.common_name}
                    </span>
                  ) : null}
                  <span className="ml-2 text-xs uppercase tracking-wider text-slate-500">
                    {s.family}
                  </span>
                  {s.iucn_status ? (
                    <span className="ml-2 rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-semibold text-slate-700">
                      {s.iucn_status}
                    </span>
                  ) : null}
                </button>
              </li>
            ))}
          </ul>
        ) : null}
        <p id="species-help" className="mt-1 text-xs text-slate-500">
          {t.rich("speciesHelp", {
            email: (chunks) => (
              <a
                href="mailto:alekseisaunders@gmail.com"
                className="text-sky-700 underline underline-offset-2"
              >
                {chunks}
              </a>
            ),
          })}
        </p>
        {errors.species ? (
          <p id="species-error" className="mt-1 text-sm text-red-700">
            {errors.species}
          </p>
        ) : null}
      </div>

      {/* Total count — UX §5: total-first, breakdown collapsed. */}
      <div>
        <label
          htmlFor="count-total"
          className="block text-sm font-medium text-slate-900"
        >
          {t("countTotalLabel")}
        </label>
        <input
          id="count-total"
          type="text"
          inputMode="numeric"
          pattern="[0-9]*"
          value={countTotal}
          onChange={(e) =>
            setCountTotal(e.target.value.replace(/[^0-9]/g, ""))
          }
          className="mt-1 block w-32 rounded border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
          aria-describedby="count-total-help count-total-error"
        />
        <p id="count-total-help" className="mt-1 text-xs text-slate-500">
          {t("countTotalHelp")}
        </p>
        {errors.count_total ? (
          <p id="count-total-error" className="mt-1 text-sm text-red-700">
            {errors.count_total}
          </p>
        ) : null}
      </div>

      <div>
        <button
          type="button"
          onClick={() => setShowBreakdown((s) => !s)}
          className="text-sm text-sky-700 underline underline-offset-2 hover:text-sky-900"
        >
          {showBreakdown ? t("hideBreakdown") : t("showBreakdown")}
        </button>
        {showBreakdown ? (
          <div className="mt-3 rounded border border-slate-200 bg-slate-50 p-4">
            <div className="grid grid-cols-3 gap-3">
              {(
                [
                  ["count-male", t("countMaleLabel"), countMale, setCountMale],
                  [
                    "count-female",
                    t("countFemaleLabel"),
                    countFemale,
                    setCountFemale,
                  ],
                  [
                    "count-unsexed",
                    t("countUnsexedLabel"),
                    countUnsexed,
                    setCountUnsexed,
                  ],
                ] as const
              ).map(([id, label, value, setter]) => (
                <div key={id}>
                  <label
                    htmlFor={id}
                    className="block text-xs font-medium text-slate-700"
                  >
                    {label}
                  </label>
                  <input
                    id={id}
                    type="text"
                    inputMode="numeric"
                    pattern="[0-9]*"
                    value={value}
                    onChange={(e) =>
                      setter(e.target.value.replace(/[^0-9]/g, ""))
                    }
                    className="mt-1 block w-full rounded border border-slate-300 px-2 py-1.5 text-sm shadow-sm focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
                  />
                </div>
              ))}
            </div>
            <p
              className={`mt-3 text-xs ${
                breakdownMismatch ? "text-amber-700" : "text-slate-600"
              }`}
            >
              {t("breakdownReconcile", {
                entered: breakdownTotal,
                total: totalNum,
              })}
            </p>
          </div>
        ) : null}
      </div>

      {/* Breeding status — pills per UX §5. */}
      <div>
        <p className="block text-sm font-medium text-slate-900">
          {t("breedingStatusLabel")}
        </p>
        <div className="mt-2 inline-flex gap-2">
          {(
            ["breeding", "non-breeding", "unknown"] as const satisfies readonly BreedingStatus[]
          ).map((status) => (
            <button
              key={status}
              type="button"
              onClick={() => setBreedingStatus(status)}
              className={`rounded-full px-4 py-1.5 text-sm font-medium ${
                breedingStatus === status
                  ? "bg-sky-600 text-white"
                  : "bg-slate-100 text-slate-700 hover:bg-slate-200"
              }`}
              aria-pressed={breedingStatus === status}
            >
              {tBreeding(status)}
            </button>
          ))}
        </div>
      </div>

      {/* Last counted on — native date picker. */}
      <div>
        <label
          htmlFor="last-census-date"
          className="block text-sm font-medium text-slate-900"
        >
          {t("lastCensusDateLabel")}
        </label>
        <input
          id="last-census-date"
          type="date"
          value={lastCensusDate}
          max={todayIso}
          onChange={(e) => setLastCensusDate(e.target.value)}
          className="mt-1 block w-48 rounded border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
        />
      </div>

      {/* Notes — 1000 char limit, counter visible from 800. */}
      <div>
        <label
          htmlFor="notes"
          className="block text-sm font-medium text-slate-900"
        >
          {t("notesLabel")}
        </label>
        <textarea
          id="notes"
          value={notes}
          onChange={(e) => setNotes(e.target.value.slice(0, NOTES_MAX))}
          placeholder={t("notesPlaceholder")}
          rows={4}
          className="mt-1 block w-full rounded border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
        />
        {notes.length >= NOTES_WARN_AT ? (
          <p className="mt-1 text-xs text-slate-500">
            {notes.length} / {NOTES_MAX}
          </p>
        ) : null}
        {errors.notes ? (
          <p className="mt-1 text-sm text-red-700">{errors.notes}</p>
        ) : null}
      </div>

      <div className="flex items-center justify-between border-t border-slate-200 pt-5">
        <p className="text-xs text-slate-500">{t("disclaimer")}</p>
        <button
          type="submit"
          disabled={pending || !speciesId || !countTotal}
          className="rounded bg-sky-600 px-5 py-2 text-sm font-semibold text-white shadow-sm hover:bg-sky-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {pending ? t("submitting") : t("submit")}
        </button>
      </div>

      {/* Reconciliation modal — UX §5 soft confirm, not blocking. */}
      {reconcileModalOpen ? (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="reconcile-modal-title"
          className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4"
        >
          <div className="max-w-md rounded bg-white p-6 shadow-xl">
            <h2
              id="reconcile-modal-title"
              className="font-serif text-lg text-slate-900"
            >
              {t("reconcileTitle")}
            </h2>
            <p className="mt-2 text-sm text-slate-700">
              {t("reconcileBody", {
                total: totalNum,
                breakdown: breakdownTotal,
              })}
            </p>
            <div className="mt-4 flex flex-col gap-2">
              <button
                type="button"
                onClick={() => {
                  // Match total to breakdown (lower the total)
                  setCountTotal(String(breakdownTotal));
                  setReconcileModalOpen(false);
                  doSubmit();
                }}
                className="rounded bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-700"
              >
                {t("reconcileMatchTotal", { breakdown: breakdownTotal })}
              </button>
              <button
                type="button"
                onClick={() => {
                  // Keep total, put extras in unsexed
                  setCountUnsexed(
                    String(parseCount(countUnsexed) + (totalNum - breakdownTotal)),
                  );
                  setReconcileModalOpen(false);
                  doSubmit();
                }}
                className="rounded border border-sky-600 bg-white px-4 py-2 text-sm font-medium text-sky-700 hover:bg-sky-50"
              >
                {t("reconcileKeepTotal", {
                  extras: totalNum - breakdownTotal,
                })}
              </button>
              <button
                type="button"
                onClick={() => setReconcileModalOpen(false)}
                className="rounded px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100"
              >
                {t("reconcileLetMeFix")}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </form>
  );
}
