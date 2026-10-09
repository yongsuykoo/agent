# Embedded forms and web components — 0.17.0

Browser tasks can now read and operate standard controls inside open shadow roots and same-origin embedded documents, as well as the main page. This expands the DOM adapter to web-component applications and embedded forms without creating a separate script for each site. It still observes one owned browser tab and verifies actual rendered output.

## Dropdown choices

The observer advertises a single-choice native `<select>` as a ComboBox with bounded options: exact value, displayed label, enabled state and current selection. The planner's `select` action supplies `text` equal to one enabled option's exact value. The adapter sets the native value and emits input/change events so the application receives the change. Labels, guessed values, disabled options and duplicate values cannot silently select another choice.

For example, a page can display **Express shipping** with the internal value `express`. A goal can say:

```text
Use the browser at "https://your-app.example/form" to enter Hello in Message, choose Express shipping in Delivery, confirm, and click Apply and verify exactly: "Saved: Hello / express"
```

This is syntax, not a provided service. Use your actual public HTTPS URL and the result your page renders. [Named account sessions](BROWSER_SESSIONS.md) use the same controls and task grammar after direct sign-in. Selecting a value alone never proves the final task succeeded.

Dropdowns with multiple selection, more than 80 options, or oversized option values/labels do not advertise selection. Individual duplicate values are ambiguous and rejected, even if their labels differ. A disabled optgroup also disables its options. Custom JavaScript dropdowns that do not use native select elements retain their observed button/link behavior; this release does not add a universal custom-menu tool.

## Nested context and stale targets

The fixed observer walks ordinary DOM elements, open shadow roots and same-origin HTTP(S) iframe documents. Controls and result elements carry their root/frame path and document URL. A frame must remain connected to the original tab and own the observed document. Closed shadow roots, cross-origin or sandbox-isolated frames, and srcdoc/about:blank documents are unavailable in this route. No browser security boundary is disabled to expose them.

Observation waits up to five seconds for supported visible embedded documents to finish loading before returning their controls. Inaccessible frames do not hold up planning. A frame that does not become ready stops observation with a timeout; the adapter does not assume its controls are absent.

Before an action, the adapter checks live visibility, composed ancestor inert/disabled state, element identity/value, option metadata and the complete nested context. A replaced element, moved component, changed frame URL, detached frame, or changed option list stops dispatch. Typing and selecting use the element's own document's native setter and composed input/change events; they work inside the observed components without model-supplied code.

Exact output verification works inside supported nested contexts. A hidden ancestor, input/select value, button label, body substring, truncated result or inaccessible frame cannot certify completion. Saved recipes bind to the DOM-tool revision as well as browser/session revisions and live controls. Repeats can use local replay with zero provider calls only while those guards remain valid. Action journaling and uncertain-submit recovery remain in effect.

## Bounded inspection

A snapshot inspects at most 8,000 elements across 64 document/shadow roots, with at most 16 nested root levels, 200 interactive controls and 200 eligible output elements. Visibility/context checks also cap ancestor depth at 64. `coverage` reports inspected element/root counts, unavailable frames and reached limits. Deep or oversized pages can therefore leave controls unobserved; missing coverage is not proof that the app lacks those capabilities. The strong node map retains only the current bounded observed controls; prior nodes use weak identity references.

Transport and text limits still apply. URLs are bounded to 4,096 characters, dropdown values to 2,000 and option labels to 300. Long/deep contexts can exceed the existing transport limit and stop observation safely. There is no new arbitrary JavaScript, password/OTP, upload/download, closed-root, cross-origin-frame, canvas or screenshot automation action.

## Automatic testing

`windows\TestBrowser.cmd` now runs nineteen checks automatically with disposable data and no provider key. Six new real-Chromium checks exercise a shadow root containing an iframe containing another shadow root: four actions produce one actual HTTP submission, and the nested rendered output is independently verified. Other checks reject unsafe selections and stale targets, preserve nested password/privacy boundaries, replay the queued task without provider access, and enforce DOM/node-map limits.

The fixture uses a reviewed deterministic planner. These checks establish execution and recovery behavior on the owned test application. All nineteen pass on actual hosted Windows with Python 3.11 and 3.14, retaining the browser sandbox. See [release validation](VALIDATION_017.md). They do not establish arbitrary-site planning quality, other native Windows app workflows, external account delivery, voice reliability or universal understanding of installed and future applications.
