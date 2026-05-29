# KB-02 · ASBL LOFT PROJECT FACTS

> **Owner:** Sales Ops · **Update frequency:** As pricing/inventory changes (live document) · **Last verified:** March 2026
>
> All numbers in this file are immutable truths the bot uses as ground facts. Never approximate. If a fact isn't here, the bot must say *"let me have an executive confirm that for you."*
>
> **Reference IDs**: Each fact has a `[LOFT-NNN]` tag. When the QA agent flags an issue, it should cite the exact ID from this file.

---

## 1. PROJECT VITALS

| Field | Value | Ref |
|-------|-------|-----|
| Project Name | ASBL Loft | LOFT-001 |
| Developer | Ashoka Builders India Pvt. Ltd. | LOFT-002 |
| Location | Financial District, Gachibowli, Hyderabad | LOFT-003 |
| RERA No. | P02400006761 | LOFT-004 |
| Building Permit | 057423/ZOA/R1/U6/HMDA/21102022 | LOFT-005 |
| Configuration | Exclusive 3 BHK | LOFT-006 |
| Towers | 2 Towers, G+45 floors each | LOFT-007 |
| Units per floor | 10 per typical floor (unit numbers 01–10) | LOFT-008 |
| Total Units | 894 | LOFT-009 |
| Launched | August 2023 | LOFT-010 |
| Possession | December 2026 (Tentative) | LOFT-011 |
| Mortgage Partner | Bajaj Housing Finance Ltd (BHFL) | LOFT-012 |
| Sales Email | sales@asbl.in | LOFT-013 |
| Sales Office | SS Tech Park, PSR Prime Tower, Unit-2, Ground Floor, Hyderabad | LOFT-014 |

---

## 2. UNIT INVENTORY & PRICING

| Unit Type | Orientation | Saleable | Carpet | Balcony | Box Price | GST (5%) | All-in Consideration | Ref |
|-----------|-------------|----------|--------|---------|-----------|----------|---------------------|-----|
| 1,695 sqft East | East | 1,695 sqft | 1,050 sqft | 125 sqft | ₹1.94 Cr | ₹9.70 L | ~₹2.03 Cr | LOFT-020 |
| 1,695 sqft West | West | 1,695 sqft | 1,050 sqft | — | ₹1.94 Cr | ₹9.70 L | ~₹2.03 Cr | LOFT-021 |
| 1,870 sqft East | East | 1,870 sqft | ~1,160 sqft | 260 sqft wrap | ₹2.15 Cr | ₹10.75 L | ~₹2.26 Cr | LOFT-022 |
| 1,870 sqft West | West | 1,870 sqft | ~1,160 sqft | 260 sqft wrap | ₹2.15 Cr | ₹10.75 L | ~₹2.26 Cr | LOFT-023 |

**Key facts:**
- `[LOFT-024]` All balconies face outward — nothing blocks the line of sight.
- `[LOFT-025]` Per-sqft pricing is **not offered at the moment.**
- `[LOFT-026]` 1,870 sqft units are now available for sale.
- `[LOFT-027]` Approximate inventory: ~228 units available, ~665 sold (as of early 2026 — bot should not state exact availability; route `share_request` for live count).

---

## 3. OTHER CHARGES (for 1,695 sqft example)

| Charge | Rate | Total |
|--------|------|-------|
| Facility Maintenance (first 2 years) | ₹108/sqft + 18% GST | ₹2,16,011 |
| Corpus Fund | ₹80/sqft | ₹1,35,600 |
| Move-in Charges | ₹25,000/flat + 18% GST | ₹29,500 |
| **Total Other Charges** | — | **₹3,81,111** |

**All-in cost (excl. stamp duty + registration):** ~₹2.07 Cr for 1,695 sqft.

*Note: Maintenance cited as ₹100/sqft + 18% GST in older docs and ₹108/sqft + 18% GST in the pricing sheet. When in doubt, route to sales — do not quote without verification.*

---

## 4. PAYMENT STRUCTURES

