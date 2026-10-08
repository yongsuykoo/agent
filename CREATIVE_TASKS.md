# Photoshop logo tasks

Version 0.9.0 adds native logo creation to the personal task engine. It discovers the installed Photoshop edition, observes fonts, plans a composition, creates a fresh layered document, exports PSD/PNG and checks the files. It needs no user demonstration. It implements documented Adobe operations, without claiming every feature or proprietary source code is understood.

In `windows\Start.cmd`, use **Automatic — choose app from command** and autonomous submitted tasks. Example:

> Design a 1024x1024 transparent logo in Photoshop for brand "Papa Print" using #0066CC and #FF8800. Use a geometric printer symbol and a readable wordmark.

Chat and transcribed voice use the same path. A submitted task authorizes its fresh document and exports; supervised mode retains its approval step. Existing documents are not edited or overwritten. Exports go to `%LOCALAPPDATA%\AppAgent\outputs\logo-<unique-id>\logo.psd` and `logo.png`; the log reports paths. Evidence goes to `objective-sessions.jsonl` and separate versioned artifact recipes. **Machine knowledge** distinguishes artifact workflows from accessibility-control workflows.

The model supplies only bounded dimensions, polygon shapes, literal text, colors and installed PostScript fonts. A fixed reviewed ExtendScript runs through the documented Windows COM interface. Model-supplied code, commands, paths and extra fields are rejected. Native version, installation path and selected-window process must match. Duplicate entries for one installation are consolidated; ambiguous editions stop before document creation.

Supported: 32–4096 pixel RGB canvases, at most twenty raster polygon/editable text layers. Explicit dimensions, quoted brand text, hexadecimal colors, transparency and icon-only constraints are preserved. Verification checks native text/fonts/bounds; PSD structure and composite encoding; PNG checksums, decoded dimensions, visible pixels, palette and transparency. `artifacts_verified` does not certify artistic quality, complete semantic satisfaction of a complex brief, or independent editing of exported PSD text. Vector paths/SVG, photos, effects, other Photoshop tasks and other design programs need additional operations and acceptance.

Failures retain evidence and allow one composition repair; malformed plans allow up to three corrections. Exact-brief recipes replay without planning calls when installation generation/native identity match. Every replay creates and verifies new files. Installation changes invalidate recipes. New/repaired plans incur provider charges, without a daily submitted-task cap.

STOP checks run before/after COM calls and between layers/exports using a local cancellation marker. One Photoshop operation cannot be interrupted instantly. Script failure closes only the newly created document without saving; ruler/dialog preferences are restored. Partial failed files remain in their unique folder as evidence. Successful documents remain open. Background discovery/study does not invoke this adapter automatically.

The cloud companion's remote task endpoint still operates locally granted accessibility controls. It cannot invoke native logo creation or bypass those grants. Launch the updated standalone interface for this feature. Signed backend updates retain compatible companion connections, without replacing an already running standalone UI.

Validation: **276 cloud checks** and **14 executions of the actual trusted script against a simulated Adobe DOM**, plus the full suite from an installed wheel in a fresh extracted kit. Checks cover corruption, PNG filters, literal-string injection, binding mismatches, cancellation, failed completion claims, bounded repair, recipe reuse and invalidation. COM/Photoshop behavior is simulated; actual Windows Photoshop/CS2 rendering, fonts, exports and visual quality remain unverified. Earlier Calculator/Notepad evidence does not establish Photoshop acceptance.

Requests to edit an existing logo, export to an external destination, or combine creation with email/upload/publication are rejected rather than silently dropping those requirements. The general task engine needs additional native artifact handoffs to support these compound workflows.

Adobe references: [scripting overview](https://helpx.adobe.com/photoshop/using/scripting.html), [JavaScript reference](https://github.com/Adobe-CEP/CEP-Resources/blob/master/Documentation/Product%20specific%20Documentation/Photoshop%20Scripting/photoshop-javascript-ref-2020.pdf), [Windows COM/VBScript reference](https://github.com/Adobe-CEP/CEP-Resources/blob/master/Documentation/Product%20specific%20Documentation/Photoshop%20Scripting/photoshop-vbs-ref-2020.pdf).
