import { Link } from "@/i18n/routing";
import { getTranslations } from "next-intl/server";
import type { CSSProperties } from "react";

import IucnChart from "@/components/IucnChart";
import UpdatedAgo from "@/components/UpdatedAgo";
import { fetchDashboard } from "@/lib/dashboard";

export const revalidate = 3600;

export async function generateMetadata() {
  const t = await getTranslations("dashboard");
  return {
    title: t("metaTitle"),
    description: t("metaDescription"),
  };
}

const STALE_THRESHOLD_MS = 2 * 60 * 60 * 1000;

const COVERAGE_GAP_HREF =
  "/species/?iucn_status=CR,EN,VU&has_captive_population=false";

const EYEBROW_STYLE: CSSProperties = {
  margin: 0,
  fontFamily: "var(--sans)",
  fontSize: 11,
  fontWeight: 700,
  letterSpacing: "0.18em",
  textTransform: "uppercase",
  color: "var(--ink-3)",
};

const SECTION_EYEBROW_STYLE: CSSProperties = {
  ...EYEBROW_STYLE,
  marginBottom: 8,
};

const SECTION_H2_STYLE: CSSProperties = {
  margin: 0,
  fontFamily: "var(--serif)",
  fontSize: 22,
  fontWeight: 600,
  letterSpacing: "-0.01em",
  color: "var(--ink)",
  lineHeight: 1.2,
};

function StalenessBanner({ message }: { message: string }) {
  return (
    <div
      role="status"
      style={{
        padding: "12px 16px",
        borderRadius: "var(--radius)",
        border:
          "1px solid color-mix(in oklab, var(--highlight) 55%, var(--rule))",
        backgroundColor:
          "color-mix(in oklab, var(--highlight) 14%, var(--bg-raised))",
        fontSize: 13,
        color: "var(--ink)",
      }}
    >
      {message}
    </div>
  );
}

function StatTile({
  label,
  value,
  sublabel,
  href,
}: {
  label: string;
  value: number | string;
  sublabel?: string;
  href?: string;
}) {
  const tileStyle: CSSProperties = {
    display: "flex",
    flexDirection: "column",
    gap: 6,
    height: "100%",
    padding: "20px 22px",
    borderRadius: "var(--radius-lg)",
    border: "1px solid var(--rule)",
    backgroundColor: "var(--bg-raised)",
    color: "var(--ink)",
    textDecoration: "none",
  };
  const inner = (
    <>
      <span style={EYEBROW_STYLE}>{label}</span>
      <span
        style={{
          fontFamily: "var(--serif)",
          fontSize: 32,
          fontWeight: 600,
          letterSpacing: "-0.02em",
          fontVariantNumeric: "tabular-nums",
          color: "var(--ink)",
        }}
      >
        {typeof value === "number" ? value.toLocaleString() : value}
      </span>
      {sublabel ? (
        <span style={{ fontSize: 12, color: "var(--ink-3)" }}>{sublabel}</span>
      ) : null}
    </>
  );
  return href ? (
    <Link href={href} style={tileStyle}>
      {inner}
    </Link>
  ) : (
    <div style={tileStyle}>{inner}</div>
  );
}

const MAIN_STYLE: CSSProperties = {
  maxWidth: 1280,
  margin: "0 auto",
  padding: "48px 32px 80px",
  display: "flex",
  flexDirection: "column",
  gap: 40,
};

const GRID_STYLE: CSSProperties = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))",
  gap: 16,
};

