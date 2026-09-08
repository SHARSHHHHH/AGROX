"""Stage-by-stage lifecycle data for the crops missing from lifecycle.py.

WHY THIS FILE EXISTS
--------------------
The Crop Advisor's crop dropdown is built from MP_CROPS, which holds 15 crops.
LIFECYCLE held only 5. So ten of the fifteen options in that dropdown — every
one of them selectable — returned "No lifecycle data for <crop>." A farmer
picking Green Gram, Rice or Onion hit a dead end with no explanation.

Timings target Madhya Pradesh practice and are aligned to the duration_days
already recorded in MP_CROPS, so the last stage's end_day matches the duration
the rest of the app uses. Where they disagreed, MP_CROPS won, because the
advisor, the satellite phenology curve and the harvest-readiness logic all read
duration from there.

These are representative windows, not prescriptions. Variety, sowing date and
season shift every one of them, which is what the disclaimer on the endpoint
says.
"""

from typing import Dict, List

ADDITIONAL_LIFECYCLE: Dict[str, List[dict]] = {

    # ---------------------------------------------------------- 65 days
    "greengram": [
        {"stage": "Germination", "start_day": 0, "end_day": 8,
         "tasks": ["Treat seed with Rhizobium and Trichoderma before sowing",
                   "Sow at 4-5 cm depth, 30 cm between rows",
                   "Check emergence by day 6 — gaps should be filled early"],
         "irrigation": "Sow into moisture. If sown in summer, one light "
                       "irrigation immediately after sowing helps even "
                       "emergence.",
         "risks": ["Poor germination if sown too deep in heavy soil",
                   "Seedling damping-off in waterlogged patches"]},
        {"stage": "Vegetative", "start_day": 9, "end_day": 25,
         "tasks": ["First weeding at 15-20 days — moong competes poorly",
                   "Scout for whitefly, which spreads yellow mosaic virus",
                   "Remove and destroy any yellow-mosaic infected plants"],
         "irrigation": "Light irrigation if there is no rain for 8-10 days. "
                       "Moong is shallow-rooted and cannot pull deep moisture.",
         "risks": ["Yellow mosaic virus", "Weed competition", "Jassid"]},
        {"stage": "Flowering", "start_day": 26, "end_day": 40,
         "tasks": ["Scout twice weekly for thrips and pod borer",
                   "Do not apply nitrogen — it pushes leaf at the cost of pods",
                   "Avoid spraying during peak flowering hours to protect bees"],
         "irrigation": "Most critical stage. A single irrigation here protects "
                       "yield more than at any other point.",
         "risks": ["Flower drop from moisture stress or high temperature",
                   "Thrips damage to flowers"]},
        {"stage": "Pod filling", "start_day": 41, "end_day": 55,
         "tasks": ["Continue pod borer monitoring",
                   "Keep field weed-free until pods fill"],
         "irrigation": "Second critical stage. Stress now directly cuts seed "
                       "size.",
         "risks": ["Pod borer", "Powdery mildew in humid weather"]},
        {"stage": "Maturity", "start_day": 56, "end_day": 65,
         "tasks": ["Pick pods when 80% turn black — moong matures unevenly",
                   "A second picking 7-10 days later is normal and worthwhile",
                   "Dry to 9-10% moisture before storage"],
         "irrigation": "Stop irrigation completely.",
         "risks": ["Pod shattering if harvest is delayed",
                   "Rain on mature pods causes sprouting in the pod"]},
    ],

    # --------------------------------------------------------- 110 days
    "groundnut": [
        {"stage": "Germination", "start_day": 0, "end_day": 10,
         "tasks": ["Treat seed with Rhizobium and a fungicide",
                   "Sow at 5 cm depth, 30 x 10 cm spacing",
                   "Apply gypsum basal dose at sowing"],
         "irrigation": "Adequate moisture at sowing is essential. Crusted soil "
                       "after heavy rain blocks emergence.",
         "risks": ["Collar rot", "Poor emergence through a soil crust"]},
        {"stage": "Vegetative", "start_day": 11, "end_day": 35,
         "tasks": ["First weeding at 20-25 days",
                   "Earth up lightly to keep pegging zone loose",
                   "Scout for leaf miner and thrips"],
         "irrigation": "Irrigate if there is no rain for 10 days.",
         "risks": ["Leaf miner", "Weed competition", "Iron chlorosis in "
                   "high-pH soil"]},
        {"stage": "Flowering and pegging", "start_day": 36, "end_day": 60,
         "tasks": ["Apply the second gypsum dose at peak flowering",
                   "Do NOT disturb the soil once pegs enter the ground",
                   "Stop all inter-cultivation from day 45"],
         "irrigation": "Critical. The pegging zone must stay moist or pegs "
                       "cannot penetrate and pods never form.",
         "risks": ["Dry surface soil preventing peg entry",
                   "Tikka leaf spot beginning"]},
        {"stage": "Pod development", "start_day": 61, "end_day": 90,
         "tasks": ["Monitor for tikka leaf spot and rust; spray if needed",
                   "Keep the field free of late weeds without soil disturbance"],
         "irrigation": "Second critical stage. Stress now gives shrivelled "
                       "kernels.",
         "risks": ["Tikka leaf spot", "Rust", "White grub in light soil"]},
        {"stage": "Maturity", "start_day": 91, "end_day": 110,
         "tasks": ["Check maturity by shelling — inner shell should be dark",
                   "Harvest when 70-80% pods are mature",
                   "Dry pods to 8-9% moisture to prevent aflatoxin"],
         "irrigation": "Stop irrigation 10-15 days before harvest, but do not "
                       "let soil go bone dry or pods break off during lifting.",
         "risks": ["Aflatoxin contamination if pods are dried poorly",
                   "Pods left in soil if harvested from dry hard ground"]},
    ],

    # --------------------------------------------------------- 120 days
    "mustard": [
        {"stage": "Germination", "start_day": 0, "end_day": 8,
         "tasks": ["Sow at 2-3 cm depth — mustard seed is small and shallow",
                   "Maintain 30-45 cm row spacing",
                   "Apply full phosphorus and potash basal"],
         "irrigation": "Pre-sowing irrigation gives even emergence. Avoid "
                       "irrigating immediately after sowing — it crusts.",
         "risks": ["Poor stand from sowing too deep", "Soil crusting"]},
        {"stage": "Rosette and vegetative", "start_day": 9, "end_day": 35,
         "tasks": ["Thin to 10-15 cm between plants by day 20",
                   "First weeding at 20-25 days",
                   "Apply first nitrogen top-dress with the first irrigation"],
         "irrigation": "First irrigation around 30-35 days is important for "
                       "branching.",
         "risks": ["Aphid colonies starting on young shoots",
                   "Painted bug in early sown crop"]},
        {"stage": "Flowering", "start_day": 36, "end_day": 70,
         "tasks": ["Scout weekly for mustard aphid — this is the main pest",
                   "Spray only in the evening to protect pollinators",
                   "Do not irrigate during peak bloom if wind is strong"],
         "irrigation": "Critical stage. Moisture stress here cuts siliqua "
                       "number sharply.",
         "risks": ["Mustard aphid", "White rust", "Alternaria blight",
                   "Frost damage in December-January"]},
        {"stage": "Siliqua development", "start_day": 71, "end_day": 100,
         "tasks": ["Continue aphid monitoring until pods harden",
                   "Watch for Alternaria blight spreading up the plant"],
         "irrigation": "Second critical stage. Stress now shrinks seed size "
                       "and oil content.",
         "risks": ["Aphid", "Alternaria blight", "Lodging in over-irrigated "
                   "crop"]},
        {"stage": "Maturity", "start_day": 101, "end_day": 120,
         "tasks": ["Harvest when 75% siliquae turn yellow-brown",
                   "Harvest in the early morning to reduce shattering",
                   "Stack and cure 5-7 days before threshing"],
         "irrigation": "Stop irrigation completely.",
         "risks": ["Shattering losses from delayed or midday harvest",
                   "Unseasonal rain on stacked crop"]},
    ],

    # --------------------------------------------- 120 days (transplanted)
    "onion": [
        {"stage": "Transplant establishment", "start_day": 0, "end_day": 15,
         "tasks": ["Transplant 6-8 week old seedlings, 15 x 10 cm spacing",
                   "Dip roots in a fungicide solution before planting",
                   "Fill gaps within the first week"],
         "irrigation": "Irrigate immediately after transplanting, then every "
                       "3-4 days until roots establish.",
         "risks": ["Transplant shock", "Damping off in poorly drained beds"]},
        {"stage": "Vegetative", "start_day": 16, "end_day": 50,
         "tasks": ["First weeding at 20-25 days, second at 45 days",
                   "Apply first nitrogen top-dress at 30 days",
                   "Scout for thrips on young leaves"],
         "irrigation": "Every 7-10 days. Onion is shallow-rooted — little and "
                       "often beats heavy and rare.",
         "risks": ["Thrips", "Purple blotch beginning", "Weed competition"]},
        {"stage": "Bulb initiation", "start_day": 51, "end_day": 80,
         "tasks": ["Apply the second and final nitrogen top-dress by day 60",
                   "Stop all nitrogen after day 60 — late N delays bulbing and "
                   "gives thick necks that store badly",
                   "Continue thrips monitoring"],
         "irrigation": "Keep moisture steady. Fluctuation now causes bulb "
                       "splitting and doubles.",
         "risks": ["Thrips", "Purple blotch", "Bolting if temperatures swing"]},
        {"stage": "Bulb development", "start_day": 81, "end_day": 105,
         "tasks": ["Remove any bolted plants — they will not store",
                   "Keep the field weed-free but avoid deep hoeing near bulbs"],
         "irrigation": "Maintain even moisture until bulbs size up.",
         "risks": ["Purple blotch", "Stemphylium blight",
                   "Bulb rot in waterlogged patches"]},
        {"stage": "Maturity", "start_day": 106, "end_day": 120,
         "tasks": ["Stop irrigation when 50% of necks fall over",
                   "Harvest 10-15 days after neck fall",
                   "Cure in shade for 7-10 days before storage"],
         "irrigation": "Stop irrigation completely at neck fall. Late "
                       "irrigation is the single biggest cause of storage rot.",
         "risks": ["Storage rot from harvesting too wet",
                   "Sunscald if cured in direct sun"]},
    ],

    # --------------------------------------------------------- 170 days
    "pigeonpea": [
        {"stage": "Germination", "start_day": 0, "end_day": 12,
         "tasks": ["Treat seed with Rhizobium and Trichoderma",
                   "Sow at 4-5 cm depth, 60-90 cm between rows",
                   "Ensure drainage channels are cut before the monsoon peaks"],
         "irrigation": "Rain-fed at sowing. Waterlogging kills pigeonpea "
                       "seedlings faster than drought.",
         "risks": ["Waterlogging in black cotton soil",
                   "Phytophthora blight in wet spells"]},
        {"stage": "Vegetative", "start_day": 13, "end_day": 60,
         "tasks": ["First weeding at 25-30 days, second at 50 days",
                   "Keep drainage channels clear through the monsoon",
                   "Nip the growing tip at 45-50 days to encourage branching"],
         "irrigation": "Normally rain-fed. Drainage matters more than "
                       "irrigation at this stage.",
         "risks": ["Waterlogging", "Fusarium wilt in infected fields",
                   "Weed competition in wide rows"]},
        {"stage": "Flowering", "start_day": 61, "end_day": 110,
         "tasks": ["Begin pod borer scouting — Helicoverpa is the main threat",
                   "Install pheromone traps at 5 per hectare",
                   "Encourage bird perches for natural predation"],
         "irrigation": "Critical. One irrigation at flowering in a dry spell "
                       "gives a large yield response.",
         "risks": ["Helicoverpa pod borer", "Flower drop from moisture stress",
                   "Sterility mosaic virus"]},
        {"stage": "Pod development", "start_day": 111, "end_day": 150,
         "tasks": ["Continue pod borer monitoring until pods harden",
                   "Watch for pod fly, which leaves no external hole"],
         "irrigation": "Second critical stage. Stress now gives poorly filled "
                       "pods.",
         "risks": ["Pod borer", "Pod fly", "Pod bug"]},
        {"stage": "Maturity", "start_day": 151, "end_day": 170,
         "tasks": ["Harvest when 80% pods turn brown",
                   "Cut plants at ground level and stack for sun drying",
                   "Thresh and dry seed to 10-12% moisture"],
         "irrigation": "Stop irrigation completely.",
         "risks": ["Pod shattering if over-dried on the plant",
                   "Bruchid infestation in stored grain"]},
    ],

    # --------------------------------------------------------- 100 days
    "potato": [
        {"stage": "Sprouting and emergence", "start_day": 0, "end_day": 15,
         "tasks": ["Plant well-sprouted, disease-free seed tubers",
                   "Maintain 60 x 20 cm spacing, 5-6 cm deep",
                   "Apply full phosphorus and potash basal"],
         "irrigation": "Light irrigation right after planting. Never flood the "
                       "ridge top — seed tubers rot.",
         "risks": ["Seed tuber rot in waterlogged soil",
                   "Uneven emergence from poorly sprouted seed"]},
        {"stage": "Vegetative", "start_day": 16, "end_day": 35,
         "tasks": ["First earthing up at 20-25 days",
                   "Apply nitrogen top-dress at earthing up",
                   "Begin aphid monitoring — aphids spread potato viruses"],
         "irrigation": "Every 7-10 days, keeping ridges moist but never "
                       "submerged.",
         "risks": ["Aphid-transmitted virus", "Early blight starting",
                   "Cutworm"]},
        {"stage": "Tuber initiation", "start_day": 36, "end_day": 55,
         "tasks": ["Second earthing up to cover developing tubers",
                   "Any tuber exposed to light turns green and is unsaleable",
                   "Start late blight watch in cool humid weather"],
         "irrigation": "Critical stage. Keep moisture even — fluctuation now "
                       "causes cracked and knobbly tubers.",
         "risks": ["Late blight", "Greening of exposed tubers",
                   "Tuber cracking from irregular watering"]},
        {"stage": "Tuber bulking", "start_day": 56, "end_day": 85,
         "tasks": ["Continue late blight scouting after every cool, damp night",
                   "Maintain ridge cover over all tubers"],
         "irrigation": "Second critical stage and the heaviest water demand. "
                       "Stress here directly cuts tuber size.",
         "risks": ["Late blight", "Common scab in dry alkaline soil"]},
        {"stage": "Maturity", "start_day": 86, "end_day": 100,
         "tasks": ["Cut and remove haulm 10-15 days before digging",
                   "Let skins set before harvesting to avoid bruising",
                   "Cure in shade before storage"],
         "irrigation": "Stop irrigation 10-12 days before harvest.",
         "risks": ["Skin damage during digging",
                   "Storage rot from harvesting immature or wet tubers"]},
    ],

    # --------------------------------------------- 130 days (transplanted)
    "rice": [
        {"stage": "Transplant establishment", "start_day": 0, "end_day": 15,
         "tasks": ["Transplant 21-25 day old seedlings, 2-3 per hill",
                   "Maintain 20 x 15 cm spacing",
                   "Fill gaps within 7 days of transplanting"],
         "irrigation": "Keep 2-3 cm standing water until seedlings establish. "
                       "Deep water at this stage suppresses tillering.",
         "risks": ["Transplant shock", "Snail damage in standing water"]},
        {"stage": "Tillering", "start_day": 16, "end_day": 45,
         "tasks": ["Apply first nitrogen top-dress at 20-25 days",
                   "First weeding before the canopy closes",
                   "Scout for stem borer dead-hearts and leaf folder"],
         "irrigation": "Maintain 3-5 cm standing water. Alternate wetting and "
                       "drying from now saves water without cutting yield.",
         "risks": ["Stem borer", "Leaf folder", "Weed competition",
                   "Zinc deficiency in calcareous soil"]},
        {"stage": "Panicle initiation", "start_day": 46, "end_day": 70,
         "tasks": ["Apply second nitrogen top-dress at panicle initiation — "
                   "this is the highest-response dose of the season",
                   "Scout for brown planthopper at the base of the plant",
                   "Check for sheath blight in the lower canopy"],
         "irrigation": "Critical. Do not let the field dry out. Keep 5 cm "
                       "standing water.",
         "risks": ["Brown planthopper", "Sheath blight", "Blast in cool "
                   "humid weather"]},
        {"stage": "Flowering", "start_day": 71, "end_day": 95,
         "tasks": ["Avoid all spraying during flowering hours",
                   "Continue planthopper and neck blast monitoring"],
         "irrigation": "Most critical stage. Water stress at flowering causes "
                       "spikelet sterility that cannot be recovered.",
         "risks": ["Neck blast", "Brown planthopper hopperburn",
                   "Spikelet sterility from heat or cold"]},
        {"stage": "Grain filling", "start_day": 96, "end_day": 115,
         "tasks": ["Watch for grain discolouration and ear-head bug",
                   "Do not apply nitrogen now — it delays maturity"],
         "irrigation": "Maintain shallow water, then begin draining towards "
                       "the end of this stage.",
         "risks": ["Ear-head bug", "Grain discolouration", "Lodging"]},
        {"stage": "Maturity", "start_day": 116, "end_day": 130,
         "tasks": ["Drain the field 10 days before harvest",
                   "Harvest when 80-85% grains are straw-coloured",
                   "Dry grain to 12-14% moisture before storage"],
         "irrigation": "Drain completely. A wet field at harvest makes "
                       "machine harvesting impossible.",
         "risks": ["Shattering if harvest is delayed",
                   "Rain damage to cut crop lying in the field"]},
    ],

    # --------------------------------------------------------- 110 days
    "sorghum": [
        {"stage": "Germination", "start_day": 0, "end_day": 10,
         "tasks": ["Sow at 3-4 cm depth, 45 cm between rows",
                   "Thin to 10-15 cm between plants by day 15",
                   "Treat seed against shoot fly before sowing"],
         "irrigation": "Sow into moisture. Sorghum germinates poorly in dry "
                       "soil but tolerates drought well once established.",
         "risks": ["Shoot fly in late-sown crop", "Poor stand in dry soil"]},
        {"stage": "Vegetative", "start_day": 11, "end_day": 40,
         "tasks": ["First weeding at 20-25 days",
                   "Apply nitrogen top-dress at 30 days",
                   "Scout for stem borer dead-hearts"],
         "irrigation": "Largely rain-fed. Irrigate only in a prolonged break.",
         "risks": ["Stem borer", "Shoot fly", "Weed competition"]},
        {"stage": "Boot and panicle initiation", "start_day": 41,
         "end_day": 60,
         "tasks": ["Continue stem borer monitoring",
                   "Check for downy mildew and rogue infected plants"],
         "irrigation": "Critical stage. One irrigation here in a dry spell "
                       "gives a strong response.",
         "risks": ["Stem borer", "Downy mildew"]},
        {"stage": "Flowering", "start_day": 61, "end_day": 80,
         "tasks": ["Watch for midge during flowering — damage is invisible "
                   "until grain fails to form",
                   "Protect from birds as grain begins to set"],
         "irrigation": "Second critical stage. Stress now causes poor grain "
                       "set.",
         "risks": ["Sorghum midge", "Head smut", "Bird damage"]},
        {"stage": "Grain filling", "start_day": 81, "end_day": 100,
         "tasks": ["Continue bird protection — this is when losses are worst",
                   "Watch for grain mould in humid weather"],
         "irrigation": "Moisture stress now reduces grain weight.",
         "risks": ["Bird damage", "Grain mould", "Ear-head bug"]},
        {"stage": "Maturity", "start_day": 101, "end_day": 110,
         "tasks": ["Harvest when grain hardens and shows a black layer at the "
                   "base",
                   "Dry to 12% moisture before storage",
                   "Fodder can be cut and stacked after grain harvest"],
         "irrigation": "Stop irrigation completely.",
         "risks": ["Grain mould if rain falls on mature heads",
                   "Storage pests in poorly dried grain"]},
    ],

    # --------------------------------------------------------- 330 days
    "sugarcane": [
        {"stage": "Germination", "start_day": 0, "end_day": 45,
         "tasks": ["Plant healthy three-budded setts from a 9-10 month crop",
                   "Treat setts in fungicide before planting",
                   "Fill gaps by day 40 — late gap filling never catches up"],
         "irrigation": "Irrigate every 7-10 days. Setts need constant moisture "
                       "to sprout evenly.",
         "risks": ["Poor sprouting from diseased or dried setts",
                   "Termite attack on setts in light soil"]},
        {"stage": "Tillering", "start_day": 46, "end_day": 120,
         "tasks": ["First earthing up at 60-70 days",
                   "Apply nitrogen in split doses through this stage",
                   "Scout for early shoot borer causing dead hearts"],
         "irrigation": "Every 10-12 days. This stage sets the final number of "
                       "millable canes.",
         "risks": ["Early shoot borer", "Weed competition in the wide "
                   "inter-row"]},
        {"stage": "Grand growth", "start_day": 121, "end_day": 240,
         "tasks": ["Final earthing up and propping to prevent lodging",
                   "Complete all nitrogen application by day 150",
                   "Detrash lower dry leaves to reduce pest shelter",
                   "Scout for top borer and internode borer"],
         "irrigation": "Heaviest water demand of the whole cycle. Stress here "
                       "costs more yield than at any other stage.",
         "risks": ["Top borer", "Internode borer", "Lodging in unpropped "
                   "crop", "Red rot in susceptible varieties"]},
        {"stage": "Maturity and ripening", "start_day": 241, "end_day": 300,
         "tasks": ["Stop all nitrogen — late N keeps cane green and cuts sugar",
                   "Check sugar content with a hand refractometer from day 270",
                   "Arrange harvest and mill scheduling in advance"],
         "irrigation": "Reduce irrigation gradually. Withholding water in the "
                       "last 4-6 weeks raises sugar recovery.",
         "risks": ["Low sugar recovery from late nitrogen or late irrigation",
                   "Rat damage in mature cane"]},
        {"stage": "Harvest", "start_day": 301, "end_day": 330,
         "tasks": ["Cut at ground level — the lowest internodes hold the most "
                   "sugar",
                   "Deliver to the mill within 24 hours of cutting",
                   "Keep the base intact if you intend to take a ratoon crop"],
         "irrigation": "Stop irrigation completely before harvest.",
         "risks": ["Sugar loss from delay between cutting and crushing",
                   "Poor ratoon if stubble is cut too high"]},
    ],

    # --------------------------------------------- 120 days (transplanted)
    "tomato": [
        {"stage": "Transplant establishment", "start_day": 0, "end_day": 15,
         "tasks": ["Transplant 25-30 day old seedlings, 60 x 45 cm spacing",
                   "Dip roots in fungicide before planting",
                   "Transplant in the evening to reduce wilting"],
         "irrigation": "Irrigate immediately after transplanting, then every "
                       "3-4 days.",
         "risks": ["Transplant shock", "Damping off", "Cutworm at the collar"]},
        {"stage": "Vegetative", "start_day": 16, "end_day": 40,
         "tasks": ["Stake or trellis plants before they begin to sprawl",
                   "First weeding and nitrogen top-dress at 25-30 days",
                   "Begin whitefly monitoring — it spreads leaf curl virus",
                   "Rogue out any leaf-curl infected plants immediately"],
         "irrigation": "Every 5-7 days. Avoid wetting the foliage.",
         "risks": ["Tomato leaf curl virus", "Whitefly", "Early blight"]},
        {"stage": "Flowering", "start_day": 41, "end_day": 65,
         "tasks": ["Continue whitefly and fruit borer scouting",
                   "Install pheromone traps for fruit borer",
                   "Avoid heavy nitrogen — it drops flowers"],
         "irrigation": "Critical stage. Keep moisture even; fluctuation causes "
                       "flower drop.",
         "risks": ["Flower drop from heat or moisture stress",
                   "Fruit borer", "Early blight"]},
        {"stage": "Fruit development", "start_day": 66, "end_day": 95,
         "tasks": ["Scout for fruit borer twice weekly and remove bored fruit",
                   "Watch for late blight in cool humid weather",
                   "Support heavy trusses to prevent branch breakage"],
         "irrigation": "Steady moisture is essential. Irregular watering here "
                       "causes blossom-end rot and fruit cracking.",
         "risks": ["Fruit borer", "Late blight", "Blossom-end rot",
                   "Fruit cracking after sudden irrigation"]},
        {"stage": "Harvest", "start_day": 96, "end_day": 120,
         "tasks": ["Pick every 3-4 days at the colour stage your market wants",
                   "Harvest at breaker stage for distant markets, ripe for "
                   "local sale",
                   "Handle carefully — bruised fruit will not keep"],
         "irrigation": "Continue light irrigation between pickings. Stopping "
                       "water entirely ends the picking season early.",
         "risks": ["Fruit borer in late pickings",
                   "Post-harvest losses from rough handling",
                   "Price crash at peak arrival — stagger picking if possible"]},
    ],
}