### Structure A — Other Banks (higher booking, lower later)  `[LOFT-040]`
| Milestone | % | Amount (1,695 sqft) | Due |
|-----------|---|---------------------|-----|
| Booking (Customer) | 10% | ₹19.4 L | At booking |
| Installment 1 (Bank) | 57.5% | ₹1.11 Cr | 30 days from booking |
| Installment 2 (Customer + Bank) | 22.5% | ₹43.65 L | 30 Sep 2026 |
| Installment 3 (Bank) | 5% | ₹9.7 L | 31 Oct 2026 |
| Handover (Bank) | 5% | ₹9.7 L | 31 Dec 2026 |

### Structure B — Bajaj Housing Finance (BHFL — low entry)  `[LOFT-041]`
| Milestone | % | Amount (1,695 sqft) | Due |
|-----------|---|---------------------|-----|
| Booking (Customer) | 5.51% | ₹10 L | At booking |
| Installment 1 (Bank) | 62.35% | ₹1.20 Cr | 30 days from booking |
| Installment 2 (Customer + Bank) | 22.5% | ₹43.65 L | 30 Sep 2026 |
| Installment 3 (Bank) | 5% | ₹9.7 L | 31 Oct 2026 |
| Handover (Bank) | 5% | ₹9.7 L | 31 Dec 2026 |

- `[LOFT-042]` **Key differentiator for users:** BHFL = start with just ₹10 L. Other Banks = ₹19.4 L. Frame BHFL as the *"low-entry"* path.
- `[LOFT-043]` **Discontinued:** The 25:75 offer was discontinued on 11 February 2026. Do not mention it as active.

---

## 5. RENTAL OFFER (LIVE — headline conversion lever)

| Fact | Detail | Ref |
|------|--------|-----|
| Structure | Book at ₹10 L → receive guaranteed ₹50/sqft/month rental income | LOFT-050 |
| Validity | Till 31 December 2026 | LOFT-051 |
| 1,695 sqft payout | Up to ~₹84,750/month (cited as "up to ₹85,000") | LOFT-052 |
| 1,870 sqft payout | Up to ~₹93,500/month (cited as "up to ₹95,000") | LOFT-053 |
| FD 3BHK market rent today | ₹75K–₹85K | LOFT-054 |
| Nature | Contractual, written into agreement (not a forecast) | LOFT-055 |

**Why this matters:**
- Net effective entry on 1,695 sqft = ₹1.94 Cr box − ~₹20.4 L rental (~12 months) = **~₹1.73 Cr effective**.
- Gross yield = ₹10.2 L/year on ₹1.94 Cr = **~5.26% gross** — strong for Indian residential (sector average 2–3%).
- The offer is the single most powerful conversion tool. Surface on every investor-path touchpoint.

---

## 6. LOCATION & CONNECTIVITY (drive times)

### Corporate (key employers)
| Employer | Time |
|----------|------|
| Google Phase 2 Campus | 5 min |
| Apple Development Centre | 5 min |
| Amazon India HQ | 5 min |
| Waverock SEZ | 5 min |
| Accenture Corporate Office | 10 min |
| Microsoft India | 10 min |
| Infosys Campus | 15 min |
| TCS | 15 min |
| DLF Cyber City | 15 min |
| Google Main Campus | 20 min |

### Schools
Keystone International (5 min) · The Future Kid's (5 min) · Global Edge (10 min) · Oakridge International (10 min) · Delhi Public School (10 min) · The Gaudium (10 min) · Phoenix Greens International (15 min) · Rockwell International (15 min)

### Hospitals
Continental, Apollo, Star (5 min) · Care Hospitals, AIG (15 min) · Image Hospitals (25 min)

### Airport
35 min to Rajiv Gandhi International Airport

### Neighbourhood
Premium, safe, moderately dense urban residential-commercial mix. No slums. Robust civic, road, sewage and electrical infrastructure. Public transport easily accessible.

---

## 7. MASTER PLAN

Linear masterplan. Central towers flanked by landscaped amenity zones on both sides. North-south alignment for ventilation and natural light. Dedicated resident entry/exit, drop-off points, smooth vehicular flow.

