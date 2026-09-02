# Responsive and accessibility contract

## Responsive behavior

Declare behavior at narrow (~390), intermediate (1024/768) and wide (1440)
viewports. For each region state whether it stacks, changes columns, wraps,
scrolls, summarizes, reorders or stays visible. Preserve the primary task,
required content, status and error recovery. Do not hide data or squeeze a
desktop table until it becomes unusable.

Check long headings, labels, error copy, table columns, controls, focus rings,
sticky regions, zoom/reflow and touch targets at the intermediate width. A
mobile layout should support one-handed reach and avoid keyboard occlusion;
gestures never replace a visible equivalent control.

## Accessibility baseline

Use semantic landmarks, one clear `h1`, logical heading order, native form
controls, programmatic labels, accessible names, descriptive links, and text
or shape cues alongside color. Errors and status changes must be perceivable
through text and an appropriate live region. Focus must be visible, not
removed by an outline reset. Respect `prefers-reduced-motion`.

Automated accessibility is a filter. Pair it with keyboard traversal,
focus/state observation, contrast checks, touch-target measurement and a
representative manual assistive-technology path when available. Record the
exact checks and the unavailable ones; a static scan is not a certification.