export default async function DashboardPage() {
  const [data, t, tCommon] = await Promise.all([
    fetchDashboard(),
    getTranslations("dashboard"),
    getTranslations("common"),
  ]);

  if (!data) {
    return (
      <main style={MAIN_STYLE}>
        <header>
          <p style={EYEBROW_STYLE}>{t("eyebrow")}</p>
          <h1
            style={{
              margin: "8px 0 0",
              fontFamily: "var(--serif)",
              fontSize: 36,
              fontWeight: 600,
              letterSpacing: "-0.015em",
              color: "var(--ink)",
              lineHeight: 1.15,
            }}
          >
            {t("title")}
          </h1>
        </header>
        <StalenessBanner message={t("stalenessFailure")} />
        <p style={{ margin: 0, fontSize: 14, color: "var(--ink-2)" }}>
          {t("backendDownPrefix")}{" "}
          <Link
            href="/species/"
            style={{
              color: "var(--accent-2)",
              textDecoration: "none",
              borderBottom:
                "1px solid color-mix(in oklab, var(--accent-2) 35%, transparent)",
            }}
          >
            {t("backendDownLink")}
          </Link>
          .
        </p>
      </main>
    );
  }

  const {
    species_counts,
    ex_situ_coverage,
    field_programs,
    coordination,
    contributors,
    last_updated,
  } = data;
  const programByType = coordination.active_programs_by_type;
  const formalPrograms =
    (programByType.ssp ?? 0) + (programByType.eep ?? 0) + (programByType.cares ?? 0);
  const otherPrograms =
    (programByType.independent ?? 0) + (programByType.other ?? 0);
  const lastUpdatedMs = Date.parse(last_updated);
  const isStale =
    Number.isFinite(lastUpdatedMs) && Date.now() - lastUpdatedMs > STALE_THRESHOLD_MS;

  // Active-programs sublabel: empty / formal-only / formal+other.
  let activeProgramsSublabel: string;
  if (coordination.active_programs_total === 0) {
    activeProgramsSublabel = t("coordinated.activeProgramsSublabelEmpty");
  } else if (otherPrograms > 0) {
    activeProgramsSublabel = t("coordinated.activeProgramsSublabelMixed", {
      formal: formalPrograms,
      other: otherPrograms,
    });
  } else {
    activeProgramsSublabel = t("coordinated.activeProgramsSublabelFormalOnly", {
      formal: formalPrograms,
    });
  }

  return (
    <main style={MAIN_STYLE}>
      <header style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        <p style={EYEBROW_STYLE}>{t("eyebrow")}</p>
        <h1
          style={{
            margin: 0,
            fontFamily: "var(--serif)",
            fontSize: 36,
            fontWeight: 600,
            letterSpacing: "-0.015em",
            color: "var(--ink)",
            lineHeight: 1.15,
          }}
        >
          {t("title")}
        </h1>
        <UpdatedAgo iso={last_updated} />
      </header>

      {isStale ? <StalenessBanner message={t("stalenessStale")} /> : null}

      <Link
        href={COVERAGE_GAP_HREF}
        data-testid="coverage-gap-stat"
        style={{
          display: "block",
          padding: "24px 28px",
          borderRadius: "var(--radius-lg)",
          border:
            "1px solid color-mix(in oklab, var(--highlight) 45%, var(--rule))",
          backgroundColor:
            "color-mix(in oklab, var(--highlight) 12%, var(--bg-raised))",
          color: "var(--ink)",
          textDecoration: "none",
        }}
      >
        <p style={{ ...EYEBROW_STYLE, color: "var(--ink-2)" }}>
          {tCommon("coverageGap.eyebrow")}
        </p>
        <p
          style={{
            margin: "12px 0 0",
            fontFamily: "var(--serif)",
            fontSize: 22,
            fontWeight: 500,
            lineHeight: 1.35,
            color: "var(--ink)",
          }}
        >
          {tCommon.rich("coverageGap.body", {
            withoutCaptive:
              ex_situ_coverage.threatened_species_without_captive_population.toLocaleString(),
            total: ex_situ_coverage.threatened_species_total.toLocaleString(),
            gap: (chunks) => (
              <span
                style={{
                  fontSize: 40,
                  fontWeight: 600,
                  fontVariantNumeric: "tabular-nums",
                  letterSpacing: "-0.02em",
                }}
              >
                {chunks}
              </span>
            ),
            ts: (chunks) => (
              <span
                style={{
                  fontSize: 26,
                  fontWeight: 600,
                  fontVariantNumeric: "tabular-nums",
                }}
              >
                {chunks}
              </span>
            ),
          })}
        </p>
        <p
          style={{
            margin: "12px 0 0",
            fontSize: 13,
            fontWeight: 600,
            color: "var(--accent-2)",
          }}
        >
          {tCommon("coverageGap.seeWhich")}
        </p>
      </Link>

      <section
        style={{
          padding: "24px 28px",
          borderRadius: "var(--radius-lg)",
          border: "1px solid var(--rule)",
          backgroundColor: "var(--bg-raised)",
        }}
      >
        <IucnChart counts={species_counts.by_iucn_status} caption={t("iucnChartCaption")} />
      </section>

      <section aria-label={t("totals.ariaLabel")}>
        <p style={SECTION_EYEBROW_STYLE}>{t("totals.eyebrow")}</p>
        <h2 style={SECTION_H2_STYLE}>{t("totals.title")}</h2>
        <ul
          role="list"
          style={{
            ...GRID_STYLE,
            listStyle: "none",
            margin: "16px 0 0",
            padding: 0,
          }}
        >
          <li>
            <StatTile
              label={t("totals.totalSpecies")}
              value={species_counts.total}
              sublabel={t("totals.totalSpeciesSublabel", {
                described: species_counts.described.toLocaleString(),
                undescribed: species_counts.undescribed.toLocaleString(),
              })}
              href="/species/"
            />
          </li>
          <li>
            <StatTile
              label={t("totals.institutions")}
              value={ex_situ_coverage.institutions_active}
            />
          </li>
          <li>
            <StatTile
              label={t("totals.exSituTracked")}
              value={ex_situ_coverage.total_populations_tracked}
            />
          </li>
        </ul>
      </section>

      <section aria-label={t("coordinated.ariaLabel")}>
        <p style={SECTION_EYEBROW_STYLE}>{t("coordinated.eyebrow")}</p>
        <h2 style={SECTION_H2_STYLE}>{t("coordinated.title")}</h2>
        <ul
          role="list"
          style={{
            ...GRID_STYLE,
            listStyle: "none",
            margin: "16px 0 0",
            padding: 0,
          }}
        >
          <li>
            <StatTile
              label={t("coordinated.activePrograms")}
              value={coordination.active_programs_total}
              sublabel={activeProgramsSublabel}
            />
          </li>
          <li>
            <StatTile
              label={t("coordinated.transfersInFlight")}
              value={coordination.transfers_in_flight}
              sublabel={t("coordinated.transfersInFlightSublabel")}
            />
          </li>
          <li>
            <StatTile
              label={t("coordinated.transfersCompleted", {
                days: coordination.transfer_window_days,
              })}
              value={coordination.transfers_recent_completed}
              sublabel={t("coordinated.transfersCompletedSublabel")}
            />
          </li>
        </ul>
      </section>

      {contributors ? (
        <section aria-label={t("contributors.ariaLabel")}>
          <p style={SECTION_EYEBROW_STYLE}>{t("contributors.eyebrow")}</p>
          <h2 style={SECTION_H2_STYLE}>{t("contributors.title")}</h2>
          <p
            style={{
              margin: "8px 0 0",
              fontSize: 14,
              color: "var(--ink-2)",
              lineHeight: 1.5,
              maxWidth: 760,
            }}
          >
            {t("contributors.caption", {
              days: contributors.activity_window_days,
            })}
          </p>
          <ul
            role="list"
            style={{
              ...GRID_STYLE,
              listStyle: "none",
              margin: "16px 0 0",
              padding: 0,
            }}
          >
            {/* Gate 15 Q1 lock — split the single "active institutions"
                tile into two equal-weight tiles. Falls back to the legacy
                single tile if the backend hasn't shipped the split fields
                yet (defensive across deploy windows). */}
            {contributors.institutional_contributors_total !== undefined &&
            contributors.verified_keeper_network_total !== undefined ? (
              <>
                <li>
                  <StatTile
                    label={t("contributors.institutionalContributors")}
                    value={contributors.institutional_contributors_total}
                    sublabel={t("contributors.institutionalContributorsSublabel")}
                  />
                </li>
                <li>
                  <StatTile
                    label={t("contributors.verifiedKeeperNetwork")}
                    value={contributors.verified_keeper_network_total}
                    sublabel={t("contributors.verifiedKeeperNetworkSublabel")}
                  />
                </li>
              </>
            ) : (
              <li>
                <StatTile
                  label={t("contributors.activeInstitutions")}
                  value={contributors.active_institutions_total}
                  sublabel={t("contributors.activeInstitutionsSublabel", {
                    countries: contributors.countries_represented,
                  })}
                />
              </li>
            )}
            <li>
              <StatTile
                label={t("contributors.recentEdits", {
                  days: contributors.activity_window_days,
                })}
                value={contributors.populations_edited_recent}
                sublabel={t("contributors.recentEditsSublabel")}
              />
            </li>
            <li>
              <StatTile
                label={t("contributors.recentBreedingEvents", {
                  days: contributors.activity_window_days,
                })}
                value={contributors.breeding_events_recent}
                sublabel={t("contributors.recentBreedingEventsSublabel")}
              />
            </li>
            <li>
              <StatTile
                label={t("contributors.recentCensus", {
                  days: contributors.activity_window_days,
                })}
                value={contributors.populations_recent_census}
                sublabel={t("contributors.recentCensusSublabel")}
              />
            </li>
          </ul>
        </section>
      ) : null}

      <section aria-label={t("fieldPrograms.ariaLabel")}>
        <p style={SECTION_EYEBROW_STYLE}>{t("fieldPrograms.eyebrow")}</p>
        <h2 style={SECTION_H2_STYLE}>{t("fieldPrograms.title")}</h2>
        <ul
          role="list"
          style={{
            ...GRID_STYLE,
            listStyle: "none",
            margin: "16px 0 0",
            padding: 0,
          }}
        >
          <li>
            <StatTile
              label={t("fieldPrograms.active")}
              value={field_programs.active}
              href="/field-programs/"
            />
          </li>
          <li>
            <StatTile label={t("fieldPrograms.planned")} value={field_programs.planned} />
          </li>
          <li>
            <StatTile label={t("fieldPrograms.completed")} value={field_programs.completed} />
          </li>
        </ul>
        <p style={{ margin: "12px 0 0", fontSize: 13 }}>
          <Link
            href="/field-programs/"
            style={{
              color: "var(--accent)",
              textDecoration: "underline",
              textUnderlineOffset: 2,
            }}
          >
            {t("fieldPrograms.browseAll")}
          </Link>
        </p>
      </section>
    </main>
  );
}
