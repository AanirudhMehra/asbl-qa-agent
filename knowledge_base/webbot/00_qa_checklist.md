# CHATBOT QA CHECKLIST
# Edit this file to change what the QA agent checks.
# This file is loaded fresh on every conversation — no restart needed.

## CHECKS TO PERFORM

### PRICE_ACCURACY (HIGH severity if wrong)
- Loft 1695 sqft = 1.94 crore + GST
- Loft 1870 sqft = 2.15 crore + GST
- Spectra 1980 sqft = 1.95 crore + GST
- Spectra 2220 sqft = 2.15 crore + GST
- Broadway = Rs 9,899/sqft only — never quote total crore price
- Landmark = Rs 8,799/sqft only — never quote total crore price
- GST = 5% on all projects always — must be disclosed

### RERA_NUMBER (HIGH severity if wrong)
- Loft: P02400006761
- Spectra: P02400003071
- Broadway: P02400009684
- Landmark: P02200008770

### FACT_ACCURACY (HIGH severity if wrong)
- Loft handover: December 2026
- Spectra: Ready to move in now (handed over December 2025)
- Broadway handover: December 2029
- Landmark handover: December 2028
- Loft: NO rental offer
- Loft: NO model flat
- Spectra: Model flat available
- Broadway: NO model flat
- Landmark: NO model flat
- All projects: 3 BHK only EXCEPT Landmark which has 3BHK and 3.5BHK (4BHK sold out)

### PROJECT_MIXING (HIGH severity)
- Never carry a price, size, offer, or BHK type from one project to another
- If talking about Loft, use only Loft facts

### LEAD_CAPTURE (LOW severity if missed)
- In conversations of 3+ turns, bot should attempt to understand:
  budget range, timeline, purpose (own stay / investment)

### INVENTED_FACTS (HIGH severity)
- Bot must never invent discounts, offers, or inventory numbers not in KB
- If asked something not in KB → "let me have an executive confirm that for you"

### TONE (LOW severity)
- No bullet points or numbered lists in responses
- No "Great question!", "Absolutely!", "Certainly!"
- Responses should be 2-5 sentences — flag if much longer
- Should feel like a peer advisor, not a brochure

## WHAT TO IGNORE
- Minor phrasing variations that don't affect accuracy
- Slightly longer responses in complex topics
- Follow-up questions that are natural to the conversation
