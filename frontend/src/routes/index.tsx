import { createFileRoute, redirect } from "@tanstack/react-router";

/**
 * The old "Companies" network overview lived here. The product is deployed
 * per pair and a company sees only its own pairs (PRD 2a, R21), so the home
 * screen is /pairs.
 */
export const Route = createFileRoute("/")({
  beforeLoad: () => {
    throw redirect({ to: "/pairs" });
  },
});
