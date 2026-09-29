# Miora prompt pack — Technical Services Fault Diagnosis

## Miora's role: DESIGN AGENT (UI/UX + slides)

Miora is **not** a knowledge repository, backend, or diagnostic engine.
Those are already built and final (WorkBuddy spec → CodeBuddy backend +
tests + review, R1–R12 fixed, 19 tests passing, 14 endpoints, KB v1.3.0).

Miora turns the completed specification into a **coherent, interactive-looking
UI/UX design** for the Keppel Intelligence Pill demo. It designs how the
**Asset Operations Manager** interacts with the system:

> Detect issue → Review AI diagnosis → Approve action → Verify maintenance → Review outcome

## Workflow

```
WorkBuddy  →  specification            (done)
CodeBuddy →  backend + tests + review (done)
Miora     →  UI/UX design              ← YOU ARE HERE
CodeBuddy →  implement UI components, connect backend, validate
Final       →  full demo (J validates experience, S validates backend)
```

## Files

| File | Purpose |
|------|---------|
| `01_miora_design_prompt.md` | The ready-to-use prompt to paste into Miora |
| `02_screen_field_map.md` | Maps every design element to a real backend field/endpoint so S can wire it without inventing behaviour |

## Definition of done

Miora's work is complete when:
- A consistent visual system exists (colour palette, typography, components)
- All five screens are designed
- Key interactions are mapped (approve / reject / modify / verification)
- S can connect the designs to the existing APIs without inventing new backend behaviour

## Priority

Start with **screens 1–3** (detect → AI recommendation → human approval) —
they form the core of the live demo. Add screens 4–5 (maintenance verification
+ knowledge governance) to show the full Intelligence Pill lifecycle.