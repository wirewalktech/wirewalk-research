# Wirewalk Research

Public website: https://research.wirewalk.com

Research-focused HPC, GPU performance, scientific computing, and AI engineering. Jekyll site deployed by GitHub Pages from `main`, repository root. DNS CNAME: `research.wirewalk.com` → `wirewalktech.github.io`.

## Source and pricing

Shared layout: `_layouts/default.html`. CSS and client scripts: `assets/`. Each page has an explicit permalink; keep `_config.yml` baseurl empty for the custom domain.

The payment catalog is authoritative in the **private** `wirewalktech/wirewalk-orders-worker` repository, `src/research-catalog.js`. `_data/services.json` is its public display snapshot. Regenerate after changing a service:

```sh
node tools/sync-catalog.mjs /absolute/path/to/wirewalk-orders-worker/src/catalog.js
```

Four fixed-price services accept Stripe Checkout. Three bespoke offerings show planning minimums and require a quote. No automatic subscription, prepayment discount, or ACH discount applies to Research services. The browser sends a SKU, never an amount. Payment return paths are under this site's `/order/`.

`/contact/` submits to the existing Wirewalk portal inquiry endpoint. It saves the inquiry before attempting notification. `/thanks/` does not establish email delivery. The Stripe status page reads the provider-backed session endpoint and distinguishes paid, unpaid, test, unknown, and other-practice sessions.

## Local build

Use a Ruby installation with Jekyll and jekyll-sitemap available. In the existing Wirewalk environment, the main site's Gemfile can be reused with `BUNDLE_GEMFILE`.

```sh
bundle exec jekyll serve --port 8770
```

## Operations

Read `wirewalktech/wirewalk-web-ops/README.md` and `AGENTS.md` before edits or deployment. That private repository records claims, deployment evidence, verification tools, pricing assumptions, and operational limitations. No credentials or client information belong in this public site repository.

Contact: sales@wirewalk.com · 516-269-1517.
