import { getTranslations } from "next-intl/server";
import { Link } from "@/i18n/routing";

const REPO_URL = "https://github.com/AlekseiSaunders/malagasyfishes";

type FooterLink = {
  /** i18n key relative to footer.<columnLinks> */
  labelKey: string;
  href: string;
  external?: boolean;
};

type FooterColumn = {
  /** i18n key under footer.* (e.g. "platformHeading") */
  headingKey: string;
  /** i18n namespace (relative to "footer") that holds this column's link labels */
  linksNamespace: string;
  links: FooterLink[];
};

// External-link labels (IUCN Red List, FishBase, etc.) are proper nouns
// and stay untranslated — they're brand names of partner organizations.
// Internal-link labels live in the footer.<linksNamespace> table.
const COLUMNS: FooterColumn[] = [
  {
    headingKey: "platformHeading",
    linksNamespace: "platformLinks",
    links: [
      { labelKey: "speciesDirectory", href: "/species/" },
      { labelKey: "distributionMap", href: "/map/" },
      { labelKey: "conservationDashboard", href: "/dashboard/" },
    ],
  },
  {
    headingKey: "dataHeading",
    linksNamespace: "", // proper-noun links below
    links: [],
  },
  {
    headingKey: "aboutHeading",
    linksNamespace: "aboutLinks",
    links: [
      { labelKey: "aboutThePlatform", href: "/about/" },
      { labelKey: "dataSources", href: "/about/data/" },
      { labelKey: "glossary", href: "/about/glossary/" },
    ],
  },
  {
    headingKey: "contributeHeading",
    linksNamespace: "contributeLinks",
    links: [
      { labelKey: "husbandryReports", href: "/contribute/husbandry/" },
      { labelKey: "github", href: REPO_URL, external: true },
    ],
  },
];

const PROPER_NOUN_DATA_LINKS = [
  { label: "IUCN Red List", href: "https://www.iucnredlist.org/" },
  { label: "FishBase", href: "https://www.fishbase.se/" },
  { label: "GBIF", href: "https://www.gbif.org/" },
  { label: "CARES Preservation", href: "https://carespreservation.com/" },
];

const linkStyle = {
  display: "inline-flex",
  alignItems: "center",
  minHeight: 32,
  color: "var(--ink-2)",
  textDecoration: "none",
  transition: "color 120ms ease",
} as const;

export default async function SiteFooter() {
  const t = await getTranslations("footer");

  return (
    <footer
      style={{
        marginTop: 96,
        borderTop: "1px solid var(--rule)",
        backgroundColor: "var(--bg-sunken)",
      }}
    >
      <div
        style={{
          margin: "0 auto",
          maxWidth: 1152,
          padding: "48px 28px 40px",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 12,
            marginBottom: 32,
          }}
        >
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src="/logo.svg"
            alt=""
            width={21}
            height={32}
            style={{ height: 32, width: "auto", display: "block" }}
          />
          <span
            style={{
              fontFamily: "var(--serif)",
              fontSize: 13,
              fontWeight: 500,
              letterSpacing: "-0.01em",
              color: "var(--ink)",
            }}
          >
            Malagasy Freshwater Fishes
          </span>
        </div>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
            gap: 40,
          }}
        >
          {COLUMNS.map((col) => (
            <div key={col.headingKey}>
              <p className="eyebrow" style={{ marginBottom: 12 }}>
                {t(col.headingKey)}
              </p>
              <ul
                style={{
                  listStyle: "none",
                  margin: 0,
                  padding: 0,
                  display: "flex",
                  flexDirection: "column",
                  gap: 8,
                  fontSize: 13,
                }}
              >
                {col.linksNamespace === ""
                  ? PROPER_NOUN_DATA_LINKS.map((link) => (
                      <li key={link.href}>
                        <a
                          href={link.href}
                          target="_blank"
                          rel="noreferrer"
                          style={linkStyle}
                        >
                          {link.label}
                        </a>
                      </li>
                    ))
                  : col.links.map((link) => (
                      <li key={link.href}>
                        {link.external ? (
                          <a
                            href={link.href}
                            target="_blank"
                            rel="noreferrer"
                            style={linkStyle}
                          >
                            {t(`${col.linksNamespace}.${link.labelKey}`)}
                          </a>
                        ) : (
                          <Link href={link.href} style={linkStyle}>
                            {t(`${col.linksNamespace}.${link.labelKey}`)}
                          </Link>
                        )}
                      </li>
                    ))}
              </ul>
            </div>
          ))}
        </div>
        <div
          style={{
            marginTop: 40,
            display: "flex",
            flexWrap: "wrap",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 8,
            borderTop: "1px solid var(--rule)",
            paddingTop: 24,
            fontSize: 12,
            color: "var(--ink-3)",
          }}
        >
          <p style={{ margin: 0 }}>{t("license")}</p>
          <p style={{ margin: 0, textAlign: "right" }}>{t("dataNote")}</p>
        </div>
      </div>
    </footer>
  );
}
