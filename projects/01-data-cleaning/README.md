# 01 · Customer Data Cleaning Pipeline

Turns a messy customer export (mixed formats, typos, duplicates, invalid values and
spreadsheet-injection attempts) into a clean, validated, deduplicated table, plus a
data-quality report.

## Problem
CRM exports are rarely analysis-ready. The synthetic input reproduces common issues:

| Field | Examples of mess |
| --- | --- |
| Name | `"  mary-ann  O'NEIL "`, `"JOHN   SMITH"`, `=HYPERLINK(...)` |
| Email | upper case, padded spaces, `john@`, `N/A` |
| Phone | `(415) 555-0123`, `415.555.0123`, `+1 415 555 0123`, `ext 12` |
| State | `California`, `ca`, `Calif.`, `Atlantis` |
| Date | `2021-03-04`, `03/04/2021`, `Mar 04, 2021`, `2099-01-01` |
| Money | `$1,234.50`, `USD 99.99`, `(25.00)`, `abc` |

## Approach
1. **Standardize**
2. **Validate**
3. **Deduplicate**
4. **Report**
5. **Write Safely**

## Results (seed 42)
| Metric | Value |
| --- | --- |
| Rows in | 2,120 |
| Clean rows | 1,930 |
| Rejected (with reason) | 75 |
| Duplicates removed | 115 |

## Run it
```bash
make cleaning     # from the repo root
pytest projects/01-data-cleaning -q
```

## Skills shown
pandas · regular expressions · data validation · deduplication · data-quality reporting ·
unit testing with pytest · secure CSV export
