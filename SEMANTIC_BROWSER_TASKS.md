# Rich-text and semantic browser controls — 0.18.0

The browser adapter can replace text in bounded `contenteditable` documents and operate controls declared through standard ARIA roles. The same fixed tools apply across observed applications, including supported open shadow roots and same-origin frames. No website-specific model script is executed.

A `type` action replaces the entire rich editor with literal plain text. The browser editing command receives only escaped text and fixed line-break markup, emits real application input events and supports undo. It does not preserve document formatting. A blank editor's placeholder break is represented as empty text. An editor must have no embedded interactive controls, noneditable widgets, media or scripts, at most 2,000 rendered characters and at most 16,000 markup characters. Readonly, disabled and oversized editors do not advertise typing. Unsupported editor markup is not exported to the planner. Application-specific editor models can still refuse or ignore an edit; the runner must observe the effect and independently verify the saved result.

Custom checkboxes, switches and menu checkboxes with explicit `aria-checked=true/false` advertise `toggle`. Toggle buttons with explicit `aria-pressed=true/false` do the same. The adapter clicks the application's actual handler only when the requested state differs from the observed state. Mixed, missing and unknown toggle states do not advertise automatic toggling. Radio buttons, tabs, menu items and custom options advertise `click`; their selected/checked state remains observable. This provides semantic controls, not universal custom-combobox interpretation. A custom option must actually be visible and observed before it can be clicked.

Names can come from a visible `aria-labelledby` reference in the same DOM root, in addition to existing labels. At most five references are read. Referenced labels and their descendants are excluded from completion evidence even when they appear separately from the control. An unlabeled rich editor uses its ID or tag as a stable fallback rather than its changing draft text.

The current role, checked/selected/pressed/expanded/readonly state, declared controlled-element IDs, editor markup and nested context participate in live guards. The adapter rechecks the control after scrolling/focusing, before applying an effect. Changed markup, toggle state, tab selection or focus-time editability stops stale dispatch. DOM-tool revision `semantic-dom-3` invalidates earlier cached browser recipes. Verified workflows can replay without provider calls only while their live state guards still match.

Editor content and interactive-control labels never certify browser completion. Only exact, nontruncated, independently rendered `page:output` text can do so. Editable descendants, custom options, radio/toggle labels and tab labels are excluded from eligible output. Existing task permissions, action journals, scope checks, cancellation, account profile locks and uncertain-effect recovery still apply.

Use the existing browser task grammar, for example:

```text
Use the browser at "https://your-app.example/drafts" to replace Draft with Hello, enable Confirmed, choose Review and click Apply and verify exactly: "Saved: Hello"
```

This is syntax for your actual application, not a provided public service. A named agent-owned browser session uses the same task format after direct sign-in. External sending or publishing must have been explicitly requested; a DOM success message alone does not certify final delivery.

Six added automatic checks run against an owned application in actual Chromium. They cover a Unicode/multiline rich draft, switch and tab sequence followed by a real HTTP submission and exact output verification; literal script-looking text and empty replacement; readonly/widget/media/oversized protection; idempotent toggles and actual radio/menu/option handlers; changed markup/state/focus rejection; and queued provider-free replay. The existing nineteen checks continue to cover authentication, nested native forms, privacy, navigation, scope, interruption and bounded observation. These deterministic fixture tests establish named execution behavior, not model planning quality or universal mastery of websites/native apps. See VALIDATION_018.md for completed platform results.
