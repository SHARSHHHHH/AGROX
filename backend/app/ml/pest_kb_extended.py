"""Extended pest knowledge base — same verified schema as pest_knowledge.PEST_KB,
covering more Indian field crops and indigenous/minor-millet varieties that the
original 7-entry KB didn't reach (rice, pulses, oilseeds, cotton, sugarcane,
millets, coconut, general field pests).

This is deliberately a SEPARATE module rather than more entries jammed into
pest_knowledge.py: it keeps the original, demo-verified core KB easy to spot,
while making it obvious where new curated pests should be added going forward.
pest_knowledge.py merges this in automatically, so nothing downstream
(severity engine, IPM engine, API, tests) needs to know this file exists.

Same rules as the core KB: chemical_control is always category-level and
label-deferring — no product names, doses or concentrations.
"""

PEST_KB_EXTENDED = {
    "Brown Planthopper": {
        "scientific_name": "Nilaparvata lugens",
        "affected_crops": ["rice"],
        "symptoms": "Yellowing and drying of rice tillers from the base outward "
                    "('hopperburn'), circular patches of dead plants in the field, "
                    "stunted growth.",
        "visual_indicators": "Brown, wedge-shaped insects clustered at the base of "
                             "tillers near the waterline; sticky honeydew and sooty "
                             "mould on lower leaves.",
        "common_causes": "Excess nitrogen giving dense, lush growth; continuous "
                         "flooding; closely spaced planting restricting airflow.",
        "favorable_conditions": "Warm, humid weather with standing water and dense "
                                "canopy.",
        "prevention": "Avoid excess nitrogen; use resistant/tolerant varieties where "
                      "available; maintain alternate wetting and drying instead of "
                      "continuous flooding.",
        "cultural_control": "Drain the field intermittently to disrupt breeding; "
                            "avoid very close spacing; remove volunteer rice plants "
                            "and stubble between crops.",
        "mechanical_control": "Use light traps to monitor adult influx; direct a jet "
                              "of water at the base of hills to dislodge nymphs into "
                              "the water where predators can reach them.",
        "biological_control": "Conserve spiders, mirid bugs and dragonflies that prey "
                              "on hoppers; avoid broad-spectrum sprays that kill them.",
        "chemical_control": "Only above threshold and targeting the base of the "
                            "tillers, consider a locally registered product effective "
                            "on planthoppers, following the label and local guidance.",
        "severity_threshold": "Escalate when hopperburn patches appear or hopper "
                              "numbers at the tiller base are clearly building, not "
                              "for a few scattered individuals.",
    },
    "Rice Gundhi Bug": {
        "scientific_name": "Leptocorisa acuta",
        "affected_crops": ["rice"],
        "symptoms": "Discoloured, chaffy or empty grains; a distinctive foul odour "
                    "from disturbed insects; grain shrivelling at the milky stage.",
        "visual_indicators": "Slender greenish-brown bugs with long legs and antennae "
                             "on panicles during flowering and grain-filling; foul "
                             "smell when handled.",
        "common_causes": "Nearby grassy weeds and wild grasses hosting the bug; "
                         "staggered planting extending the susceptible flowering "
                         "window in the area.",
        "favorable_conditions": "Warm weather during panicle emergence and grain "
                                "filling; nearby weedy bunds.",
        "prevention": "Keep field bunds and surrounding areas free of grassy weeds; "
                      "synchronise planting with neighbouring fields where possible.",
        "cultural_control": "Clear weeds from bunds and channels; avoid staggered "
                            "sowing dates within a locality.",
        "mechanical_control": "Use a sweep net or hand-operated net during early "
                              "morning/evening when bugs are less active to remove "
                              "them; light traps for adults.",
        "biological_control": "Conserve spiders and predatory ants active on bunds; "
                              "avoid disturbing natural enemy populations with broad "
                              "spraying.",
        "chemical_control": "Only above threshold during the vulnerable milky grain "
                            "stage, consider a locally registered product, following "
                            "the label and local guidance.",
        "severity_threshold": "Escalate when bugs are consistently found on panicles "
                              "during flowering/milky stage across many hills, not for "
                              "occasional bund-edge sightings.",
    },
    "Gall Midge": {
        "scientific_name": "Orseolia oryzae",
        "affected_crops": ["rice"],
        "symptoms": "Central shoot transforms into a hollow, onion-leaf-like tubular "
                    "gall ('silvershoot') instead of producing a panicle; affected "
                    "tillers never flower.",
        "visual_indicators": "Pale, tubular, hollow 'onion leaf' galls standing above "
                             "the canopy in place of a normal leaf whorl.",
        "common_causes": "Continuous rice cropping without a break; nearby wild "
                         "grasses hosting the midge; staggered transplanting.",
        "favorable_conditions": "High humidity, cloudy weather and dense canopy "
                                "during the vegetative stage.",
        "prevention": "Use tolerant varieties where available; synchronise "
                      "transplanting across a locality; avoid excess nitrogen during "
                      "early vegetative stage.",
        "cultural_control": "Remove and destroy silvershoots by hand; clear grassy "
                            "weed hosts near bunds; avoid closely staggered plantings.",
        "mechanical_control": "Light traps to monitor adult midge emergence and time "
                              "any intervention.",
        "biological_control": "Conserve parasitic wasps that attack gall midge larvae; "
                              "avoid unnecessary broad-spectrum sprays early in the "
                              "season.",
        "chemical_control": "Only above threshold during early vegetative stage in "
                            "endemic areas, consider a locally registered granular or "
                            "systemic product, following the label and local guidance.",
        "severity_threshold": "Escalate when silvershoots appear on a noticeable share "
                              "of tillers during early vegetative growth.",
    },
    "Pod Borer": {
        "scientific_name": "Helicoverpa armigera / Maruca vitrata",
        "affected_crops": ["pigeon pea (arhar/tur)", "chickpea (chana)",
                          "black gram (urad)", "green gram (moong)", "cowpea (lobia)"],
        "symptoms": "Circular holes bored into pods; larvae feeding on developing "
                    "seeds inside pods; webbing between pods and leaves in some "
                    "species; pod drop.",
        "visual_indicators": "Round entry holes on pod surface, often with frass at "
                             "the opening; caterpillars visible inside opened pods; "
                             "webbed clusters of flowers/pods.",
        "common_causes": "Moth egg-laying concentrated during flowering and early "
                         "podding; continuous cultivation of host legumes in the "
                         "same area.",
        "favorable_conditions": "Warm weather coinciding with flowering and pod "
                                "formation.",
        "prevention": "Pheromone traps to monitor moth activity; intercropping with "
                      "non-host crops; timely sowing to avoid peak moth periods.",
        "cultural_control": "Hand-pick and destroy damaged pods and larvae; deep "
                            "ploughing after harvest to expose pupae; crop rotation "
                            "away from host legumes.",
        "mechanical_control": "Pheromone traps and bird perches in the field to "
                              "encourage predation; handpicking egg masses and young "
                              "larvae where feasible.",
        "biological_control": "Release Trichogramma egg parasitoids where available; "
                              "use approved Bt formulations against young larvae, "
                              "which spares pollinators visiting the flowers.",
        "chemical_control": "Only above threshold and targeting young larvae before "
                            "they enter pods, consider a locally registered product, "
                            "observing pre-harvest intervals and following the label "
                            "and local guidance.",
        "severity_threshold": "Escalate when bored pods exceed roughly 5–10% during "
                              "flowering/podding or trap catches rise sharply.",
    },
    "Pink Bollworm": {
        "scientific_name": "Pectinophora gossypiella",
        "affected_crops": ["cotton"],
        "symptoms": "Rosetted (fused) flowers, bored green bolls with pink larvae "
                    "inside, stained and damaged lint, premature boll opening.",
        "visual_indicators": "Small entry holes on bolls, often hard to see "
                             "externally; pink-tinged caterpillars found inside "
                             "opened bolls; rosette-shaped flowers that fail to open "
                             "normally.",
        "common_causes": "Carry-over of pupae in old cotton stalks and ginning "
                         "waste; extended or off-season cotton growth allowing the "
                         "pest to persist year-round.",
        "favorable_conditions": "Warm weather during boll development; continuous "
                                "cotton cultivation without a clear off-season break.",
        "prevention": "Destroy crop residue and stalks promptly after harvest; avoid "
                      "off-season/ratoon cotton; use pheromone traps for early "
                      "warning.",
        "cultural_control": "Uproot and destroy cotton stalks immediately after the "
                            "last picking; avoid storing unginned seed cotton near "
                            "the field; time sowing to avoid overlapping generations.",
        "mechanical_control": "Pheromone traps for monitoring and mass trapping; "
                              "collect and destroy rosette flowers and damaged bolls.",
        "biological_control": "Conserve natural enemies such as parasitic wasps; use "
                              "approved biological formulations where available.",
        "chemical_control": "Only above threshold based on pheromone trap catches or "
                            "boll damage, consider a locally registered product, "
                            "rotating modes of action and following the label and "
                            "local guidance.",
        "severity_threshold": "Escalate when trap catches rise sharply or boll/"
                              "rosette damage exceeds roughly 5–10%.",
    },
    "Mealybugs": {
        "scientific_name": "Phenacoccus solenopsis (and related)",
        "affected_crops": ["cotton", "sugarcane", "brinjal", "guava"],
        "symptoms": "White, cottony masses on stems, leaf axils and undersides; "
                    "curling and yellowing of leaves; stunted growth; sticky "
                    "honeydew with sooty mould.",
        "visual_indicators": "Waxy white cottony clusters on stems and leaf joints; "
                             "ants tending the colonies; blackened sooty leaves "
                             "beneath infested areas.",
        "common_causes": "Movement of infested planting material; ants protecting "
                         "colonies from predators; warm dry weather.",
        "favorable_conditions": "Warm, dry conditions and water-stressed plants.",
        "prevention": "Use clean, mealybug-free planting material; manage ant "
                      "populations that protect the colonies; avoid moving infested "
                      "material between fields.",
        "cultural_control": "Remove and destroy heavily infested plant parts; control "
                            "weeds that can host mealybugs; avoid water stress.",
        "mechanical_control": "Wipe or prune small colonies by hand early; use a "
                              "strong water jet to dislodge light infestations.",
        "biological_control": "Conserve or release the mealybug predator beetle "
                              "(Cryptolaemus) and parasitoids; control ants that "
                              "protect colonies from these natural enemies.",
        "chemical_control": "Only above threshold, consider a locally registered "
                            "systemic or contact product targeted at the colony base, "
                            "following the label and local guidance.",
        "severity_threshold": "Escalate when colonies spread beyond isolated spots to "
                              "many stems/leaf axils or sooty mould becomes widespread.",
    },
    "Early Shoot Borer": {
        "scientific_name": "Chilo infuscatellus",
        "affected_crops": ["sugarcane"],
        "symptoms": "Dead central shoot ('dead heart') that pulls out easily with a "
                    "foul smell in young sugarcane; drying of the central spindle "
                    "leaf.",
        "visual_indicators": "Central whorl dries and withers while outer leaves "
                             "stay green; the dead heart pulls out easily and smells "
                             "unpleasant at the base.",
        "common_causes": "Moth egg-laying on young cane; delayed or staggered "
                         "planting; retained old stubble carrying larvae.",
        "favorable_conditions": "Warm weather during the early tillering stage of "
                                "the crop.",
        "prevention": "Use healthy, pest-free setts for planting; timely planting to "
                      "avoid peak moth emergence; remove and destroy old stubble.",
        "cultural_control": "Detrash and remove dead hearts regularly; avoid "
                            "prolonged water stress in young cane; destroy crop "
                            "residue after harvest.",
        "mechanical_control": "Pull out and destroy dead hearts by hand as soon as "
                              "they appear; light traps to monitor moth activity.",
        "biological_control": "Release Trichogramma egg parasitoids where available; "
                              "conserve natural enemies by avoiding unnecessary "
                              "broad-spectrum sprays early in the season.",
        "chemical_control": "Only above threshold during the vulnerable early "
                            "tillering stage, consider a locally registered product "
                            "applied at planting or as a follow-up, following the "
                            "label and local guidance.",
        "severity_threshold": "Escalate when dead hearts exceed roughly 5–10% of "
                              "shoots in young cane.",
    },
    "Sugarcane Woolly Aphid": {
        "scientific_name": "Ceratovacuna lanigera",
        "affected_crops": ["sugarcane"],
        "symptoms": "White, woolly (cotton-like) colonies on the underside of lower "
                    "and middle leaves; yellowing, drying leaves; heavy honeydew "
                    "with sooty mould reducing photosynthesis and juice quality.",
        "visual_indicators": "Dense white woolly patches on leaf undersides; "
                             "blackened, sticky leaf surfaces from sooty mould; ants "
                             "moving between colonies.",
        "common_causes": "Dense, poorly ventilated canopy; movement of infested "
                         "planting material or leaves between fields; nitrogen-rich "
                         "lush growth.",
        "favorable_conditions": "Warm, humid weather with dense, overcrowded "
                                "canopy.",
        "prevention": "Avoid excess nitrogen; maintain recommended spacing for "
                      "airflow; remove and destroy trash from previously infested "
                      "fields before replanting.",
        "cultural_control": "Detrash lower leaves regularly to improve airflow and "
                            "expose colonies to predators and sunlight; remove and "
                            "burn severely infested leaves.",
        "mechanical_control": "Manual detrashing and destruction of heavily infested "
                              "leaves; avoid moving infested leaf material to clean "
                              "fields.",
        "biological_control": "Conserve or release ladybird beetles and the parasitic "
                              "wasp Dipha aphidivora, both effective natural enemies "
                              "of this aphid.",
        "chemical_control": "Only above threshold and difficult to reach with the "
                            "woolly coating, consider a locally registered systemic "
                            "product, following the label and local guidance.",
        "severity_threshold": "Escalate when woolly colonies cover a large share of "
                              "leaves across many stalks, not a few lower leaves.",
    },
    "Shoot Fly": {
        "scientific_name": "Atherigona spp.",
        "affected_crops": ["sorghum (jowar)", "pearl millet (bajra)",
                          "finger millet (ragi)", "maize"],
        "symptoms": "Dead central shoot ('dead heart') in young seedlings that pulls "
                    "out easily; a foul smell at the base; poor, gappy plant stand.",
        "visual_indicators": "Central leaf whorl wilts and dries while the plant "
                             "otherwise looks healthy; the dead heart lifts out "
                             "easily with a rotten smell at the cut end.",
        "common_causes": "Staggered or delayed sowing extending the vulnerable "
                         "seedling stage across a locality; low plant density "
                         "increasing per-plant fly pressure.",
        "favorable_conditions": "Warm weather during the first 2–4 weeks after "
                                "seedling emergence.",
        "prevention": "Sow with the onset of favourable rains and avoid delayed or "
                      "staggered sowing; use a higher seed rate to compensate for "
                      "expected losses; consider tolerant varieties where available.",
        "cultural_control": "Remove and destroy dead-heart seedlings promptly to "
                            "reduce carry-over; avoid very sparse plant stands; "
                            "synchronise sowing dates within a locality.",
        "mechanical_control": "Hand-rogue and destroy affected seedlings as soon as "
                              "dead hearts are seen.",
        "biological_control": "Conserve natural parasitoids of shoot fly by avoiding "
                              "unnecessary early-season broad-spectrum sprays.",
        "chemical_control": "Only above threshold and typically as a seed treatment "
                            "or early foliar application in endemic areas, consider a "
                            "locally registered product, following the label and "
                            "local guidance.",
        "severity_threshold": "Escalate when dead hearts affect a noticeable share of "
                              "seedlings within the first few weeks, thinning the "
                              "stand.",
    },
    "Earhead Bug": {
        "scientific_name": "Calocoris angustatus",
        "affected_crops": ["sorghum (jowar)"],
        "symptoms": "Shrivelled, discoloured or chaffy grains in the earhead; "
                    "empty or partially filled panicles at maturity.",
        "visual_indicators": "Small greenish-yellow bugs on the earhead during "
                             "flowering and grain-filling; grains appear shrunken or "
                             "discoloured where bugs have fed.",
        "common_causes": "Flowering coinciding with peak bug activity; nearby "
                         "grassy weeds hosting the bug between seasons.",
        "favorable_conditions": "Warm weather during earhead emergence and "
                                "flowering.",
        "prevention": "Grow varieties with compact earheads where available, which "
                      "are less attractive to the bug; manage grassy weeds around "
                      "the field.",
        "cultural_control": "Synchronise sowing within a locality to shorten the "
                            "window of susceptible flowering; remove grassy weed "
                            "hosts from bunds.",
        "mechanical_control": "Shake earheads over a tray during early morning to "
                              "dislodge and count/remove bugs on a sample basis.",
        "biological_control": "Conserve predatory bugs and spiders active on the "
                              "earhead; avoid unnecessary broad-spectrum sprays "
                              "during flowering, which also protects pollinators.",
        "chemical_control": "Only above threshold during flowering/grain-filling, "
                            "consider a locally registered product, following the "
                            "label and local guidance.",
        "severity_threshold": "Escalate when bugs are consistently present on most "
                              "earheads during flowering, not a few scattered "
                              "individuals.",
    },
    "Red Hairy Caterpillar": {
        "scientific_name": "Amsacta spp.",
        "affected_crops": ["groundnut", "castor", "black gram (urad)",
                          "green gram (moong)"],
        "symptoms": "Rapid, extensive defoliation soon after the first rains; large "
                    "hairy caterpillars moving across fields in groups; bare "
                    "stripped plants in patches.",
        "visual_indicators": "Reddish-brown, densely hairy caterpillars, often seen "
                             "migrating in numbers across the soil surface and up "
                             "plants; skeletonised or fully stripped leaves.",
        "common_causes": "Moths emerging with the first monsoon rains after "
                         "overwintering as pupae in the soil; light attraction "
                         "concentrating egg-laying near fields.",
        "favorable_conditions": "Onset of monsoon rains after a dry spell.",
        "prevention": "Summer ploughing to expose and destroy overwintering pupae; "
                      "light traps before sowing to reduce moth numbers; bund "
                      "trenches to intercept migrating larvae.",
        "cultural_control": "Dig trenches around the field edge to trap migrating "
                            "larvae before they enter the crop; handpick and destroy "
                            "egg masses and young larval clusters early.",
        "mechanical_control": "Light traps for adult moths; collect and destroy "
                              "larvae congregating at field bunds before they "
                              "disperse into the crop.",
        "biological_control": "Encourage birds, which readily feed on these exposed "
                              "caterpillars; conserve natural parasitoids.",
        "chemical_control": "Only above threshold and mainly on young larvae "
                            "clustered near field edges before they disperse, "
                            "consider a locally registered product, following the "
                            "label and local guidance.",
        "severity_threshold": "Escalate when migrating larvae are entering the field "
                              "in numbers rather than isolated bund sightings.",
    },
    "Coconut Rhinoceros Beetle": {
        "scientific_name": "Oryctes rhinoceros",
        "affected_crops": ["coconut", "oil palm"],
        "symptoms": "Characteristic V-shaped or triangular cuts in unopened young "
                    "fronds; boring damage at the crown; reduced frond and nut "
                    "production in repeated attacks.",
        "visual_indicators": "Fresh, wedge-shaped notches on newly opened fronds; "
                             "chewed fibrous frass at the crown; occasionally the "
                             "beetle itself found lodged in the crown.",
        "common_causes": "Breeding sites in decaying organic matter, manure pits, "
                         "or rotting palm stems nearby; young, low-crowned palms are "
                         "most exposed.",
        "favorable_conditions": "Presence of decomposing organic breeding material "
                                "(farmyard manure heaps, dead palm trunks) near the "
                                "plantation.",
        "prevention": "Remove or properly compost breeding material away from "
                      "palms; keep the crown region clean of debris where beetles "
                      "could hide; treat manure pits before use.",
        "cultural_control": "Sanitation of the plantation — remove and destroy dead "
                            "palm trunks and decaying stumps that serve as breeding "
                            "sites; cover farmyard manure pits.",
        "mechanical_control": "Hook out and destroy beetles lodged in the crown by "
                              "hand where reachable; pheromone-baited traps to catch "
                              "adults away from palms.",
        "biological_control": "Apply or conserve the Oryctes baculovirus and "
                              "Metarhizium fungal biocontrol agents in breeding "
                              "sites, which specifically target this beetle.",
        "chemical_control": "Only for severe, repeated crown attacks, consider "
                            "placing a locally registered product in the leaf axils "
                            "as per label directions, following local guidance.",
        "severity_threshold": "Escalate when fresh V-cuts appear on multiple "
                              "successive fronds or the beetle is found in the crown, "
                              "not for one old healed notch.",
    },
    "Termites": {
        "scientific_name": "Odontotermes / Microtermes spp.",
        "affected_crops": ["wheat", "sugarcane", "groundnut", "maize",
                          "finger millet (ragi)", "pearl millet (bajra)"],
        "symptoms": "Wilting and drying of whole plants, especially under moisture "
                    "stress; hollowed stems and roots packed with soil; patchy "
                    "plant death that spreads outward from a point.",
        "visual_indicators": "Soil particles cemented onto stem bases; hollow, "
                             "soil-filled stems and roots when pulled and split "
                             "open; earthen sheeting on the plant near the soil "
                             "line.",
        "common_causes": "Undecomposed organic matter (old roots, stubble) in the "
                         "soil attracting termite colonies; drought-stressed crops "
                         "are more vulnerable to attack.",
        "favorable_conditions": "Dry soil conditions and moisture-stressed crops; "
                                "presence of nearby termite mounds.",
        "prevention": "Ensure crop residue is decomposed before sowing rather than "
                      "left as fresh undecomposed matter; avoid moisture stress "
                      "through timely irrigation; treat farmyard manure before "
                      "application.",
        "cultural_control": "Remove and destroy nearby termite mounds where "
                            "practical; incorporate well-decomposed organic matter "
                            "rather than fresh residue; maintain adequate soil "
                            "moisture.",
        "mechanical_control": "Locate and physically destroy accessible termite "
                              "mounds near the field; flood irrigation channels near "
                              "mounds where feasible to disrupt colonies.",
        "biological_control": "Apply approved entomopathogenic fungi (e.g. "
                              "Metarhizium-based products) to soil or manure as a "
                              "biological alternative to chemical treatment.",
        "chemical_control": "Only above threshold, typically as a seed or soil "
                            "treatment before sowing, consider a locally registered "
                            "product, following the label and local guidance.",
        "severity_threshold": "Escalate when wilting patches expand outward across "
                              "the field or plant death continues beyond isolated "
                              "spots.",
    },
    "Groundnut Leaf Miner": {
        "scientific_name": "Aproaerema modicella",
        "affected_crops": ["groundnut"],
        "symptoms": "Papery, whitish blotch mines on leaflets; leaflets webbed "
                    "together and folded; premature drying and shedding of "
                    "affected leaves under heavy attack.",
        "visual_indicators": "Translucent whitish patches on leaflet surface where "
                             "larvae mine inside; leaflets folded and webbed "
                             "together, sometimes with a small larva visible inside "
                             "when unfolded.",
        "common_causes": "Continuous groundnut cultivation without rotation; dry "
                         "spells during the crop's mid-to-late vegetative stage.",
        "favorable_conditions": "Warm, relatively dry conditions during vegetative "
                                "growth.",
        "prevention": "Rotate away from groundnut in successive seasons where "
                      "possible; avoid moisture stress; monitor fields regularly "
                      "from early vegetative stage.",
        "cultural_control": "Remove and destroy severely mined/webbed leaves; "
                            "ensure timely irrigation to reduce plant stress; clear "
                            "crop residue after harvest.",
        "mechanical_control": "Light traps to monitor adult moth activity as an "
                              "early warning; handpicking is impractical at scale "
                              "but useful for small plots.",
        "biological_control": "Conserve parasitic wasps that attack the leaf miner "
                              "larvae; approved Bt-based products can also target "
                              "young larvae selectively.",
        "chemical_control": "Only above threshold, consider a locally registered "
                            "product with translaminar activity to reach larvae "
                            "inside the mine, following the label and local "
                            "guidance.",
        "severity_threshold": "Escalate when mining/webbing affects a large share "
                              "of leaflets across most plants, not scattered leaves.",
    },
}
