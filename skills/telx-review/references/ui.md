# UI angle

## Why this angle matters here

The visual layer is Tailwind v4 with a custom palette in `src/app/globals.css` that overrides Tailwind's own gray, blue, and green scales, one dark navy theme, Typekit fonts, and class names built by string concatenation with no variant or merge helper. That combination makes three kinds of defect common: classes that do nothing (typos, v3 syntax, tokens that do not exist), colors that fail contrast because a "standard" Tailwind shade is now a brand color, and controls built from `div`s that keyboard and screen reader users cannot operate. On a site whose primary action is signing a transaction, a modal without focus management or a button without a name is not cosmetic.

## File map

Read first:

- `src/app/globals.css`: the `@theme` tokens (gray, tblue, blue, burple, and green scales 100 to 1300 that overwrite Tailwind's 100 to 900; `white-10` to `white-100`; `primary`; `status-*`; gradients stored as color tokens), the unlayered helper classes (`.bg-ocean-gradient` and friends, `.custom-search-css`, `.md-rich-text`), the Typekit `@font-face` rules (`font-display: auto`, no fallback family), leftover `--font-sans`, `--font-mono`, and `--color-background` variables, and unused `.wallet-*` classes.
- Primitives: `src/components/common/Button.tsx` (variants by string join, an `<a>` without href inside a `<button>`, no `type`, a "disabled" link that stays focusable; imported by 17 files), `Modal.tsx` (no dialog role, focus trap, Escape, or scroll lock; a div as the close control), `Skrim.tsx` with `src/components/providers/SkrimProvider.tsx`, `LoadingWrapper.tsx`, `LoadingAnimationCircle.tsx`, `LabelValueRow.tsx` (click-only tooltips, one document-level listener per instance), `ReturnAsset.tsx` and `src/components/pool/PoolWeightChip.tsx` (two identical token icon tables), `ReturnLogo.tsx`, `ReturnStatus.tsx`, `ChainLogo.tsx`, `ProtocolVersionLogo.tsx`.
- Layout: `src/components/layout/Header.tsx`, `HeaderMenuItems.tsx`, `HeaderMenuLink.tsx`, `SearchMenuLink.tsx`, `MobileMenuDrawer.tsx`, `MobileMenuDrawerToggle.tsx`, `CustomConnectButton.tsx`, `Footer.tsx`, `AppLayout.tsx`, `Layout.tsx` (dead), `src/app/layout.tsx`.
- Lists and tables: `src/components/pool/PoolSnapshot.tsx` with `PoolSnapshotLabels.tsx`, `src/components/archive/ArchiveCard.tsx` with `ArchiveSnapshotLabels.tsx` (grid templates duplicated between header and row; `overflow-x-auto min-w-5xl`), `src/components/pools/PoolsMain.tsx`, `PoolTabs.tsx`, `src/components/search/SearchPoolsCards.tsx` (rows without a header), `src/components/home/PoolsHomePage.tsx`.
- Pool page: `src/app/pool/[poolID]/PoolDetails.tsx`, `src/components/common/Label*Row.tsx`, `PoolHeading.tsx`, `src/components/chart/ChartTabs.tsx` and `PoolChart.tsx` (both charts mounted, an unlabeled select, `font-[500px]`), `src/components/common/UserPositions.tsx`, `PositionCard.tsx`, and `src/components/pool/PositionInputCard.tsx` (a stray quote in a className, white text on `bg-blue-600`, `ReturnStatus` given values it does not handle), `LabelPositionRow.tsx` (chevron direction, pill tabs).
- Other pages: `src/app/HomePage.tsx` and `src/components/home/*.tsx` (a second h1; `expandedCard` never read), `src/app/search/SearchPage.tsx` (an unlabeled input with its outline removed; a results component defined inside render), `src/components/search/CardSearchAbout.tsx`, `src/components/about/*.tsx`, `src/app/about/[slug]/page.tsx`, `src/components/generalized/*.tsx` and `WeightedAsset.tsx` (legacy light-theme components).
- Feedback: `src/components/toast/Toast.tsx` (`text-primary` against the container's theme), `src/app/Providers.tsx` (the ToastContainer theme).
- The model for new code: `src/components/common/LabelTokenAddressesRow.tsx` (typed props, `type="button"`, `aria-label`, `focus-visible`, `useId`, list semantics). Its one gap is an `aria-live` region for "Copied".

## Checklist

### Tokens and classes

- Every class resolves. Watch for typos that split a class (`bac kgrounds`, `bg-oce an-gradient`, `items-centermd:text-center`), v3 syntax beside v4 (`!w-full` and `w-full!`, `bg-gradient-to-r` and `bg-linear-to-r`), and classes that do not exist (`text-tblue`, `font-base`, `border-lg`, `shadow-blackz`, `font-[500px]`). The build does not catch these; only reading does.
- Gradient tokens are colors, so `hover:bg-ocean-gradient` sets an invalid `background-color` and the hover never appears. The helper classes are unlayered plain CSS, so they beat utilities and cannot take variants. Recommend `@utility` for helpers and `--background-image-*` tokens for gradients.
- Palette overrides: `blue-600`, `green-800`, and the gray scale are brand values here, not Tailwind's. A class that assumes the default scale, especially for contrast, is suspect, and the 50 and 950 shades are still Tailwind's, so the scale is discontinuous.
- One-off hex values (`bg-[#0E0E3E]/20`, `from-[#19245d]`, `bg-[#4967FF]`) where a token exists. Report the pattern once with the list.
- Two classes that conflict on one element (`bg-theme-gradient bg-ocean-gradient`, `fixed absolute`); stylesheet order decides which wins.
- Callers overriding `Button` with `!` classes is the symptom of string-joined variants. `cx()` (clsx plus tailwind-merge) exists in `src/lib/utils.ts` and the primitives do not use it.

### Component reuse and drift

- The same table grid template in two files per table, the same token icon table in two files, the same pill-tab markup in four places, three overlay systems (Modal, Skrim, RainbowKit). Report each as one finding with every location and the shared component to extract.
- Hand-rolled buttons where `Button` exists (`CustomConnectButton`), `div` or `p` inside `<button>`, an `<a>` inside an `<a>` (`CardGeneralized`).
- Lookup components (`Return*`) render nothing for unknown keys, including status values the caller passes ("Subscribed"), and an unknown ticker shows no icon and no fallback.
- Dead files and dead state: `Layout.tsx`, `.wallet-open`, `expandedCard`.

### Accessibility

- Interactive elements are the right element: `button` for actions, `a` with `href` for navigation. Divs with `onClick` (menu toggle, drawer close, modal close, archive rows, tooltips) fail keyboard users.
- Names: icon-only controls carry `aria-label` (the search link, the about nav toggle, header and footer icons, the position chevron). Image `alt` is meaningful, or empty when the same text sits beside it.
- Dialogs: `role="dialog"`, `aria-modal`, a label, focus moved in and restored on close, Escape to close, background scroll locked. `Modal.tsx` and the Skrim drawer have none of these.
- Tabs and tooltips: `tablist`, `tab`, and `aria-selected`, or a plain set of links; tooltips reachable by keyboard with `aria-describedby`. Click-only tooltips are a finding.
- Forms: every input has a label (the search input, the chart days select); focus outlines are replaced, never removed; search submits from a form, not only on Enter.
- Structure: one `h1` per page (home has two, `/pools` has none, about puts an h4 before the h1), headings in order and not used as visual labels, `li` inside `ul`, `aria-current` on the active nav link, `fieldset` and legend for radio groups (`UserPositions` does this right).
- Live feedback: "Copied", toasts, and status messages announce through `aria-live` or `role="status"`.
- Contrast: compute with the brand hex values. White on `blue-600` (#70C6FF) is about 1.9:1, white on `green-800` (#03B591) about 2.6:1, `text-primary` (#C9CFED) on a light toast about 1.5:1. Report the ratio and the token to use instead.
- Motion: `hover:scale-105` and drawer slides with no `prefers-reduced-motion` guard. One finding, Low.

### Responsiveness and layout

- Tables are 1024px-wide grids that scroll sideways on phones, with no card layout below `lg`. One finding, Medium when the primary action (subscribe, claim) sits inside the scrolled region.
- Separate mobile and desktop trees both mounted (`PoolChart`, `PoolSnapshotGeneralized`, the `PoolWeightChip` images) instead of responsive classes; the hidden chart measures zero width.
- `break-all` on numeric values splits digits. Long addresses use `break-all` or `overflow-wrap: anywhere` consistently.
- The JavaScript `width < 1024` check duplicates the CSS `lg` breakpoint. Drift between them shows two navs or none.

### Typography and fonts

- `font-display: auto` with no fallback family means invisible text until Typekit loads. `next/font`, or `font-display: swap` with a system fallback, is the fix.
- Heading and label sizes come from a small set of classes. Note deviations only when they break the hierarchy.

### Consistency of formatted values

- Currency in three styles (`"$" + stringNumbertoUSD`, `formatNumberToCurrencyString`, `Intl.NumberFormat` beside `toLocaleString` in one chart), missing values as "Unavailable", "N/A", or blank, `PoolStaked` without the "$" its siblings have, raw position amounts. One finding per pattern, naming the helper to standardize on.

## Severity examples

- High: a modal or drawer that traps or loses focus so a keyboard user cannot complete or cancel a transaction; a primary action rendered as a `div` with `onClick`.
- Medium: contrast under 3:1 on interactive text; controls without names on a transaction flow; the mobile table that hides the primary action; hover states that never render because the class is invalid.
- Low: class typos and dead classes; duplicated grid templates and icon tables; inconsistent formatting; missing reduced-motion handling.
- Informational: token naming, leftover create-next-app variables, dead CSS.

## Do not flag

- The single dark theme and the absence of `dark:` variants.
- Tailwind v4's CSS-first configuration itself, or the absence of a `tailwind.config.ts`.
- Tremor Raw copies existing.
- Flows, states, and copy. Those belong to the UX angle. Numbers being wrong belongs to data-correctness.