### 26 Numbered Zones
1. Entry/exit dropoff · 2. Resident entry/exit · 3. Cascading waterfall · 4. Seating alcove · 5. Reflective pond · 6. Roundabout with sculpture · 7. Open lawn · 8. Gazebo seating · 9. Basketball court · 10. Kids' play area · 11. Toddler's play area · 12. Senior's court + reflexology park · 13. Outdoor fitness station · 14. Bicycle parking · 15. Clubhouse (55,000 sqft) · 16. Wall fountain · 17. Lawn spill-out · 18. Amphitheatre · 19. Multi-purpose plaza · 20. Pet's park · 21. Bicycle loop · 22. Jogging loop · 23. Avenue plantation · 24. Reflective waterbody · 25. Themed garden · 26. Party spill-out area

### Thematic Clusters
- **Active:** Basketball, outdoor fitness, jogging loop, cycling loop
- **Social:** 55,000 sqft clubhouse, amphitheatre, multi-purpose plaza, party spill-out
- **Wellness:** Reflexology park, themed garden, open lawn, seating alcoves, reflective pond

---

## 8. TOWERS

### Tower A — Professional Utility
- 10 units per typical floor, central spine corridor
- 2 main lift lobbies (north + south), 10 passenger high-speed lifts total
- 2 fire-escape staircases at corridor ends
- ODU platforms outside utility areas (noise isolation)
- Mix of 1,695 + 1,870 sqft + premium configs on select floors
- Most balconies outward-facing

**Urban Corridor (ground/podium):**
- Grand double-height entrance lobby with reflection pools
- Zen garden & outdoor lounge
- 2 co-working spaces (4 conference rooms total)
- Breakout lounges
- Ratnadeep Supermarket (double entry)
- Pharmacy + storage
- ATM locker
- Fire command centre

### Tower B — Family & Learning
- 10 units per floor, 6'11" central corridor
- 10 lifts, staircases at both ends
- Left wing = West-facing, right wing = East-facing
- Outdoor decks/balconies face outward

**Urban Corridor:**
- 3 creche play areas (padded floors)
- Tuition centre (2 classrooms)
- Hobby centre / art space
- Conference rooms, business pods
- Pantry, storage, service rooms
- ATM locker facility

---

## 9. SPECIFICATIONS (bot may cite these specifically when asked)

**Structure:** RCC Shear Wall (Zone 2 seismic compliance)
**Walls:** Asian Paints emulsion interior; GVT tile cladding in bathrooms
**Flooring:** 800×800mm double-charged vitrified (living/dining); 600×1200mm anti-skid matte (master bath); wood-finish vitrified (balcony)
**Main Door:** 2,400mm teak frame with Oak Veneer shutters
**Balcony:** UPVC sliding doors, double-glazed
**Kitchen:** Full power outlets pre-laid for Chimney, Hob, Fridge, Microwave, Mixer, Water Purifier, Dishwasher
**Plumbing:** Grohe-equivalent CP fittings · Duravit-equivalent sanitary ware · Sloan flush valves
**Electrical:** Legrand / Schneider switches; concealed PVC copper wiring throughout
**Lifts:** Kone-equivalent high-speed; 10 passenger + 2 service per tower
**Power:** 100% DG backup
**LPG:** Piped gas from centralized bank
**Solar:** On terrace
**Water:** WTP + STP (treated water reused for landscaping)
**EV Charging:** Points in basement parking
**Fire Safety:** NBC compliant — sprinklers, fire alarms, hydrants, fire curtains
**On-Campus Brands:** Bubbles Salon · Ratnadeep Supermarket · ICICI Bank

---

## 10. AMENITIES

### Clubhouse (55,000 sqft)
Swimming pool · Gym · Calisthenics studio · Yoga / fitness centre · Double-height squash court · 3 badminton courts · Indoor games room · Guest rooms · Multi-sports turf · Gents + Ladies salons · Creche (3 zones) · Hobby & art centre · Tuition centre · Co-working with conference rooms · Breakout lounges

