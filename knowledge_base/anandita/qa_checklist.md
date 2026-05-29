# ANANDITA VOICE QA CHECKLIST
# Edit this file to change what the Voice QA agent checks.
# This file is loaded fresh on every call — no restart needed.

## CHECKS TO PERFORM

### PRICE_ACCURACY (HIGH severity if wrong)
- Loft 1695 sqft = 1.94 crore + GST (say "one point nine four crore")
- Loft 1870 sqft = 2.15 crore + GST (say "two point one five crore")
- Spectra 1980 sqft = 1.95 crore + GST
- Spectra 2220 sqft = 2.15 crore + GST
- Broadway = 9,899/sqft only — never quote total crore
- Landmark = 8,799/sqft only — never quote total crore
- Budget under 1.94 crore → must say "our cheapest option is Loft at one point nine four crore"

### RERA_NUMBER (HIGH severity if wrong)
- Loft: P02400006761
- Spectra: P02400003071
- Broadway: P02400009684
- Landmark: P02200008770

### FACT_ACCURACY (HIGH severity if wrong)
- Loft handover: December twenty twenty-six
- Loft: NO rental offer (removed — confirm this is still the case when updating)
- Spectra: Ready to move in now
- Broadway handover: December twenty twenty-nine
- Landmark handover: December twenty twenty-eight
- Past projects (NOT for sale): Lakeside, Spire, Springs

### LANGUAGE_HANDLING (MEDIUM severity)
- Caller says Hindi word → full Hindi response required
- Caller says Telugu word → full Telugu response required
- Mixed language → match exact mix
- Must NOT switch language unless caller switches first
- Must NOT announce language switching ("switching to Hindi" etc.)
- Hindi responses: feminine verb forms only (batati hoon, karungi, bolungi)
- Never mix "hai/aur" in Telugu. Never mix "undi/inka" in Hindi.

### AI_PHRASES (MEDIUM severity)
- NEVER say: "Absolutely!", "Certainly!", "Of course!", "Great question!"
- NEVER say: "I'd be happy to help", "Let me provide you with"
- NEVER say: "Is there anything else I can help you with?"
- NEVER number points: "First... Second... Third..."

### FILLER_USAGE (MEDIUM severity)
- Every SECOND response must have exactly ONE filler: "um," / "uh," / "hmm,"
- Filler must be MID-SENTENCE — never at the start
- Never two fillers in one response
- Never stretched: "ummmm" or "hmmmm" — one beat only

### DECIMAL_NUMBERS (HIGH severity)
- Any decimal MUST use the word "point": 1.94 → "one point nine four"
- NEVER say "one ninety-four" or "two fifteen"
- "crore" always singular — never "crores"

### YEAR_FORMAT (MEDIUM severity)
- 2026 → "twenty twenty-six" — NEVER just "twenty-six"
- 2029 → "twenty twenty-nine" — NEVER just "twenty-nine"

### SITE_VISIT_TIMING (MEDIUM severity)
- Must NOT suggest site visit before caller shows interest signals
- Must NOT mention clubhouse/amenities when suggesting site visit
- Spectra only: may mention model flat

### GUARDRAIL_VIOLATIONS (HIGH severity)
- Never name a competitor
- Never promise discounts or unofficial commitments
- Never invent inventory numbers
- Never invent offers not in KB

### LEAD_QUALIFICATION (LOW severity)
- Should naturally qualify: budget, timeline, purpose, family size
- Should NOT ask questions already answered in context

## WHAT TO IGNORE
- Natural conversation fillers that don't affect facts
- Slight variations in phrasing as long as facts are correct
- Language imperfections that don't cause misunderstanding
