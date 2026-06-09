import { Link } from "@/i18n/routing";
import { getTranslations } from "next-intl/server";
import type { CSSProperties, ReactNode } from "react";
import type { Metadata } from "next";

import type { Locale } from "@/i18n/routing";
import { fetchDashboard } from "@/lib/dashboard";
import { buildAlternates } from "@/lib/seo";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: Locale }>;
}): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "about.page" });
  return {
    title: t("metaTitle"),
    description: t("metaDescription"),
    alternates: buildAlternates("/about", locale),
  };
}

export const revalidate = 3600;

const REPO_URL = "https://github.com/AlekseiSaunders/malagasyfishes";
const ADMIN_URL = "https://api.malagasyfishes.org/admin/";

const EYEBROW_STYLE: CSSProperties = {
  margin: 0,
  fontFamily: "var(--sans)",
  fontSize: 11,
  fontWeight: 700,
  letterSpacing: "0.18em",
  textTransform: "uppercase",
  color: "var(--ink-3)",
};

const H2_STYLE: CSSProperties = {
  margin: 0,
  fontFamily: "var(--serif)",
  fontSize: 24,
  fontWeight: 600,
  letterSpacing: "-0.01em",
  color: "var(--ink)",
  lineHeight: 1.2,
};

const BODY_STYLE: CSSProperties = {
  margin: 0,
  fontSize: 15,
  lineHeight: 1.65,
  color: "var(--ink-2)",
};

const LINK_STYLE: CSSProperties = {
  color: "var(--accent-2)",
  textDecoration: "none",
  borderBottom:
    "1px solid color-mix(in oklab, var(--accent-2) 35%, transparent)",
};

function Section({
  eyebrow,
  title,
  children,
}: {
  eyebrow: string;
  title: string;
  children: ReactNode;
}) {
  return (
    <section style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <p style={EYEBROW_STYLE}>{eyebrow}</p>
      <h2 style={H2_STYLE}>{title}</h2>
      <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
        {children}
      </div>
    </section>
  );
}

export default async function AboutPage() {
  const [dashboard, t] = await Promise.all([
    fetchDashboard(),
    getTranslations("about.page"),
  ]);
  const speciesTotal = dashboard?.species_counts.total;
  const speciesTotalText =
    speciesTotal !== undefined && speciesTotal !== null
      ? String(speciesTotal)
      : t("missionFallbackTotal");

  return (
    <>
      <section
        style={{
          backgroundColor: "var(--bg-sunken)",
          borderBottom: "1px solid var(--rule)",
        }}
      >
        <div
          style={{
            maxWidth: 880,
            margin: "0 auto",
            padding: "64px 32px 48px",
            display: "flex",
            flexDirection: "column",
            gap: 16,
          }}
        >
          <p style={EYEBROW_STYLE}>{t("heroEyebrow")}</p>
          <h1
            style={{
              margin: 0,
              fontFamily: "var(--serif)",
              fontSize: 40,
              fontWeight: 600,
              letterSpacing: "-0.015em",
              color: "var(--ink)",
              lineHeight: 1.15,
            }}
          >
            {t("heroTitle")}
          </h1>
          <p
            style={{
              margin: 0,
              fontSize: 17,
              lineHeight: 1.55,
              color: "var(--ink-2)",
              maxWidth: 720,
            }}
          >
            {t("heroSubtitle")}
          </p>
        </div>
      </section>

      <main
        style={{
          maxWidth: 880,
          margin: "0 auto",
          padding: "56px 32px 96px",
          display: "flex",
          flexDirection: "column",
          gap: 48,
        }}
      >
        <Section eyebrow={t("missionEyebrow")} title={t("missionTitle")}>
          <p style={BODY_STYLE}>
            {t("missionPara1", { speciesTotal: speciesTotalText })}
          </p>
          <p style={BODY_STYLE}>{t("missionPara2")}</p>
        </Section>

        <Section eyebrow={t("scopeEyebrow")} title={t("scopeTitle")}>
          <p style={BODY_STYLE}>{t("scopePara1")}</p>
          <p style={BODY_STYLE}>{t("scopePara2")}</p>
        </Section>

        <Section eyebrow={t("provenanceEyebrow")} title={t("provenanceTitle")}>
          <p style={BODY_STYLE}>{t("provenancePara1")}</p>
          <p style={BODY_STYLE}>
            {t.rich("dwcLine", {
              dwcLink: (chunks) => (
                <a
                  href="/api/v1/dwc/archive.zip"
                  style={LINK_STYLE}
                  download="mffcp-occurrences.zip"
                >
                  {chunks}
                </a>
              ),
            })}
          </p>
          <p style={BODY_STYLE}>
            {t.rich("provenancePara2", {
              dataLink: (chunks) => (
                <Link href="/about/data/" style={LINK_STYLE}>
                  {chunks}
                </Link>
              ),
            })}
          </p>
          <p style={BODY_STYLE}>
            {t.rich("provenancePara3", {
              glossaryLink: (chunks) => (
                <Link href="/about/glossary/" style={LINK_STYLE}>
                  {chunks}
                </Link>
              ),
            })}
          </p>
        </Section>

        <Section eyebrow={t("stewardshipEyebrow")} title={t("stewardshipTitle")}>
          <p style={BODY_STYLE}>
            {t.rich("stewardshipBody", {
              repoLink: (chunks) => (
                <a
                  href={REPO_URL}
                  style={LINK_STYLE}
                  target="_blank"
                  rel="noreferrer"
                >
                  {chunks}
                </a>
              ),
            })}
          </p>
        </Section>

        <Section eyebrow={t("referencesEyebrow")} title={t("referencesTitle")}>
          <ul
            style={{
              margin: 0,
              paddingLeft: 20,
              display: "flex",
              flexDirection: "column",
              gap: 10,
              ...BODY_STYLE,
            }}
          >
            <li>
              {t("citation1Prefix")}
              <em>{t("citation1Journal")}</em>
              {t("citation1Suffix")}
              <a
                href="https://doi.org/10.1002/zoo.21661"
                style={LINK_STYLE}
                target="_blank"
                rel="noreferrer"
              >
                {t("citation1DoiText")}
              </a>
              {t("citation1End")}
            </li>
            <li>{t("citation2")}</li>
            <li>{t("citation3")}</li>
            <li>{t("citation4")}</li>
          </ul>
        </Section>

        <p
          style={{
            marginTop: 24,
            textAlign: "right",
            fontSize: 12,
            color: "var(--ink-3)",
          }}
        >
          <a href={ADMIN_URL} target="_blank" rel="noopener noreferrer" style={{ color: "inherit", textDecoration: "none" }}>
            {t("staffSignIn")}
          </a>
        </p>
      </main>
    </>
  );
}
