import { apiFetch } from "./api";

export interface DashboardResponse {
  species_counts: {
    total: number;
    described: number;
    undescribed: number;
    by_iucn_status: Record<string, number>;
  };
  ex_situ_coverage: {
    threatened_species_total: number;
    threatened_species_with_captive_population: number;
    /**
     * Gate 15 Q1 — funder-facing "captive coverage" metric. Threatened
     * species with ≥1 ExSituPopulation in `breeding_status='breeding'`.
     * Optional on the type so older deployed backends without the new
     * field don't break rendering; the UI falls back to the legacy
     * `threatened_species_with_captive_population` when missing.
     */
    threatened_species_with_breeding_population?: number;
    threatened_species_without_captive_population: number;
    institutions_active: number;
    total_populations_tracked: number;
  };
  field_programs: {
    active: number;
    planned: number;
    completed: number;
  };
  // Coordination summary — added in PR #118 (v2 dashboard payload). The
  // only deployed backend (Hetzner staging at api.malagasyfishes.org)
  // serves it unconditionally as of 2026-04-28; verified via curl. If a
  // future deployment topology adds a backend that's behind on the
  // payload version, restore the optional `?` and add the zero-fallback
  // back to /dashboard/page.tsx.
  coordination: {
    active_programs_total: number;
    active_programs_by_type: Record<string, number>;
    transfer_window_days: number;
    transfers_in_flight: number;
    transfers_recent_completed: number;
  };
  // Contributors block — added with the public dashboard "platform contributors"
  // panel. Optional on the type so a backend running an older v2 payload
  // still renders the rest of the page; the panel itself short-circuits to
  // null when the field is missing.
  contributors?: {
    active_institutions_total: number;
    by_type: Record<string, number>;
    /**
     * Gate 15 Q1 split — equal-weight buckets. `institutional_contributors_total`
     * is the non-keeper count (zoos / aquariums / research orgs / hobbyist
     * programs / NGOs / government). `verified_keeper_network_total` is
     * the hobbyist_keeper count. Optional on the type so older backends
     * still render; the UI falls back to deriving from `by_type` if missing.
     */
    institutional_contributors_total?: number;
    verified_keeper_network_total?: number;
    countries_represented: number;
    activity_window_days: number;
    breeding_events_recent: number;
    populations_edited_recent: number;
    populations_recent_census: number;
  };
  last_updated: string;
  last_sync_at: string | null;
}

export async function fetchDashboard(): Promise<DashboardResponse | null> {
  try {
    return await apiFetch<DashboardResponse>("/api/v1/dashboard/");
  } catch {
    return null;
  }
}
