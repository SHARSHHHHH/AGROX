"""Structured pest knowledge base (RAG source of truth for pests).

Mirrors the design of ml/knowledge.py (DISEASE_KB): the vision model only picks
a pest LABEL; all agronomic facts (symptoms, controls, thresholds) come from
this verified dictionary — never invented by the LLM.

Each entry follows a fixed schema so the IPM and severity engines can rely on
it. The knowledge base is intentionally easy to extend: add a new key with the
same fields and it flows through detection, severity, IPM and the frontend
automatically.

Control fields follow the Integrated Pest Management ladder, least-harmful
first: cultural -> mechanical -> biological -> chemical. Chemical entries never
contain product names, dosages or concentrations — only category-level,
label-deferring guidance, per the safety rules.

severity_threshold: a short, human-readable action-threshold description used by
the severity engine and shown to the user (the level of infestation at which
escalation is warranted for that pest).
"""

PEST_KB = {
    "Aphids": {
        "scientific_name": "Aphidoidea",
        "affected_crops": ["tomato", "chilli", "brinjal", "cucumber", "potato", "okra"],
        "symptoms": "Clusters of tiny soft-bodied insects on new shoots and leaf "
                    "undersides; curling, yellowing and stunted new growth; sticky "
                    "honeydew and sooty mould.",
        "visual_indicators": "Green, black or yellow specks massed along stems and "
                             "under young leaves; shiny sticky residue; ants moving "
                             "on the plant.",
        "common_causes": "Soft lush growth from excess nitrogen; nearby infested "
                         "plants; absence of natural predators.",
        "favorable_conditions": "Warm, dry weather (roughly 20–30°C) and tender new "
                                "growth.",
        "prevention": "Avoid over-fertilising with nitrogen; encourage beneficial "
                      "insects; use reflective mulch; inspect new plants before "
                      "introducing them.",
        "cultural_control": "Remove weeds that host aphids; avoid excess nitrogen; "
                            "keep plants well spaced for airflow.",
        "mechanical_control": "Spray plants with a strong jet of water to dislodge "
                             "colonies; prune and destroy heavily infested shoots; "
                             "use yellow sticky traps.",
        "biological_control": "Encourage or release lady beetles, lacewings and "
                             "parasitic wasps; protect these natural enemies.",
        "chemical_control": "Only if the action threshold is exceeded, consider a "
                           "locally registered insecticidal soap, neem-based product "
                           "or approved insecticide, following the product label and "
                           "local agricultural guidance.",
        "severity_threshold": "Escalate when colonies spread beyond a few shoots or "
                              "cover more than ~10–15% of leaves, or when honeydew/"
                              "sooty mould becomes widespread.",
    },
    "Whiteflies": {
        "scientific_name": "Aleyrodidae",
        "affected_crops": ["tomato", "chilli", "brinjal", "cucumber", "okra", "cotton"],
        "symptoms": "Tiny white winged insects that fly up in clouds when the plant "
                    "is disturbed; yellowing, weakening and honeydew with sooty mould; "
                    "can transmit viruses.",
        "visual_indicators": "White moth-like specks on leaf undersides; a white "
                             "cloud when foliage is shaken; sticky, blackened leaves.",
        "common_causes": "Warm conditions, dense planting, movement of infested "
                         "seedlings; poor natural-enemy populations.",
        "favorable_conditions": "Warm, humid weather and crowded canopies.",
        "prevention": "Use clean seedlings; yellow sticky traps for early detection; "
                      "avoid overcrowding; manage weeds.",
        "cultural_control": "Remove and destroy infested lower leaves; control weed "
                           "hosts; avoid dense spacing.",
        "mechanical_control": "Yellow sticky traps; vacuuming adults in small plots; "
                             "reflective mulch to deter settling.",
        "biological_control": "Encourage Encarsia parasitic wasps, lacewings and "
                             "predatory beetles; protect them from broad-spectrum "
                             "sprays.",
        "chemical_control": "Only above threshold, consider a locally registered "
                           "neem-based or approved product, rotating modes of action "
                           "and following the label and local guidance.",
        "severity_threshold": "Escalate when adults are numerous on most plants or "
                              "honeydew/virus symptoms appear, rather than a few "
                              "scattered adults.",
    },
    "Thrips": {
        "scientific_name": "Thysanoptera",
        "affected_crops": ["chilli", "onion", "tomato", "cucumber", "cotton"],
        "symptoms": "Silvery streaks and speckling on leaves; curled or distorted "
                    "leaves; scarred fruit; can transmit viruses.",
        "visual_indicators": "Very slender pale/dark insects in flowers and along "
                            "veins; silvery scratch-like patches with tiny black "
                            "faecal specks.",
        "common_causes": "Hot dry spells; nearby flowering weeds; movement on "
                         "seedlings.",
        "favorable_conditions": "Hot, dry weather.",
        "prevention": "Blue/yellow sticky traps; remove weed hosts; avoid water "
                      "stress; inspect flowers regularly.",
        "cultural_control": "Remove crop debris and weeds; avoid consecutive "
                           "susceptible crops; keep plants unstressed.",
        "mechanical_control": "Blue sticky traps; remove and destroy badly affected "
                             "flowers and leaves.",
        "biological_control": "Encourage predatory mites and minute pirate bugs; "
                             "protect natural enemies.",
        "chemical_control": "Only above threshold, consider a locally registered "
                           "product effective on thrips, rotating chemistry and "
                           "following the label and local guidance.",
        "severity_threshold": "Escalate when leaf silvering/distortion is widespread "
                              "or virus symptoms appear, not for a few trapped adults.",
    },
    "Fruit Borers": {
        "scientific_name": "Helicoverpa armigera (and related)",
        "affected_crops": ["tomato", "chilli", "okra", "pigeon pea", "cotton"],
        "symptoms": "Round bore holes in fruit; internal feeding and frass; fruit "
                    "rot and drop; caterpillars found inside fruit.",
        "visual_indicators": "Neat holes on fruit surface, often with excreta at the "
                            "entry; hollowed or rotting fruit interiors.",
        "common_causes": "Moth egg-laying during flowering/fruiting; continuous "
                         "cropping of hosts.",
        "favorable_conditions": "Warm weather during flowering and fruiting stages.",
        "prevention": "Pheromone traps to monitor moths; timely harvest; crop "
                      "rotation; destroy crop residue.",
        "cultural_control": "Handpick and destroy bored fruit; deep summer ploughing; "
                           "rotate away from host crops.",
        "mechanical_control": "Pheromone traps to catch males; light traps; remove "
                             "and destroy infested fruit.",
        "biological_control": "Release Trichogramma egg parasitoids where available; "
                             "encourage birds; use approved Bt formulations against "
                             "young larvae.",
        "chemical_control": "Only above threshold and targeting young larvae, consider "
                           "a locally registered product, observing pre-harvest "
                           "intervals and following the label and local guidance.",
        "severity_threshold": "Escalate when bored fruit exceeds roughly 5–10% or moth "
                              "catches rise sharply in traps.",
    },
    "Stem Borers": {
        "scientific_name": "Chilo / Scirpophaga spp.",
        "affected_crops": ["rice", "maize", "sugarcane", "sorghum"],
        "symptoms": "Dead central shoot ('dead heart') in young plants; whiteheads "
                    "(empty panicles) later; tunnelling inside stems; exit holes.",
        "visual_indicators": "Central whorl dries while outer leaves stay green; "
                            "hollow tunnelled stems; small entry/exit holes near nodes.",
        "common_causes": "Moth egg masses on leaves; staggered planting; residue "
                         "harbouring larvae.",
        "favorable_conditions": "Warm, humid crop stages; overlapping plantings.",
        "prevention": "Use tolerant varieties; synchronous planting; destroy stubble; "
                      "balanced nitrogen.",
        "cultural_control": "Remove and destroy dead hearts and stubble; avoid "
                           "excess nitrogen; time planting to avoid peak moth flights.",
        "mechanical_control": "Pheromone and light traps; clip egg-mass-bearing leaf "
                             "tips; remove affected tillers.",
        "biological_control": "Release Trichogramma parasitoids where available; "
                             "conserve natural enemies.",
        "chemical_control": "Only above threshold, consider a locally registered "
                           "product applied to the whorl at the correct stage, "
                           "following the label and local guidance.",
        "severity_threshold": "Escalate when dead hearts exceed roughly 5–10% of "
                              "tillers or whitehead incidence rises.",
    },
    "Leaf Miners": {
        "scientific_name": "Liriomyza spp.",
        "affected_crops": ["tomato", "cucumber", "beans", "okra", "chilli"],
        "symptoms": "Winding pale tunnels ('mines') inside leaves; blotchy patches; "
                    "reduced photosynthesis; premature leaf drop when severe.",
        "visual_indicators": "Serpentine white/tan trails traced through the leaf; "
                            "tiny puncture dots on the surface.",
        "common_causes": "Adult flies laying in leaf tissue; broad-spectrum sprays "
                         "killing their natural enemies.",
        "favorable_conditions": "Warm weather; lush foliage.",
        "prevention": "Remove mined leaves early; yellow sticky traps; avoid "
                      "unnecessary broad-spectrum insecticides.",
        "cultural_control": "Pick and destroy mined leaves; remove crop residue; "
                           "avoid over-fertilising.",
        "mechanical_control": "Yellow sticky traps for adults; prune affected foliage.",
        "biological_control": "Conserve parasitic wasps (e.g. Diglyphus) that "
                             "naturally control miners; avoid disruptive sprays.",
        "chemical_control": "Only above threshold, consider a locally registered "
                           "product with translaminar action, rotating chemistry and "
                           "following the label and local guidance.",
        "severity_threshold": "Escalate when mines affect more than ~20% of leaf area "
                              "on many plants, especially on young plants.",
    },
    "Cutworms": {
        "scientific_name": "Agrotis spp.",
        "affected_crops": ["tomato", "cabbage", "maize", "brinjal", "chilli"],
        "symptoms": "Young seedlings cut off at or near the soil line overnight; "
                    "wilted, toppled plants; larvae hiding in soil by day.",
        "visual_indicators": "Seedlings felled at the base; smooth greasy grey/brown "
                            "caterpillars curled in the soil near damaged plants.",
        "common_causes": "Weedy or recently grassed land; moist soil with surface "
                         "debris; egg-laying moths.",
        "favorable_conditions": "Moist soil and abundant surface residue early in "
                                "the season.",
        "prevention": "Clear weeds before sowing; prepare land early; protective "
                      "collars around transplants.",
        "cultural_control": "Remove weeds and debris; expose soil by ploughing; "
                           "flood the bed briefly where feasible.",
        "mechanical_control": "Handpick larvae at night; place cardboard/foil collars "
                             "around seedling stems; dig around damaged plants.",
        "biological_control": "Encourage birds and predatory beetles; apply approved "
                             "Bt or entomopathogenic nematodes where available.",
        "chemical_control": "Only above threshold, consider a locally registered "
                           "bait or product applied near the base at dusk, following "
                           "the label and local guidance.",
        "severity_threshold": "Escalate when nightly seedling loss exceeds a few "
                              "plants per bed or a stand is being rapidly thinned.",
    },
    "Caterpillars": {
        "scientific_name": "Lepidoptera larvae (e.g. Spodoptera spp.)",
        "affected_crops": ["tomato", "cabbage", "chilli", "brinjal", "cucumber", "beans"],
        "symptoms": "Irregular chewed holes in leaves; skeletonised patches; visible "
                    "droppings; rapid defoliation in outbreaks.",
        "visual_indicators": "Ragged leaf edges and holes; green/brown caterpillars "
                            "on undersides; dark frass pellets on leaves.",
        "common_causes": "Moth egg masses; continuous host cropping; loss of natural "
                         "enemies to broad-spectrum sprays.",
        "favorable_conditions": "Warm weather; tender leafy growth.",
        "prevention": "Scout for egg masses; pheromone traps; encourage predators; "
                      "remove residue.",
        "cultural_control": "Handpick and destroy egg masses and larvae; remove crop "
                           "residue; rotate crops.",
        "mechanical_control": "Handpicking; pheromone and light traps; netting on "
                             "young or high-value plants.",
        "biological_control": "Conserve/release parasitoids and predators; apply "
                             "approved Bt against young larvae, which is selective and "
                             "spares beneficial insects.",
        "chemical_control": "Only above threshold and targeting young larvae, consider "
                           "a locally registered product, observing pre-harvest "
                           "intervals and following the label and local guidance.",
        "severity_threshold": "Escalate when defoliation approaches ~15–20% or many "
                              "larvae are present per plant, especially pre-harvest.",
    },
}

# Merge in the extended KB (more Indian crops + indigenous millet varieties —
# see pest_kb_extended.py). Kept as a separate source file so the original,
# demo-verified core set above stays easy to find, while every downstream
# consumer (severity engine, IPM engine, API, semantic match) sees one
# combined PEST_KB and needs no changes.
from app.ml.pest_kb_extended import PEST_KB_EXTENDED  # noqa: E402

PEST_KB.update(PEST_KB_EXTENDED)

# Pests the detector is allowed to name (kept in sync with the KB automatically).
KNOWN_PESTS = list(PEST_KB.keys())
