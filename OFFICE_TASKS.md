# Verified Office creation — 0.12.0

The agent can create a new Excel workbook or Word document from a chat or voice task. A deterministic tool broker selects these native tools for supported creation goals and retains the general desktop workflow for other goals. Photoshop remains a separate native creative tool. The broker respects the selected app, excludes compound delivery/editing goals from Office creation, and refuses to choose arbitrarily between different installed Office editions. Duplicate discovery records of the same executable are coalesced.

Examples:

- `Create an Excel workbook listing Paper 12.5 and Ink 7.5 with a total and a column chart titled Costs.`
- `Create an Excel workbook with A1 = 12 and A2 = 8 and their total in A3.`
- `Write a Word document titled "Project brief" with these paragraphs: Our objective is a blue logo. The deadline is Friday. Include a table of deliverables and owners using only those supplied facts.`

The Office tool creates fresh files under the agent's `outputs/office-<unique id>` directory. It uses the installed Microsoft desktop apps and documented COM interfaces. Web Office and other spreadsheet editors can still use the general desktop route; they do not receive Microsoft COM support automatically. The first task needs model access for a declarative plan. Repeating the same successfully verified task on an unchanged installation reuses its recipe with no planning API call, while creating and checking a fresh file. There is no new daily spending cap; provider requests still incur the provider's normal charges.

Excel supports one to three worksheets, up to 1,500 declared cells in A1:Z200, literal text/numbers/blanks, column number formats, and one column or line chart per sheet. Formulas support same-sheet references, basic arithmetic, and `SUM`, `AVERAGE`, `MIN`, `MAX` and `COUNT`. A small AST interpreter independently calculates these results without executing formula code. Links, macros, cross-sheet formulas and arbitrary functions are excluded. Cell assignment happens in a batch, followed by fixed formula/chart operations and a macro-free XLSX save.

Word supports a title, plain paragraphs and an optional literal table, saved as macro-free DOCX. The tool does not promise arbitrary formatting, pictures, existing-file edits, imports, printing, email or publication. Unsupported requests stay on the desktop route, or stop with an explicit failure if they cannot be completed faithfully. A native interface that cannot be bound to the selected process falls back before any Office write. After a write starts, an uncertain failure is retained for review; it does not trigger a blind alternate workflow.

Saved file verification reads the actual OOXML package: document identity/content types, cell values, formula text and calculated caches, column formats, chart sources/cache/title, paragraphs and table contents. It rejects external relationships, executable/embedded content, unexpected document fields and output links/junctions. Explicit cell-number assignments and literal document titles are independently checked against the user request before creation. Broader interpretation of a natural-language request still relies on the planner; agreement with a validated plan is not an independent semantic proof of every possible goal. Typography and artistic/print appearance are not certified.

Durable jobs journal the native effect before dispatch and checkpoint the file hashes after verification. Resuming a verified goal rereads the saved file without creating it twice. A missing or changed file, changed saved app/OS generation, or interrupted unverified effect prevents automatic completion/replay. Verified recipes enter the existing versioned evidence graph and are retired after installation changes. The adapter binds the running application's process, version and installation path; it never executes model-generated COM method names or scripts and never quits the application or edits existing documents.

## Automatic Windows acceptance

Run `windows\TestOffice.cmd` after setup, or `app-agent self-test --with-office`. This runs the existing Windows checks and adds credential-free native Excel and Word checks. Each Office check creates a new test file, verifies its bytes and leaves the test document open. Missing or ambiguous Office installations are reported as skipped rather than passed. Native interface/save/verification failures are reported as failures. This option is separate from the connection helper's existing Calculator/Notepad grant; that grant is not silently expanded.

The cloud regression suite has **372 passing tests**, including **33 Office checks**. COM/Windows behavior is simulated on Linux; temporary file and SQLite verification are real. Additional validation using independently generated openpyxl and python-docx files passed, and an uncalculated formula was rejected. None of these substitutes for native Excel/Word acceptance. No new live Windows tests ran for this release because the previous helper connection is stopped. Universal all-app mastery, broad creative/browser/file-manager coverage, microphone reliability and update adaptation on a real host remain unfinished.

## Documented interfaces

Implementation checked Microsoft's public interface references:

- [Excel Workbooks.Add](https://learn.microsoft.com/en-us/office/vba/api/excel.workbooks.add), [Workbook.SaveAs](https://learn.microsoft.com/en-us/office/vba/api/excel.workbook.saveas) and [XlFileFormat](https://learn.microsoft.com/en-us/office/vba/api/excel.xlfileformat).
- [Range.Value2](https://learn.microsoft.com/en-us/office/vba/api/excel.range.value2), [Range.Formula](https://learn.microsoft.com/en-us/office/vba/api/excel.range.formula), [Range.Calculate](https://learn.microsoft.com/en-us/office/vba/api/excel.range.calculate), [Series.XValues](https://learn.microsoft.com/en-us/office/vba/api/excel.series.xvalues) and [Application.Hwnd](https://learn.microsoft.com/en-us/office/vba/api/excel.application.hwnd).
- [Word Documents.Add](https://learn.microsoft.com/en-us/office/vba/api/word.documents.add), [Window.Hwnd](https://learn.microsoft.com/en-us/office/vba/api/word.window.hwnd), [Document.SaveAs2](https://learn.microsoft.com/en-us/dotnet/api/microsoft.office.interop.word._document.saveas2), [WdSaveFormat](https://learn.microsoft.com/en-us/office/vba/api/word.wdsaveformat) and [WdBuiltinStyle](https://learn.microsoft.com/en-us/office/vba/api/word.wdbuiltinstyle).
