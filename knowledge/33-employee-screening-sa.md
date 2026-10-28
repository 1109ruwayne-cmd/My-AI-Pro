# 33 - Employee Screening & Trust Files (South Africa)

Added 2026-10-28. How My AI Pro keeps employee records (certificates + SARS tax numbers)
and how screening stays lawful. Backed by the `hr_file` skill (OWNER-ONLY) and `hrdesk.py`
server-side store (hr.db).

## What the app stores (owner-only, server-side)

- **Employee**: name, ID number, position, SARS tax number, POPIA consent status, notes.
- **Certificates** per employee: credential, issuing body, number, issued/expires dates,
  verification status (pending / verified / rejected / expired), verification note.
- Tax numbers are format-checked on the way in; every certificate comes back with the
  free official channel to verify it (see module 32).
- The `hr_file` skill is hidden from visitors: the model literally cannot be asked for
  employee data by anyone without the owner password.

## SARS numbers - the facts (verified Oct 2026)

- **Employee's personal income tax reference**: exactly 10 digits, starts 0, 1, 2, 3 or 9
  (OECD TIN portal + SARS BRS). Appears on the employee's IRP5 and IT150.
- **Employer PAYE reference**: 10 digits starting with 7. If an employer is NOT PAYE-
  registered their income tax number (0/1/2/3/9) is used and all certificates must be
  IT3(a) - no tax deducted.
- **Modulus-10**: SARS applies a modulus-10 check digit test to reference numbers in the
  PAYE BRS validation rules - a number failing it is likely a typo. Payroll systems
  reject such numbers on EMP501/IRP5 submission.
- **VAT numbers (start with 4) are NOT personal tax numbers** - common mix-up.
- **UIF/SDL linkage rule**: last 9 digits of the UIF/SDL reference match the last 9 of
  the PAYE number (where PAYE starts with 7).
- **Proof of an employee's tax number**: the IT150 Notice of Registration (name + ID +
  tax number, downloadable from the employee's own eFiling profile) or any IRP5.
- **The app NEVER pulls numbers from SARS.** There is no lawful public API for third
  parties to look up a person's tax number - the employee supplies it, the employer
  format-checks it and keeps the IT150/IRP5 proof on file. Asking for someone's eFiling
  login is a red line - never.

## Certificates - lawful verification flow

1. **Consent first (POPIA)**: ID numbers, criminal records and health info are special
   personal information - get written consent BEFORE screening (trust_desk
   action=consent_form generates it). Record consent=yes on the employee file.
2. **Employee supplies certified copies**; capture credential, body, number, dates in the
   trust file (hr_file action=add_certificate).
3. **Verify via the official channel** for the type (module 32): SACPCMP search for
   project/construction managers, SANC eRegister for nurses, AHPRA for Australia,
   issuing institution/QCTO/SETA for training certificates, SAQA for qualifications,
   pbdesig.saqa.org.za for professional designations.
4. **Record the outcome**: hr_file action=update_certificate status=verified/rejected
   with a note ("checked SANC eRegister 2026-10-28, active, ref 12345").
5. **Track expiries**: SACPCMP registrations lapse 31 March yearly, SANC APCs are annual,
   AHPRA renews 31 May, PrDPs and first-aid certificates carry their own dates. The
   lookup and list actions flag EXPIRED / expiring-within-60-days automatically.

## What may and may not be checked

- MAY (with consent + job relevance): qualifications, professional registrations,
  identity, tax number for payroll, reference checks, credit check ONLY for roles with
  financial trust (see module 31 - permissible purpose + consent), criminal record via
  SAPS with written consent or via an accredited screening provider (e.g. MIE).
- MAY NOT: social-media snooping beyond public professional claims, health testing
  without legal justification (EEA s7-11), requiring eFiling/SARS logins, pulling data
  from credit bureaus without a subscriber agreement, retaining data after the purpose
  ends without reason.
- EEA note: Employers must verify qualifications claimed for appointment; misrepresentation
  of qualifications can be grounds for dismissal - but the verification itself must follow
  POPIA (consent, minimality, purpose).

## Chat examples (owner)

- "Add employee Thabo Mokoena, ID 9001015555087, site agent, tax number 9123456789,
  consent yes." -> stored + tax format-check result.
- "Record Thabo's SACPCMP Pr.CPM certificate 123456, expires 2027-03-31." -> stored
  pending + verify hint (SACPCMP search, March rule).
- "Look up Thabo." -> full file: tax check, consent, certificates with statuses,
  expiry warnings, verification channels.
- "List employees." -> summary with pending/verified counts + expiring certificates.
- "Is tax number 4012345678 valid for an employee?" -> rejected as a VAT number with
  the correct format explained.
