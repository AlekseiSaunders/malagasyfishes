import { getToken } from "next-auth/jwt";
import createIntlMiddleware from "next-intl/middleware";
import { NextResponse, type NextRequest } from "next/server";
import { routing } from "./i18n/routing";

/**
 * Composed middleware: next-intl first, then auth/tier guards.
 *
 * **Why composed.** Path-prefix locale routing (`/fr/account`,
 * `/de/dashboard/coordinator`) means the auth gate sees one of five URL
 * shapes per protected route, not one. Running next-intl first means it
 * negotiates the locale (rewrites or redirects), and the auth gate then
 * reads `request.nextUrl.pathname` with the canonical post-rewrite path
 * — which still carries the locale prefix in `as-needed` mode for non-
 * default locales. We strip the locale before the path-prefix checks
 * so `/fr/account` and `/account` go through the same auth logic.
 *
 * **Why preserve the locale on redirects.** When an anonymous user hits
 * `/fr/account`, redirecting to `/login?callbackUrl=/fr/account` would
 * lose the active locale on the login page. We construct
 * `/fr/login?callbackUrl=/fr/account` so the login page renders in the
 * user's chosen language and the post-login destination preserves
 * locale too.
 *
 * Routes:
 *   - `/account/*` (and `/<locale>/account/*`) — needs a session. Gated
 *     only when the auth UX flag is on; if off, route passes through.
 *   - `/dashboard/coordinator/*` (and `/<locale>/dashboard/coordinator/*`)
 *     — needs a session AND `tier >= 3`, UNCONDITIONALLY. The page
 *     surfaces population-level detail at identifiable institutions
 *     (Tier 3+ data per the access model). This gate runs regardless of
 *     `NEXT_PUBLIC_FEATURE_AUTH`. There is no service-token bypass at
 *     the middleware layer — the service token is a server-to-server
 *     fallback inside SSR fetchers, never a browser-route bypass.
 */

const COORDINATOR_MIN_TIER = 3;
const INSTITUTION_MIN_TIER = 2;

const intlMiddleware = createIntlMiddleware(routing);

const NON_DEFAULT_LOCALES = routing.locales.filter(
  (l) => l !== routing.defaultLocale,
);

/**
 * Strip the leading locale segment if present, returning both the
 * locale (or null for default) and the de-localized path. Used so
 * the path-prefix checks below stay locale-agnostic.
 */
function splitLocale(pathname: string): {
  locale: string | null;
  path: string;
} {
  for (const locale of NON_DEFAULT_LOCALES) {
    if (pathname === `/${locale}` || pathname.startsWith(`/${locale}/`)) {
      return {
        locale,
        path: pathname.slice(`/${locale}`.length) || "/",
      };
    }
  }
  return { locale: null, path: pathname };
}

function withLocale(localePath: string, locale: string | null): string {
  if (!locale) return localePath;
  return `/${locale}${localePath === "/" ? "" : localePath}`;
}

function redirectToLogin(
  request: NextRequest,
  originalPath: string,
  locale: string | null,
): NextResponse {
  const url = new URL(withLocale("/login", locale), request.url);
  url.searchParams.set("callbackUrl", originalPath);
  return NextResponse.redirect(url);
}

async function authGate(request: NextRequest): Promise<NextResponse> {
  const fullPath = request.nextUrl.pathname;
  const { locale, path } = splitLocale(fullPath);
  const flagOn = process.env.NEXT_PUBLIC_FEATURE_AUTH === "true";

  const token = await getToken({
    req: request,
    secret: process.env.NEXTAUTH_SECRET,
  });

  if (path.startsWith("/account")) {
    if (!flagOn) {
      return NextResponse.next();
    }
    if (!token) {
      return redirectToLogin(request, fullPath, locale);
    }
    return NextResponse.next();
  }

  if (path.startsWith("/dashboard/coordinator")) {
    const tier = typeof token?.tier === "number" ? token.tier : 0;
    if (tier < COORDINATOR_MIN_TIER) {
      // Flag on → bounce to login (locale-aware). Flag off → bounce
      // home (locale-aware) so we don't expose the hidden login page.
      if (flagOn) {
        return redirectToLogin(request, fullPath, locale);
      }
      const homeUrl = new URL(withLocale("/", locale), request.url);
      return NextResponse.redirect(homeUrl);
    }
    return NextResponse.next();
  }

  if (path.startsWith("/dashboard/institution")) {
    // Gate 13: Tier 2+ AND token present. The institution-membership
    // claim_status check happens server-side on the page itself —
    // middleware can only see the JWT (tier + token) and an extra
    // round trip per request would be wasteful. The page redirects
    // to /account if claim_status != "approved".
    if (!flagOn) {
      const homeUrl = new URL(withLocale("/", locale), request.url);
      return NextResponse.redirect(homeUrl);
    }
    const tier = typeof token?.tier === "number" ? token.tier : 0;
    if (!token || tier < INSTITUTION_MIN_TIER) {
      return redirectToLogin(request, fullPath, locale);
    }
    return NextResponse.next();
  }

  // Gate 15: authenticated population contribute form. Tier 2+ AND
  // token AND the contribute-population feature flag both on (the
  // server-side flag `CONTRIBUTE_POPULATION_ENABLED` is independent —
  // see backend/submissions/views.py). Falls back to redirecting home
  // if either flag is off, so the route is invisible until launch.
  if (path.startsWith("/contribute/population")) {
    const contributeFlagOn =
      process.env.NEXT_PUBLIC_FEATURE_CONTRIBUTE_POPULATION === "true";
    if (!flagOn || !contributeFlagOn) {
      const homeUrl = new URL(withLocale("/", locale), request.url);
      return NextResponse.redirect(homeUrl);
    }
    const tier = typeof token?.tier === "number" ? token.tier : 0;
    if (!token || tier < INSTITUTION_MIN_TIER) {
      return redirectToLogin(request, fullPath, locale);
    }
    return NextResponse.next();
  }

  return NextResponse.next();
}

export async function middleware(request: NextRequest): Promise<NextResponse> {
  // Run next-intl first. If it produced a redirect (locale negotiation,
  // cookie-based default, etc.) honor that and skip the auth gate —
  // the redirected URL will hit middleware again on the next request.
  const intlResponse = intlMiddleware(request);
  if (intlResponse.headers.get("location")) {
    return intlResponse;
  }

  // Otherwise run auth/tier checks. If auth fails, its redirect
  // overrides the i18n pass-through. If it passes, return the i18n
  // response so any internal rewrite headers (e.g., `/account` →
  // `/en/account` for App Router matching) are preserved.
  const authResponse = await authGate(request);
  if (authResponse.headers.get("location")) {
    return authResponse;
  }

  return intlResponse;
}

// Matcher accepts the protected paths with or without a non-default
// locale prefix. The default locale (en) carries no prefix in
// `as-needed` mode, so `/account` and `/fr/account` are the two shapes
// to catch (likewise `/de/account`, `/es/account`).
export const config = {
  matcher: [
    "/((?!api|_next|_vercel|.*\\..*).*)",
  ],
};
