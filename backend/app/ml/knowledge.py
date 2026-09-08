"""Structured agricultural knowledge base (RAG source of truth).

Disease facts here — NOT invented by the LLM. The vision model only picks a
label; symptoms/causes/treatment come from this verified dictionary.
"""

DISEASE_KB = {
    "Early Blight": {
        "crops": ["tomato", "potato"],
        "symptoms": "Dark brown concentric-ring spots on older leaves, yellowing "
                    "around spots, lower leaves affected first.",
        "causes": "Fungus Alternaria solani, favoured by warm humid weather and "
                  "leaf wetness.",
        "prevention": "Rotate crops, space plants for airflow, avoid overhead "
                      "watering, remove infected debris.",
        "treatment": "Remove affected leaves. Apply a recommended fungicide "
                     "(e.g. mancozeb or chlorothalonil) following label rates. "
                     "Improve airflow and avoid wetting foliage.",
    },
    "Late Blight": {
        "crops": ["tomato", "potato"],
        "symptoms": "Large water-soaked grey-green patches, white fungal growth on "
                    "leaf undersides in humid conditions, rapid collapse.",
        "causes": "Oomycete Phytophthora infestans, cool wet conditions.",
        "prevention": "Use resistant varieties, avoid dense planting, do not water "
                      "late in the day.",
        "treatment": "Remove and destroy infected plants immediately. Apply "
                     "protective fungicide. Act fast — this spreads rapidly.",
    },
    "Leaf Mold": {
        "crops": ["tomato"],
        "symptoms": "Pale green to yellow spots on upper leaf surface, olive-green "
                    "to brown velvety mold underneath.",
        "causes": "Fungus Passalora fulva, high humidity and poor ventilation.",
        "prevention": "Increase ventilation, reduce humidity, avoid leaf wetness.",
        "treatment": "Improve airflow, reduce humidity, apply appropriate fungicide "
                     "if severe.",
    },
    "Bacterial Spot": {
        "crops": ["tomato", "chilli"],
        "symptoms": "Small dark water-soaked spots on leaves and fruit, spots may "
                    "have yellow halos.",
        "causes": "Xanthomonas bacteria, warm wet weather, splashing water.",
        "prevention": "Use disease-free seed, avoid overhead irrigation, rotate crops.",
        "treatment": "Remove affected parts, apply copper-based bactericide, avoid "
                     "working with wet plants.",
    },
    "Powdery Mildew": {
        "crops": ["cucumber", "chilli", "brinjal"],
        "symptoms": "White powdery patches on leaves and stems, leaves may yellow "
                    "and dry.",
        "causes": "Fungal, warm dry days with humid nights.",
        "prevention": "Space plants, ensure sunlight, avoid excess nitrogen.",
        "treatment": "Apply sulphur or potassium-bicarbonate spray; remove heavily "
                     "infected leaves.",
    },
    "Leaf Curl": {
        "crops": ["chilli", "tomato"],
        "symptoms": "Upward curling and crinkling of leaves, stunted growth.",
        "causes": "Often viral (spread by whiteflies) or nutrient/environmental "
                  "stress.",
        "prevention": "Control whiteflies, remove infected plants, use tolerant "
                      "varieties.",
        "treatment": "Manage whitefly population, remove severely infected plants, "
                     "maintain balanced nutrition.",
    },
    "Blast": {
        "crops": ["rice"],
        "symptoms": "Diamond-shaped lesions with grey centres on leaves; can affect "
                    "neck and panicle.",
        "causes": "Fungus Magnaporthe oryzae, high humidity and nitrogen excess.",
        "prevention": "Balanced nitrogen, resistant varieties, proper spacing.",
        "treatment": "Apply recommended fungicide (e.g. tricyclazole), avoid excess "
                     "nitrogen.",
    },
    "Downy Mildew": {
        "crops": ["cucumber", "onion", "spinach"],
        "symptoms": "Yellow angular patches on upper leaf surface, greyish growth "
                    "underneath.",
        "causes": "Oomycete pathogens, cool moist conditions.",
        "prevention": "Improve drainage and airflow, avoid leaf wetness.",
        "treatment": "Remove infected leaves, apply appropriate fungicide, reduce "
                     "humidity.",
    },
    "Anthracnose": {
        "crops": ["chilli", "tomato"],
        "symptoms": "Sunken dark circular lesions on fruit, often with pink spore "
                    "masses.",
        "causes": "Colletotrichum fungi, warm wet weather.",
        "prevention": "Use healthy seed, rotate crops, avoid fruit contact with soil.",
        "treatment": "Remove infected fruit, apply fungicide, harvest promptly.",
    },
    "Mosaic Virus": {
        "crops": ["tomato", "cucumber", "chilli"],
        "symptoms": "Mottled light/dark green mosaic pattern, distorted leaves, "
                    "stunted growth.",
        "causes": "Viral, spread by aphids and handling.",
        "prevention": "Control aphids, sanitise tools, remove infected plants.",
        "treatment": "No cure — remove infected plants, control insect vectors to "
                     "protect healthy plants.",
    },
}

NUTRIENT_KB = {
    "Nitrogen": "Drives leafy green growth. Deficiency: older leaves yellow. "
                "Excess: lush foliage, poor fruiting, disease-prone.",
    "Phosphorus": "Supports roots, flowering, fruiting. Deficiency: purplish "
                  "leaves, poor roots.",
    "Potassium": "Improves fruit quality and disease resistance. Deficiency: "
                 "leaf-edge scorching.",
    "Calcium": "Cell-wall strength. Deficiency: blossom-end rot in tomato.",
    "Magnesium": "Core of chlorophyll. Deficiency: yellowing between leaf veins.",
    "Iron": "Chlorophyll formation. Deficiency: yellowing of young leaves.",
    "Zinc": "Enzyme function. Deficiency: small leaves, stunted growth.",
}
