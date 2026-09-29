# Test cases: catalogue

All public (no login needed). Demo data from `seed_demo_catalogue`.

**TC-CAT-01 · Facets · P2 · FR-CAT-2**
Steps: `GET /catalogue/facets`. Expected: classes 6–12; boards CBSE, ICSE, WBBSE; 5 path stages; disciplines with subjects.

**TC-CAT-02 · Items list shows only published · P1 · FR-CAT-2**
Pre: in admin, create a course with status `draft`. Steps: `GET /catalogue/items`.
Expected: AI Foundations and "Explore AI (Class 8)" listed; the draft course **not** listed.

**TC-CAT-03 · Filters · P2 · FR-CAT-2**
Steps: `?type=course`, `?class_number=8`, `?board=icse`, `?subject=ai-foundations`, `?stage=2`.
Expected: board-independent courses (AI Foundations) appear for any class or board; `type=course` excludes programmes.

**TC-CAT-04 · Pagination · P3**
Steps: `?page_size=1&page=2`. Expected: one result; `page: 2`; `total` equals the unpaginated count. `page_size=500` is
capped at 50.

**TC-CAT-05 · Course page · P1**
Steps: `GET /courses/ai-foundations`. Expected: 3 lessons, all `is_free: true` and `has_content: true`; 4 skills;
`path_stage_label: "Explore"`; `price_paise: 49900`.

**TC-CAT-06 · Unknown or draft course · P2**
Steps: `GET /courses/does-not-exist`, then `GET /courses/biology-class-12` (a draft course).
Expected: `404 not_found` for a wrong slug and for a draft course's slug.

**TC-CAT-07 · Programme page · P2**
Steps: `GET /programmes/explore-ai-class-8`. Expected: class 8; courses list contains AI Foundations with its price.

**TC-CAT-08 · Free preview · P1 · FR-CAT-3**
Steps: `GET /lessons/<first lesson id>/preview`. Expected: `200` with sections; no quiz, no tutor.

**TC-CAT-09 · Preview of a paid lesson refused · P1 · FR-CAT-3**
Pre: in admin add a second module (not free) to AI Foundations with one lesson. Steps: preview that lesson.
Expected: `403 not_entitled`.