### Outdoor / Landscape
Cascading waterfall · Reflective pond · Open lawn · Gazebo seating · Basketball court · Kids' play area · Toddler's play area · Senior reflexology walk · Outdoor fitness station · Bicycle parking · Jogging loop · Cycling loop · Avenue plantation · Amphitheatre · Multi-purpose plaza · Pet's park · Themed garden · Party spill-out area · Roundabout with sculpture · Wall fountain

### Urban Corridor (in-building)
Grand entrance lobby (double-height) · Reflection pools · Zen garden · 2 co-working spaces · 4 conference rooms · Ratnadeep Supermarket · Pharmacy · ATM locker · Creche play areas (padded floors)

---

## 11. SITE VISIT PROTOCOL

- `[LOFT-100]` Total duration: ~45 minutes
- `[LOFT-101]` 20 minutes at experience centre + 25 minutes tower walk
- `[LOFT-102]` Visitor meets a Relationship Manager (RM), not a sales desk
- `[LOFT-103]` **No model flat at Loft** — under construction. Static model flat with finish reference is at **ASBL SPIRE in Kokapet**, which is itself **SOLD OUT** and only a finish-spec reference.
- `[LOFT-104]` Always pivot model-flat questions to *"the Loft tower walk is more valuable — it's the real building, not a sales prop."*

---

## 12. ASBL PORTFOLIO (if the buyer asks about sister projects)

| Project | Location | Status | Ref |
|---------|----------|--------|-----|
| ASBL Loft | Financial District | Under construction (Dec 2026) | LOFT-110 |
| ASBL Spectra | Financial District | Ready to move in. 1,980–2,220 sqft, 39 floors, 4 towers, 1,158 units | SPEC-001 |
| ASBL Broadway | Financial District | Dec 2029. ₹9,899/sqft. 2,035–2,650 sqft, 50 floors, 3 towers, 885 units | BWAY-001 |
| ASBL Spire | Kokapet | **SOLD OUT** — finish reference only | PAST-002 |
| ASBL Landmark | Kukatpally | Active. ₹8,799/sqft. Dec 2028. | LMRK-001 |

**Positioning logic:**
- Loft vs Broadway: Loft for nearer-horizon utility; Broadway for long-horizon premium play
- Loft vs Spectra: Loft for convenience-led premium; Spectra for ready-to-move
- Loft vs Landmark: Loft for western-corridor job-node logic; Landmark for city-side family practicality

If buyer specifically asks about a sister project, honest acknowledgement is fine. Do not pivot-and-push — honesty builds brand trust.

---

## 13. DOWNLOADABLE ASSETS (use via `render_artifact` only — never paste URLs)

| Asset | Internal Reference |
|-------|-------------------|
| Brochure | `loft_brochure` |
| Master Plan | `loft_master_plan` |
| Amenities PDF | `loft_amenities` |
| Specifications | `loft_specifications` |
| Price Sheet (1,695 sqft) | `loft_price_sheet_1695` |
| Payment Structure – BHFL | `loft_payment_bhfl` |
| Payment Structure – Other Banks | `loft_payment_other` |
| 1,695 East Floor Plan | `loft_plan_1695_e` |
| 1,695 West Floor Plan | `loft_plan_1695_w` |
| Tower A Plan | `loft_tower_a` |
| Tower A Urban Corridor | `loft_uc_a` |
| Tower B Urban Corridor | `loft_uc_b` |

**Rule:** Bot surfaces these via `render_artifact` / `share_request`. Never paste raw S3 or Drive URLs.

---

## 14. KEY DIFFERENTIATORS (lead with these on first impressions)

1. **Only FD project with guaranteed rental income from booking.**
2. **Lowest entry ticket in FD** via BHFL (₹10 L).
3. **Largest clubhouse in micro-market** (55,000 sqft).
4. **All-outward balconies** — nothing blocks the view.
5. **December 2026 = closest delivery** in the FD micro-market with this scale.
